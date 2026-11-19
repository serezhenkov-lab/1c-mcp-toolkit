"""Recover the already committed file-bridge operation; never resend a new write."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[2]
run = root / '.local/queue1-finish/file'
old = json.loads((run / 'results.json').read_text(encoding='utf-8'))
import time
(run / 'results.json').rename(run / ('before-recovery-' + str(time.time_ns()) + '.json'))
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('try:\n    barrier =')], 'queue1_runner_helpers', 'exec'))
marker, checks, events = old['marker'], old['checks'], old['events']
write = next(e for e in events if e['tool'] == 'test_action' and e['args']['request_id'].startswith('unknown-'))
try:
    committed = traces()
    check('commit_trace_before_recovery', len(committed) == 2 and committed[-1]['stage'] == 'committed', committed)
    proxy = start_proxy()
    manager = start_manager()
    ready()
    for n in range(2):
        replay = call('test_action', write['args'])
        check('replay_unknown_' + str(n), replay.get('operation_id') == write['result']['operation_id'] and replay.get('status') == 'unknown', replay)
    rows = query()
    check('no_second_document_or_handler', len(rows) == 1 and rows[0]['reference'] == committed[-1]['reference'] and traces() == committed, {'rows': rows, 'trace': traces()})
    print(json.dumps({'route': 'file', 'passed': len(checks), 'resumed_existing_write': True}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup-recovery.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
