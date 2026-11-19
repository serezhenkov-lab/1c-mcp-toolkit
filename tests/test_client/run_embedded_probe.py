"""Runtime proof through embedded REST, including the normal public restart path."""
import os
import json
import sys
from pathlib import Path
import time
import uuid
import httpx

run = Path(__file__).resolve().parents[2] / '.local/embedded-lifecycle'
run = Path(os.environ.get('TOOLKIT_STAND_DIR', str(run)))
c = httpx.Client(base_url=os.environ.get('TOOLKIT_STAND_URL','http://127.0.0.1:17657'), timeout=20)
events = []
prefix = uuid.uuid4().hex[:8] + '-'

def call(tool, args, channel='queue1'):
    r = c.post('/api/' + tool, params={'channel': channel}, json=args)
    result = r.json()
    events.append(dict(tool=tool, args=args, channel=channel, result=result, cache_control=r.headers.get('cache-control')))
    (run / 'embedded-probe.json').write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')
    if tool.startswith('test_'):
        assert r.headers.get('cache-control') == 'no-store'
    return result

def args(name, **kw):
    return dict(request_id=prefix+name, **kw)

def poll(identifier):
    return call('test_session', args(str(uuid.uuid4()), action='status', params={'operation_id': identifier}))['data']['operation']

def complete(tool, arguments, approval=False):
    result = call(tool, arguments)
    seen = set()
    compacted = False
    for _ in range(100):
        seen.add(result['status'])
        if result['status']=='awaiting_approval' and '--compact-while-awaiting' in sys.argv and not compacted:
            control(compact=True)
            compacted = True
        if result['status'] not in ('queued', 'running', 'awaiting_approval'):
            if approval:
                assert 'awaiting_approval' in seen, seen
            return result
        time.sleep(.25)
        result = poll(result['operation_id'])
    raise AssertionError(result)

def control(**kw):
    (run / 'control.json').write_text(json.dumps(dict(seq=str(uuid.uuid4()), **kw)), encoding='utf-8')
    time.sleep(1.3)

assert json.loads((run/'lock-probe.json').read_text(encoding='utf-8-sig'))['second_writer_denied']
cached = call('test_session', dict(request_id='public-start', action='start', params={'profile_id':'queue1'}))
assert cached['status'] == 'succeeded'
denied = complete('test_session', args('denied-start', action='start', params={'profile_id':'queue1'}))
assert denied['error']['code'] == 'permission_denied'
control(mode='session_allow')
attached = complete('test_session', args('attach', action='attach', params={'profile_id':'queue1'}))
assert attached['status'] == 'succeeded', attached
sid = attached['session_id']
windows = complete('test_inspect', args('windows', session_id=sid, action='windows', params={}))
window = {'id':next(w['window_id'] for w in windows['data']['windows'] if w['active'])}
control(mode='ask')
if (run/'allow.txt').exists(): (run/'allow.txt').unlink()
denied = complete('test_action', args('reject', session_id=sid, action='activate_window', window=window, params={}), True)
assert denied['error']['code'] == 'permission_denied' and denied['execution']=='not_started'
denied = complete('test_session', args('detach-reject', session_id=sid, action='detach', params={}), True)
assert denied['error']['code'] == 'permission_denied'
(run/'allow.txt').write_text('test fixture approval', encoding='utf-8')
allowed_args = args('allow', session_id=sid, action='activate_window', window=window, params={})
allowed = complete('test_action', allowed_args, True)
assert allowed['status']=='succeeded' and allowed['execution']=='invoked'
assert call('test_action',allowed_args)['operation_id']==allowed['operation_id']
foreign = call('test_session',args('foreign', action='status', params={'operation_id':allowed['operation_id']}),'foreign')
assert foreign['error']['code']=='permission_denied'
for bad in [dict(request_id=prefix+'bad',action='STATUS',params={}), dict(request_id=prefix+'bad',action='status',params={},extra=True)]:
    assert call('test_session',bad)['error']['code']=='invalid_params'
empty = call('test_inspect',args('empty-selector',session_id=sid,action='element',window=window,element={'selector':{}},params={}))
assert empty['error']['code']=='invalid_params'
if '--skip-anon' not in sys.argv:
    control(anon=True)
    assert call('test_action',allowed_args)['error']['code']=='operation_result_policy_not_ready'
control(anon=False,mode='session_allow')
status_args=args('ttl-status',action='status',params={'operation_id':allowed['operation_id']})
assert call('test_session',status_args)['data']['operation']['status']=='succeeded'
control(expire=allowed['operation_id'])
expired=call('test_action',allowed_args)
assert expired['error']['code']=='result_expired' and expired['operation_id']==allowed['operation_id']
assert call('test_session',status_args)['data']['operation']['error']['code']=='result_expired'
assert call('test_action',{**allowed_args,'timeout_ms':1})['error']['code']=='request_conflict'
expect_args=args('restart-expect',session_id=sid,window=window,timeout_ms=60000,params={'condition':{'property':'title','operator':'equals','value':'never-this-title'}})
waiting=call('test_expect',expect_args)
time.sleep(1)
assert poll(waiting['operation_id'])['status']=='running'
if '--compact-while-awaiting' in sys.argv:
    control(compact=True)
    assert poll(waiting['operation_id'])['status']=='running'
(run/'control.json').unlink()
restarted=call('restart_1c_session',{})
assert restarted['success'], restarted
for _ in range(45):
    time.sleep(1)
    try:
        result=poll(waiting['operation_id'])
        if result['status']=='unknown': break
    except httpx.TransportError: pass
else: raise AssertionError('embedded restart did not recover')
assert call('test_expect',expect_args)['status']=='unknown'
denied=complete('test_session',args('restart-deny',action='start',params={'profile_id':'queue1'}))
assert denied['error']['code']=='permission_denied'
status=complete('test_session',args('restart-status',action='status',params={}))
assert status['data']['manager_mode'] and status['data']['state']=='disconnected', status
print('embedded approvals, expiry, isolation, validation and public restart passed; anonymity guard ' + ('skipped' if '--skip-anon' in sys.argv else 'checked'))
