"""Exercise real approval callbacks in the disposable file-bridge fixture."""
import json
from pathlib import Path
import time
import uuid
import httpx

run = Path(__file__).resolve().parents[2] / '.local/queue1-file'
c = httpx.Client(base_url='http://127.0.0.1:17656', timeout=15)
events = []
run_id = uuid.uuid4().hex[:8] + '-'


def call(tool, args):
    if 'request_id' in args:
        args = {**args, 'request_id': run_id + args['request_id']}
    result = c.post('/api/' + tool + '?channel=queue1', json=args).json()
    events.append(dict(tool=tool, args=args, result=result))
    (run / 'approval-probe.json').write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def complete(tool, args, approval=False):
    result = call(tool, args)
    identifier = result.get('operation_id')
    seen = set()
    for _ in range(120):
        seen.add(result['status'])
        if result['status'] not in ('queued', 'running', 'awaiting_approval'):
            if approval:
                assert 'awaiting_approval' in seen, seen
            return result
        time.sleep(.25)
        result = call('test_session', dict(request_id=str(uuid.uuid4()), action='status',
                                          params={'operation_id': identifier}))['data']['operation']
    raise AssertionError(result)


sid = json.loads((run / 'session.json').read_text(encoding='utf-8'))['session_id']
windows = complete('test_inspect', dict(request_id='approval-windows', action='windows', session_id=sid, params={}))
window = {'id': next(w['window_id'] for w in windows['data']['windows'] if w['active'])}
setup = call('execute_code', {'code': 'РежимПодтвержденияОпасныхОпераций = "ask"; Результат = РежимПодтвержденияОпасныхОпераций;',
                             'execution_context': 'client'})
assert setup['success'], setup
denied = complete('test_action', dict(request_id='approval-reject', action='activate_window', session_id=sid,
                                     window=window, params={}), approval=True)
assert denied['error']['code'] == 'permission_denied' and denied['execution'] == 'not_started', denied
session_denied = complete('test_session', dict(request_id='approval-session-reject', action='detach', session_id=sid, params={}), approval=True)
assert session_denied['error']['code'] == 'permission_denied', session_denied
(run / 'allow.txt').write_text('fixture explicitly accepts next dialog', encoding='utf-8')
allowed = complete('test_action', dict(request_id='approval-allow', action='activate_window', session_id=sid,
                                      window=window, params={}), approval=True)
assert allowed['status'] == 'succeeded' and allowed['execution'] == 'invoked', allowed
repeat = call('test_action', dict(request_id='approval-allow', action='activate_window', session_id=sid, window=window, params={}))
assert repeat['operation_id'] == allowed['operation_id'] and repeat['status'] == 'succeeded', repeat
print('real file-bridge approval callbacks passed')
