"""Durable operation ownership for the existing proxy queue (no executor here)."""
from .operation_progress import valid_progress, public_progress
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid

from .channel_lock import ChannelLock


class OperationError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError):
        raise OperationError('invalid_params') from None


class OperationJournal:
    """One owner, FULL synchronous transactions, permanent bounded key tombstones.

    Payloads expire; keys never become reusable. At the record/byte quota admission
    fails, rather than evicting running/unknown or silently forgetting old keys.
    Commands/credentials are not stored, only their content digest and tool name.
    """
    def __init__(self, directory, *, result_ttl=86400, max_records=10000,
                 max_bytes=64 * 1024 * 1024, max_result_bytes=4 * 1024 * 1024, clock=time.time):
        self.clock = clock
        self.result_ttl = result_ttl
        self.max_records = max_records
        self.max_bytes = max_bytes
        self.max_result_bytes = max_result_bytes
        self.lock = ChannelLock(Path(directory))
        self.db = None
        try:
            self.lock.__enter__()
            path = Path(directory) / 'operations.sqlite3'
            self.db = sqlite3.connect(path, timeout=1)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('PRAGMA journal_mode=DELETE')
            self.db.execute('PRAGMA max_page_count=32768')  # 128 MiB at default 4 KiB pages
            self.db.execute('''CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY, channel TEXT NOT NULL, request_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL, tool TEXT NOT NULL, state TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, expires REAL,
                result TEXT, result_bytes INTEGER NOT NULL DEFAULT 0, error_code TEXT,
                UNIQUE(channel, request_key))''')
            columns = {row['name'] for row in self.db.execute('PRAGMA table_info(operations)')}
            if 'event_seq' not in columns:
                self.db.execute('ALTER TABLE operations ADD COLUMN event_seq INTEGER NOT NULL DEFAULT 0')
            if 'context' not in columns:
                self.db.execute('ALTER TABLE operations ADD COLUMN context TEXT')
            if 'progress' not in columns:
                self.db.execute('ALTER TABLE operations ADD COLUMN progress TEXT')
            if 'progress_bytes' not in columns:
                self.db.execute('ALTER TABLE operations ADD COLUMN progress_bytes INTEGER NOT NULL DEFAULT 0')
            # Never replay an accepted command after loss of the owner process.
            with self.db:
                self.db.execute("UPDATE operations SET state='unknown', error_code='executor_restarted', updated=? "
                                "WHERE state IN ('queued','running','awaiting_approval')", (clock(),))
        except Exception:
            self.close()
            raise OperationError('operation_store_unavailable') from None

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        self.lock.__exit__(None, None, None)

    def _expire(self):
        self.db.execute("UPDATE operations SET state='result_expired', result=NULL, result_bytes=0, progress=NULL, progress_bytes=0, "
                        "error_code='result_expired' WHERE expires IS NOT NULL AND expires<=? "
                        "AND state IN ('succeeded','failed','rejected')", (self.clock(),))

    def expire_results(self):
        try:
            with self.db:
                self._expire()
        except sqlite3.Error:
            raise OperationError('operation_store_unavailable') from None

    def find(self, channel, request_key, tool, params):
        if not isinstance(request_key, str) or not 1 <= len(request_key) <= 128:
            raise OperationError('invalid_request_id')
        digest = hashlib.sha256(canonical({'tool': tool, 'params': params}).encode('utf-8')).hexdigest()
        try:
            with self.db:
                self._expire()
                row = self.db.execute('SELECT * FROM operations WHERE channel=? AND request_key=?',
                                      (channel, request_key)).fetchone()
            if row and row['fingerprint'] != digest:
                raise OperationError('request_conflict')
            return (dict(row) if row else None), digest
        except sqlite3.Error:
            raise OperationError('operation_store_unavailable') from None

    def reserve(self, channel, request_key, tool, params, *, context=None):
        row, digest = self.find(channel, request_key, tool, params)
        if row:
            return row['id'], False
        try:
            with self.db:
                count, size = self.db.execute('SELECT COUNT(*), COALESCE(SUM(result_bytes + progress_bytes),0) FROM operations').fetchone()
                if count >= self.max_records or size >= self.max_bytes:
                    raise OperationError('operation_quota_exceeded')
                identifier = str(uuid.uuid4())
                now = self.clock()
                self.db.execute('INSERT INTO operations (id,channel,request_key,fingerprint,tool,state,created,updated) '
                                "VALUES (?,?,?,?,?,'queued',?,?)", (identifier, channel, request_key, digest, tool, now, now))
                if context is not None:
                    # Adapter-owned public identity only, never command input/credentials.
                    payload = canonical(context)
                    if len(payload.encode('utf-8')) > 1024:
                        raise OperationError('invalid_params')
                    self.db.execute('UPDATE operations SET context=? WHERE id=?', (payload, identifier))
            return identifier, True
        except sqlite3.Error:
            raise OperationError('operation_store_unavailable') from None

    def transition(self, identifier, state, error_code=None):
        if state not in ('running', 'awaiting_approval', 'unknown'):
            raise ValueError('invalid operation transition')
        try:
            with self.db:
                row = self.db.execute('SELECT state FROM operations WHERE id=?', (identifier,)).fetchone()
                if not row or row['state'] not in ('queued', 'running', 'awaiting_approval'):
                    return False
                self.db.execute('UPDATE operations SET state=?,error_code=?,updated=? WHERE id=?',
                                (state, error_code, self.clock(), identifier))
            return True
        except sqlite3.Error:
            raise OperationError('operation_store_unavailable') from None

    def observe(self, identifier, state, sequence, progress=None):
        if state == 'progress':
            return self._progress(identifier, sequence, progress)
        if progress is not None:
            return False
        if (state, sequence) not in (('awaiting_approval', 1), ('running', 2)):
            return False
        try:
            with self.db:
                row = self.db.execute('SELECT state,event_seq FROM operations WHERE id=?', (identifier,)).fetchone()
                if not row or row['state'] not in ('running', 'awaiting_approval'):
                    return False
                if sequence <= row['event_seq']:
                    return sequence == row['event_seq'] and state == row['state']
                self.db.execute('UPDATE operations SET state=?,event_seq=?,updated=? WHERE id=?',
                                (state, sequence, self.clock(), identifier))
            return True
        except sqlite3.Error:
            raise OperationError('operation_store_unavailable') from None

    def _progress(self, identifier, sequence, progress):
        if type(sequence) is not int or not 3 <= sequence <= 100000 or not valid_progress(progress):
            return False
        payload = canonical(progress)
        size = len(payload.encode('utf-8'))
        if size > min(1024, self.max_result_bytes):
            return False
        try:
            with self.db:
                row = self.db.execute('SELECT state,event_seq,progress,progress_bytes FROM operations WHERE id=?', (identifier,)).fetchone()
                if not row or row['state'] not in ('running', 'awaiting_approval'):
                    return False
                if sequence <= row['event_seq']:
                    return sequence == row['event_seq'] and payload == row['progress']
                if row['progress']:
                    previous = json.loads(row['progress'])
                    if (progress['completed_count'] < previous['completed_count']
                            or progress['elapsed_ms'] < previous['elapsed_ms']):
                        return False
                total = self.db.execute('SELECT COALESCE(SUM(result_bytes + progress_bytes),0) FROM operations').fetchone()[0]
                if total - row['progress_bytes'] + size > self.max_bytes:
                    return False  # Optional observation must not change the execution outcome.
                self.db.execute("UPDATE operations SET state='running',event_seq=?,progress=?,progress_bytes=?,updated=? WHERE id=?",
                                (sequence, payload, size, self.clock(), identifier))
            return True
        except sqlite3.Error:
            raise OperationError('operation_store_unavailable') from None

    def finish(self, identifier, result):
        payload = canonical(result)
        size = len(payload.encode('utf-8'))
        try:
            with self.db:
                row = self.db.execute('SELECT state,progress_bytes FROM operations WHERE id=?', (identifier,)).fetchone()
                if not row or row['state'] not in ('running', 'awaiting_approval'):
                    return False
                total = self.db.execute('SELECT COALESCE(SUM(result_bytes + progress_bytes),0) FROM operations').fetchone()[0]
                if size > self.max_result_bytes or total - row['progress_bytes'] + size > self.max_bytes:
                    self.db.execute("UPDATE operations SET state='unknown', error_code='result_storage_quota', updated=? WHERE id=?",
                                    (self.clock(), identifier))
                else:
                    now = self.clock()
                    state = 'succeeded' if isinstance(result, dict) and result.get('success') is True else 'failed'
                    if isinstance(result, dict) and result.get('lifecycle_outcome') == 'unknown':
                        state = 'unknown'
                    if (isinstance(result, dict) and result.get('success') is False
                            and result.get('lifecycle_outcome') == 'rejected'
                            and result.get('rejection_reason') in ('mode_deny', 'user_declined', 'approval_stale')):
                        state = 'rejected'
                    self.db.execute('UPDATE operations SET state=?,result=?,result_bytes=?,updated=?,expires=?,error_code=NULL,progress=NULL,progress_bytes=0 WHERE id=?',
                                    (state, payload, size, now, now + self.result_ttl, identifier))
            return True
        except sqlite3.Error:
            raise OperationError('operation_store_unavailable') from None

    def get(self, channel, identifier):
        try:
            with self.db:
                self._expire()
                row = self.db.execute('SELECT * FROM operations WHERE channel=? AND id=?', (channel, identifier)).fetchone()
            if not row:
                raise OperationError('operation_not_found')
            return dict(row)
        except sqlite3.Error:
            raise OperationError('operation_store_unavailable') from None

    def snapshot(self, channel, identifier):
        row = self.get(channel, identifier)
        return {'operation_id': row['id'], 'request_id': row['request_key'], 'status': row['state'],
                'created_at': row['created'], 'updated_at': row['updated'], 'result_expires_at': row['expires'],
                'result_ttl_seconds': self.result_ttl, 'error': row['error_code'],
                'result': json.loads(row['result']) if row['result'] is not None else None,
                'progress': public_progress(json.loads(row['progress']), row['id'], row['event_seq']) if row['progress'] else None}
