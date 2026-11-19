"""Recover only fenced, journal-owned file commands. Never replay old files."""
import ctypes
import json
import os
from uuid import UUID


class RecoveryBlocked(Exception):
    pass


class ExecutorFence:
    """Windows write handle sharing only READ, matching 1C FileStream.

    Do not replace with a Python byte-range lock: 1C must deny the open itself.
    """
    def __init__(self, path):
        self.path = path
        self.handle = None

    def __enter__(self):
        if os.name != 'nt':
            raise RecoveryBlocked('executor_fence_platform_unverified')
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.CreateFileW(str(self.path), 0xC0000000, 1, None, 4, 128, None)
        if handle == ctypes.c_void_p(-1).value:
            error = ctypes.get_last_error()
            raise RecoveryBlocked('executor_busy' if error in (32, 33) else 'executor_fence_unavailable')
        self.handle = handle
        self.kernel = kernel
        return self

    def __exit__(self, *exc):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def read_small(path):
    if path.stat().st_size > 4096:
        raise RecoveryBlocked('invalid_recovery_metadata')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def recover_channel(directory, queue, *, fence_factory=ExecutorFence):
    """Return a held fence across publication, or None for a clean channel.
    Caller holds proxy.lock and must close returned fence after new current.json.
    """
    pointer = directory / 'current.json'
    if not pointer.exists():
        return None
    body = read_small(pointer)
    session = str(UUID(body['session']))
    if body.get('version') != 1 or body.get('channel') != directory.name or body['session'] != session:
        raise RecoveryBlocked('invalid_channel_pointer')
    previous = directory / session
    if previous.is_symlink() or previous.resolve().parent != directory.resolve():
        raise RecoveryBlocked('invalid_session_directory')
    # Requests first: a concurrent atomic claim moves request -> running.
    # Reversing these scans could miss the command in both and publish unfenced.
    pending = list(previous.glob('*.request.json')) + list(previous.glob('*.running'))
    if not pending:
        return None
    if len(pending) > 1000:
        raise RecoveryBlocked('recovery_budget_exceeded')
    store = queue.operation_store()  # durable startup transition to unknown, no admission/replay
    for path in pending:
        identifier = path.name.split('.')[0]
        if str(UUID(identifier)) != identifier:
            raise RecoveryBlocked('invalid_command_identity')
        marker = previous / (identifier + '.fence.json')
        if not marker.exists():
            raise RecoveryBlocked('legacy_unfenced_request')
        if read_small(marker) != dict(version=1,channel=directory.name,session=session,id=identifier):
            raise RecoveryBlocked('invalid_executor_fence')
        row = store.get(directory.name, identifier)
        if row['state'] not in ('unknown','succeeded','failed','rejected','result_expired'):
            raise RecoveryBlocked('operation_not_recovered')
    # Revoke before attempting exclusion. The manager rechecks this under its fence.
    (previous / 'session.json').unlink(missing_ok=True)
    fence = fence_factory(directory / 'executor.lock')
    fence.__enter__()
    # Preserve pointer and all evidence; archive is idempotent after a crash here.
    try:
        archive = previous / 'retired-current.json'
        if not archive.exists():
            with archive.open('x', encoding='utf-8') as stream:
                json.dump(body, stream)
                stream.flush()
                os.fsync(stream.fileno())
        return fence
    except BaseException:
        fence.__exit__(None,None,None)
        raise
