"""Жизненный цикл файловых каналов HTTP-прокси."""
import asyncio
import logging
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import anyio

from .channel_lock import ChannelLock
from .command_queue import channel_command_queue
from .config import settings
from .file_transport import FileTransport
from .result_models import CommandResult
from .consumer_registry import consumer_registry
from .file_recovery import recover_channel, RecoveryBlocked

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
    consumers = []
    recovery = {}
    async def start_channel(channel):
        directory = Path(root).resolve() / channel
        while True:
            fence = None
            try:
                recovery[channel] = {'state': 'recovering'}
                fence = recover_channel(directory, channel_command_queue)
                bridge = FileTransport(directory, channel, channel_command_queue, settings.timeout, CommandResult)
                bridges[channel] = bridge
                recovery[channel] = {'state': 'ready'}
                if fence is not None:
                    fence.__exit__(None,None,None)
                    fence = None
                await bridge.run()
                recovery[channel] = {'state': 'stopped'}
                return
            except RecoveryBlocked as exc:
                recovery[channel] = {'state': 'blocked', 'reason': str(exc)}
            except Exception:
                recovery[channel] = {'state': 'blocked', 'reason': 'recovery_unavailable'}
                logger.exception('File channel recovery failed: %s', channel)
            finally:
                if fence is not None:
                    fence.__exit__(None,None,None)
            await asyncio.sleep(1)
    with ExitStack() as locks:
        try:
            # Захватить все каналы до публикации новых current.json.
            for channel in channels:
                directory = Path(root).resolve() / channel
                locks.enter_context(ChannelLock(directory))
            for channel in channels:
                consumers.append(consumer_registry.bind(channel, 'file'))
                tasks.append(asyncio.create_task(start_channel(channel), name=f"rdp-file-{channel}"))
            cleanup_task = asyncio.create_task(cleanup_abandoned_commands())
            tasks.append(cleanup_task)
            yield SimpleNamespace(bridges=bridges, tasks=tasks, recovery=recovery)
        finally:
            for task in tasks:
                task.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.gather(*tasks, return_exceptions=True)
                # Проверяем все каналы, даже если один файл остался заблокирован.
                revoked = await asyncio.gather(
                    *(bridge.revoke_session() for bridge in bridges.values()),
                    return_exceptions=True)
                for consumer in consumers:
                    consumer_registry.retire(consumer)
                for result in revoked:
                    if isinstance(result, BaseException):
                        raise result
