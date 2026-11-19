"""Final EPF: approval expiry and exact resolver diagnostics on the real client."""
import json
from pathlib import Path
import time
import uuid
import httpx

run = Path(__file__).resolve().parents[2] / '.local/queue1-file'
c = httpx.Client(base_url='http://127.0.0.1:17656', timeout=15)
events = []
prefix = uuid.uuid4().hex[:8] + '-'


def call(tool, args):
    if 'request_id' in args:
        args = {**args, 'request_id': prefix + args['request_id']}
    result = c.post('/api/' + tool + '?channel=queue1', json=args).json()
    events.append(dict(tool=tool, args=args, result=result))
    (run / 'final-probe.json').write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def complete(tool, args):
    result = call(tool, args)
    identifier = result.get('operation_id')
    for _ in range(100):
        if result['status'] not in ('queued', 'running', 'awaiting_approval'):
            return result
        time.sleep(.2)
        result = call('test_session', dict(request_id=str(uuid.uuid4()), action='status',
                                          params={'operation_id': identifier}))['data']['operation']
    raise AssertionError(result)


def mode(value):
    result = call('execute_code', {'code': 'РежимПодтвержденияОпасныхОпераций = "' + value + '"; Результат = РежимПодтвержденияОпасныхОпераций;',
                                   'execution_context': 'client'})
    assert result['success'], result


mode('session_allow')
attached = complete('test_session', dict(request_id='final-attach', action='attach', params={'profile_id': 'queue1'}))
assert attached['status'] == 'succeeded', attached
sid = attached['session_id']
assert attached['data']['diagnostics']['process_state'] == 'Alive', attached
windows = complete('test_inspect', dict(request_id='final-windows', session_id=sid, action='windows', params={}))
window = {'id': next(w['window_id'] for w in windows['data']['windows'] if w['active'])}
missing = complete('test_input', dict(request_id='final-missing', session_id=sid, action='text', window=window,
                                      element={'selector': {'name': 'DefinitelyMissing'}}, params={'text': 'not-written'}))
assert missing['error']['code'] == 'element_not_found', missing
assert missing['data']['resolution']['exact_matches'] == 0, missing
assert len(missing['data']['resolution']['candidates']) <= 20, missing
ambiguous = complete('test_action', dict(request_id='final-ambiguous', session_id=sid, action='click', window=window,
                                        element={'selector': {'type': 'button'}}, params={}))
assert ambiguous['error']['code'] == 'ambiguous_target', ambiguous
assert ambiguous['data']['resolution']['exact_matches'] > 1 and ambiguous['execution'] == 'not_started', ambiguous
mode('ask')
started = time.monotonic()
expired = complete('test_session', dict(request_id='final-expired-approval', session_id=sid, action='detach', timeout_ms=500, params={}))
elapsed = time.monotonic() - started
assert expired['error']['code'] == 'permission_denied' and expired['execution'] == 'not_started', expired
assert elapsed < 3, elapsed  # fixture answer arrives at 3 seconds; owner must finish earlier
time.sleep(3)  # let stale fixture callback run; it must not grant permission
state = complete('test_session', dict(request_id='final-after-expiry', session_id=sid, action='status', params={}))
assert state['data']['state'] == 'ready', state
permission = call('execute_code', {'code': 'Результат = РежимПодтвержденияОпасныхОпераций;', 'execution_context': 'client'})
assert 'ask' in permission['data'], permission
print('final EPF: exact candidates, Alive diagnostics and approval expiry passed')
