"""MCP stdio с одним файловым каналом; HTTP-приложение не загружается."""
import asyncio
import os

from threading import Thread
from mcp.server.stdio import stdio_server

from .channel_registry import stdio_channel
from .file_runtime import file_runtime
from .mcp_handler import get_mcp_server


class CancellableStdin:
    """SDK AsyncFile ждёт readline даже после отмены; pipe может оставаться открытым.

    Читаем fd без буфера Python, чтобы отмена и выход процесса не ждали
    освобождения stdin другим концом pipe. MCP framing остаётся в SDK.
    """
    def __init__(self):
        self.pending = b''
        self.eof = False
        self.chunks = asyncio.Queue()
        self.loop = asyncio.get_running_loop()
        # Daemon + os.read: нет потока executor, задерживающего выход Python,
        # и нет блокировки buffered stdin при завершении интерпретатора.
        Thread(target=self._read, name='mcp-stdin', daemon=True).start()

    def _read(self):
        while True:
            try:
                chunk = os.read(0, 65536)
            except OSError as exc:
                chunk = exc
            try:
                self.loop.call_soon_threadsafe(self.chunks.put_nowait, chunk)
            except RuntimeError:  # event loop уже завершён
                return
            if not chunk or isinstance(chunk, Exception):
                return

    def __aiter__(self):
        return self

    async def __anext__(self):
        while b'\n' not in self.pending:
            if self.eof:
                raise StopAsyncIteration
            chunk = await self.chunks.get()
            if isinstance(chunk, Exception):
                raise chunk
            if not chunk:
                self.eof = True
                if not self.pending:
                    raise StopAsyncIteration
                line, self.pending = self.pending, b''
                return line.decode('utf-8', errors='replace')
            self.pending += chunk
        line, self.pending = self.pending.split(b'\n', 1)
        return (line + b'\n').decode('utf-8', errors='replace')


async def serve_mcp():
    server = get_mcp_server()._mcp_server
    async with stdio_server(stdin=CancellableStdin()) as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def run_stdio(root, channel):
    token = stdio_channel.set(channel)
    try:
        async with file_runtime([channel], root) as runtime:
            server = asyncio.create_task(serve_mcp())
            try:
                done, _ = await asyncio.wait([server, *runtime.tasks],
                                             return_when=asyncio.FIRST_COMPLETED)
                if server in done:
                    await server
                else:
                    raise RuntimeError(f'File transport stopped for channel {channel}')
            finally:
                server.cancel()
                await asyncio.gather(server, return_exceptions=True)
    finally:
        stdio_channel.reset(token)
