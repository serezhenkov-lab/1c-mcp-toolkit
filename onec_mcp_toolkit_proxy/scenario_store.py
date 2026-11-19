"""Durable run/step links. Operation truth remains in the shared lifecycle."""
from contextlib import contextmanager, closing
import json
import os
from pathlib import Path
import sqlite3


class RunStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        # OS locks are released on process death; no stale PID/lease takeover.
        with open(str(self.path)+'.lock', 'a+b') as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, state TEXT NOT NULL)')
        return connection

    def save(self, state):
        with closing(self._connect()) as connection, connection:
            connection.execute('INSERT OR REPLACE INTO runs VALUES (?, ?)',
                               (state['output']['run_id'], json.dumps(state, ensure_ascii=False)))

    def load(self, run_id):
        with closing(self._connect()) as connection:
            row = connection.execute('SELECT state FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise ValueError('run_state_unavailable')
        state = json.loads(row[0])
        # JSON does not preserve shared references between output and entries.
        for entry in state['output']['steps']:
            state['entries'][entry['step_id']]['entry'] = entry
        return state

    def list_runs(self):
        with self.locked(), closing(self._connect()) as connection:
            states=[json.loads(row[0]) for row in connection.execute('SELECT state FROM runs ORDER BY rowid')]
        return [dict(run_id=s['output']['run_id'],status=s['output']['status'],
                     scenario_id=s['template']['scenario_id'],dispatch_count=s['output']['dispatch_count'],
                     steps=[{k:e[k] for k in ('step_id','status','operation_id')} for e in s['output']['steps']]) for s in states]
