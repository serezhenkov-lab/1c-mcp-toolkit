"""Последовательный файловый канал к клиенту 1С через перенаправленный диск RDP."""

import asyncio
import json
import logging
import os
import re
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)


def configured_channels(environ=None):
    """Единый CSV-список для одного или нескольких файловых каналов."""
    env = os.environ if environ is None else environ
    if not env.get('FILE_BRIDGE_ROOT'):
        return []
    raw = env.get('FILE_BRIDGE_CHANNELS', '')
    if not raw.strip():
        raise ValueError('Set FILE_BRIDGE_CHANNELS, for example: 1703784,1690771')
    channels = [part.strip() for part in raw.split(',')]
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CLOCK$'}
    reserved.update(f'{prefix}{number}' for prefix in ('COM', 'LPT') for number in range(1, 10))
    seen = set()
    for channel in channels:
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', channel) or channel.upper() in reserved:
            raise ValueError(f'Invalid file bridge channel: {channel!r}')
        if channel.lower() in seen:
            raise ValueError(f'Duplicate file bridge channel: {channel!r}')
        seen.add(channel.lower())
    return channels


def write_json(path: Path, value: dict) -> None:
    """Публикация только полностью записанного документа в том же каталоге."""
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class FileTransport:
    def __init__(self, root, channel, queue, timeout, result_model):
        self.channel = channel
        self.queue = queue
        self.timeout = timeout
        self.result_model = result_model
        self.directory = Path(root).resolve() / str(uuid4())
        self.directory.mkdir(parents=True)
        self.active = None
        write_json(self.directory / 'session.json', {'version': 1, 'channel': channel})
        # Публикуется после готовности сеанса; путь в 1С остаётся постоянным.
        write_json(self.directory.parent / 'current.json', {
            'version': 1, 'channel': channel, 'session': self.directory.name,
        })
        logger.info('RDP file channel: %s (channel=%s)', self.directory.parent, channel)
        logger.info('RDP file session: %s (channel=%s)', self.directory, channel)

    async def step(self):
        if self.active is not None:
            response = self.directory / (self.active + '.response.json')
            if not response.exists():
                # Не повторяем команду и не запускаем следующую при неизвестном исходе.
                return
            if response.stat().st_size > 32 * 1024 * 1024:
                raise ValueError('File response exceeds 32 MiB')
            body = json.loads(response.read_text(encoding='utf-8-sig'))
            result = self.result_model(**body)
            if result.id != self.active:
                raise ValueError('File response id mismatch')
            await self.queue.set_result(self.active, result.model_dump(exclude={'id'}, exclude_none=True))
            for suffix in ('.response.json', '.running', '.request.json'):
                (self.directory / (self.active + suffix)).unlink(missing_ok=True)
            self.active = None

        command = await self.queue.get_next_command(self.channel, timeout=0)
        if command is None:
            return
        # Устанавливается до записи: неоднозначную ошибку публикации нельзя повторять.
        self.active = command.id
        body = command.to_dict()
        body['channel'] = self.channel
        body['expires_at'] = (command.created_at + timedelta(seconds=self.timeout)).strftime('%Y%m%d%H%M%S')
        write_json(self.directory / (command.id + '.request.json'), body)

    async def run(self):
        try:
            while True:
                await self.step()
                await asyncio.sleep(0.25)
        except Exception:
            logger.exception('File transport for channel %s stopped; restart with a fresh session directory',
                             self.channel)
        finally:
            # Старые задания не должны исполняться после штатной остановки прокси.
            (self.directory / 'session.json').unlink(missing_ok=True)
