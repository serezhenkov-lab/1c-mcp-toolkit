"""Post-restart invariants, using only the disposable queue1 database."""
import json
from pathlib import Path
import time
import uuid
import httpx

run = Path(__file__).resolve().parents[2] / '.local/queue1'
client = httpx.Client(base_url='http://127.0.0.1:17655', timeout=10)
events = []


def call(tool, args):
    result = client.post('/api/' + tool + '?channel=queue1', json=args).json()
    events.append(dict(tool=tool, args=args, result=result))
    (run / 'restart-probe.json').write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def complete(tool, args):
    result = call(tool, args)
    identifier = result.get('operation_id')
    for _ in range(80):
        if result['status'] not in ('queued', 'running', 'awaiting_approval'):
            return result
        time.sleep(.25)
        result = call('test_session', dict(request_id=str(uuid.uuid4()), action='status',
                                          params={'operation_id': identifier}))['data']['operation']
    raise AssertionError(result)


old = json.loads((run / 'session.json').read_text(encoding='utf-8'))
status = complete('test_session', dict(request_id='restart-check-status', action='status', params={}))
assert status['data']['manager_mode'] and status['data']['state'] == 'disconnected', status
denied = complete('test_session', dict(request_id='restart-denied-start', action='start', params={'profile_id': 'queue1'}))
assert denied['error']['code'] == 'permission_denied', denied
stale = complete('test_inspect', dict(request_id='restart-old-session', session_id=old['session_id'], action='windows', params={}))
assert stale['error']['code'] == 'session_invalid', stale
# Explicit test setup through the existing client executor; not a test_* permission bypass.
setup = call('execute_code', {'code': 'РежимПодтвержденияОпасныхОпераций = "session_allow"; Результат = РежимПодтвержденияОпасныхОпераций;',
                             'execution_context': 'client'})
assert setup['success'], setup
blocked = complete('test_session', dict(request_id='restart-no-second-client', action='start', params={'profile_id': 'queue1'}))
assert blocked['error']['code'] == 'client_already_exists', blocked
attached = complete('test_session', dict(request_id='restart-attach', action='attach', params={'profile_id': 'queue1'}))
assert attached['status'] == 'succeeded' and attached['session_id'] != old['session_id'], attached
assert attached['data']['owned'] is False, attached
prior = json.loads((run / 'public-probe.json').read_text(encoding='utf-8'))
window = next(e['result']['data']['windows'][0]['window_id'] for e in prior
              if e.get('tool') == 'test_inspect' and e['result']['status'] == 'succeeded')
stale_window = complete('test_inspect', dict(request_id='restart-old-window', session_id=attached['session_id'], action='tree',
                                          window={'id': window}, params={}))
assert stale_window['error']['code'] == 'stale_target', stale_window
not_owned = complete('test_session', dict(request_id='restart-no-stop-unowned', session_id=attached['session_id'], action='stop', params={}))
assert not_owned['error']['code'] == 'client_not_owned', not_owned
print('restart invariants passed')
