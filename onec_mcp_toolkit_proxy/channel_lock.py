"""Межпроцессный захват локального канала; блокировка снимается ОС при выходе."""
import json
import os
from uuid import UUID


class ChannelLock:
    def __init__(self, directory):
        self.directory = directory
        self.file = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.file = (self.directory / 'proxy.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise RuntimeError(f'File channel busy: {self.directory}') from exc
        return self

    def __exit__(self, *exc):
        if self.file is not None:
            # Не удалять lock-файл: другой процесс может уже ждать тот же файл.
            self.file.close()
            self.file = None


def check_unresolved(directory):
    pointer = directory / 'current.json'
    if not pointer.exists():
        return
    body = json.loads(pointer.read_text(encoding='utf-8-sig'))
    session = str(UUID(body['session']))
    if session != body['session'] or body.get('channel') != directory.name:
        raise ValueError(f'Invalid file channel pointer: {pointer}')
    previous = directory / session
    if any(previous.glob('*.request.json')) or any(previous.glob('*.running')):
        raise RuntimeError(
            f'Unresolved file request in {previous}. Check the outcome in 1C; '
            'do not retry automatically. After resolution, disconnect the old EPF '
            'and archive current.json before restarting.')
