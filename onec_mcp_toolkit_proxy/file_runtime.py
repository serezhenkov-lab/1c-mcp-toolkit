"""Общий жизненный цикл файловых каналов для HTTP и stdio."""
import asyncio
import logging
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import anyio

from .channel_lock import ChannelLock, check_unresolved
from .command_queue import channel_command_queue
from .config import settings
from .file_transport import FileTransport
from .result_models import CommandResult

logger = logging.getLogger(__name__)


COMMAND_CLEANUP_INTERVAL = 60.0


async def cleanup_abandoned_commands() -> None:
    """Safety net for commands left without an active result waiter."""
    max_age = max(float(settings.timeout) * 2, 300.0)
    while True:
        await asyncio.sleep(COMMAND_CLEANUP_INTERVAL)
        try:
            removed = await channel_command_queue.cleanup_expired(max_age)
            if removed:
                logger.warning("Removed %d abandoned commands", removed)
        except Exception:
            logger.exception("Failed to clean up abandoned commands")


@asynccontextmanager
async def file_runtime(channels, root):
    bridges = {}
    tasks = []
    with ExitStack() as locks:
        try:
            # Захватить все каналы до публикации новых current.json.
            for channel in channels:
                directory = Path(root).resolve() / channel
                locks.enter_context(ChannelLock(directory))
                check_unresolved(directory)
            for channel in channels:
                bridge = FileTransport(Path(root) / channel, channel,
                                       channel_command_queue, settings.timeout, CommandResult)
                bridges[channel] = bridge
                tasks.append(asyncio.create_task(bridge.run(), name=f"rdp-file-{channel}"))
            cleanup_task = asyncio.create_task(cleanup_abandoned_commands())
            tasks.append(cleanup_task)
            yield SimpleNamespace(bridges=bridges, tasks=tasks)
        finally:
            for task in tasks:
                task.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.gather(*tasks, return_exceptions=True)
                for bridge in bridges.values():
                    (bridge.directory / 'session.json').unlink(missing_ok=True)
