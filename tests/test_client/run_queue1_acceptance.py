"""Same public lifecycle/restart assertions on three real 8.5 manager routes."""
import json
import sys
import time
import uuid
import os
from pathlib import Path
import httpx

route = sys.argv[1]
root = Path(__file__).resolve().parents[2]
run = Path(os.environ.get('TOOLKIT_QUEUE1_ROOT', str(root / '.local/queue1-acceptance'))) / route
port = {'http':17665, 'file':17666, 'embedded':17667}[route]
c = httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=15)
events, checks = [], []
prefix=uuid.uuid4().hex[:8]+'-'
assert not (run/'acceptance.json').exists(), 'Preserve evidence'

def save():
    (run/'acceptance.json').write_text(json.dumps(dict(route=route, checks=checks, events=events), ensure_ascii=False, indent=2), encoding='utf-8')

def check(name, condition, evidence=None, fatal=True):
    checks.append(dict(name=name, ok=bool(condition), evidence=evidence)); save()
    if fatal: assert condition, (name,evidence)

def args(name, **kw):
    return dict(request_id=prefix+name, **kw)

def call(tool, a, channel='queue1'):
    start=time.monotonic()
    r=c.post('/api/'+tool, params={'channel':channel},json=a,timeout=90 if tool=='restart_1c_session' else 15)
    value=r.json()
    events.append(dict(tool=tool,args=a,channel=channel,http=r.status_code,ms=round((time.monotonic()-start)*1000,2),result=value));save()
    return value

def poll(identifier, key=None):
    r=call('test_session',args(key or str(uuid.uuid4()),action='status',params={'operation_id':identifier}))
    return r.get('data',{}).get('operation',r)

def complete(tool,a):
    r=call(tool,a)
    for _ in range(160):
        if r['status'] not in ('queued','running','awaiting_approval'):return r
        time.sleep(.25);r=poll(r['operation_id'])
    raise AssertionError(r)

def control(mode):
    (run/'control.json').write_text(json.dumps(dict(seq=str(uuid.uuid4()),mode=mode)),encoding='utf-8');time.sleep(1.3)

for _ in range(60):
    try:
        if (run/'ready.txt').exists() and c.get('/health',timeout=1).status_code==200:
            readiness=complete('test_session',args('readiness-'+str(uuid.uuid4()),action='status',params={}))
            if readiness.get('data',{}).get('manager_mode'):break
    except httpx.TransportError:pass
    time.sleep(1)
else:raise AssertionError('Stand not ready')
control('session_allow')
start_args=args('start',action='start',params={'profile_id':'queue1'})
s=complete('test_session',start_args)
check('start',s['status']=='succeeded',s)
sid=s['session_id']
receipt=json.loads((run/'receipt.json').read_text(encoding='utf-8-sig'))
repeat=call('test_session',{**start_args,'timeout_ms':120000})
check('defaults_same_id',repeat['operation_id']==s['operation_id'])
conflict=call('test_session',{**start_args,'timeout_ms':1})
check('request_conflict',conflict['error']['code']=='request_conflict')
w=complete('test_inspect',args('windows',session_id=sid,action='windows',params={}))
window={'id':next(x['window_id'] for x in w['data']['windows'] if x['active'])}
opened=complete('test_open',args('open-form',session_id=sid,window=window,params={'link':'e1cib/list/Документ.T43_Required'}))
check('form_opened',opened['status']=='succeeded',opened)
w=complete('test_inspect',args('form-windows',session_id=sid,action='windows',params={}))
window={'id':next(x['window_id'] for x in w['data']['windows'] if x['active'])}
tree=complete('test_inspect',args('tree',session_id=sid,window=window,action='tree',params={}))
def ids(value):
    if isinstance(value,dict):
        if value.get('element_id'):yield value['element_id']
        for v in value.values():yield from ids(v)
    elif isinstance(value,list):
        for v in value:yield from ids(v)
elements=list(ids(tree.get('data',{})))
check('element_id_obtained',bool(elements),tree)
# Discarding a completed response at the caller must not cause a new operation.
action=args('lost-response',session_id=sid,window=window,action='activate_window',params={})
first=complete('test_action',action);second=call('test_action',action)
check('completed_response_replay',first['status']=='succeeded' and second['operation_id']==first['operation_id'] and second['status']=='succeeded')
e=args('late',session_id=sid,window=window,timeout_ms=5000,params={'condition':{'property':'title','operator':'equals','value':'Never Queue1 Title'}})
r=call('test_expect',e);time.sleep(1)
pending=poll(r['operation_id'],'same-status-key')
check('status_during_wait',pending['status']=='running',pending)
check('repeat_during_wait',call('test_expect',e)['operation_id']==r['operation_id'])
time.sleep(5)
late=poll(r['operation_id'],'same-status-key')
for _ in range(80):
    if late['status'] not in ('queued','running','awaiting_approval'):break
    time.sleep(.25)
    late=poll(r['operation_id'],'same-status-key')
check('same_status_key_refreshes_late_result',late['error']['code']=='expectation_timeout',late)
foreign=call('test_session',args('foreign',action='status',params={'operation_id':r['operation_id']}),'foreign')
check('foreign_channel_denied',foreign['error']['code']=='permission_denied')
e=args('interrupted',session_id=sid,window=window,timeout_ms=60000,params={'condition':{'property':'title','operator':'equals','value':'Never Queue1 Title'}})
r=call('test_expect',e);time.sleep(1)
check('running_before_restart',poll(r['operation_id'])['status']=='running')
(run/'control.json').unlink()
restart=call('restart_1c_session',{})
check('public_restart_accepted',restart.get('success'),restart)
for _ in range(60):
    time.sleep(1)
    try:
        state=complete('test_session',args('after-restart-'+str(uuid.uuid4()),action='status',params={}))
        if state.get('data',{}).get('manager_mode') and state['data']['state']=='disconnected':break
    except httpx.TransportError:pass
else:raise AssertionError('Manager restart not ready')
check('manager_role_after_restart',True,state)
interrupted=poll(r['operation_id'])
check('interrupted_unknown',interrupted['status']=='unknown',interrupted,fatal=False)
repeated=call('test_expect',e)
check('unknown_no_replay',repeated['operation_id']==r['operation_id'] and repeated['status']=='unknown',repeated,fatal=False)
denied=complete('test_session',args('restart-denied',action='start',params={'profile_id':'queue1'}))
check('session_permission_reset',denied['error']['code']=='permission_denied',denied)
old=complete('test_inspect',args('old-session',session_id=sid,action='windows',params={}))
check('old_session_rejected',old['error']['code']=='session_invalid',old)
control('session_allow')
blocked=complete('test_session',args('no-second',action='start',params={'profile_id':'queue1'}))
check('second_client_refused',blocked['error']['code']=='client_already_exists',blocked)
check('receipt_unchanged',json.loads((run/'receipt.json').read_text(encoding='utf-8-sig'))==receipt)
attached=complete('test_session',args('attach',action='attach',params={'profile_id':'queue1'}))
check('new_session_unowned',attached['status']=='succeeded' and attached['session_id']!=sid and attached['data']['owned'] is False,attached)
new_sid=attached['session_id']
oldw=complete('test_inspect',args('old-window',session_id=new_sid,window=window,action='tree',params={}))
check('old_window_rejected',oldw['error']['code']=='stale_target',oldw)
neww=complete('test_inspect',args('new-windows',session_id=new_sid,action='windows',params={}))
new_window={'id':next(x['window_id'] for x in neww['data']['windows'] if x['active'])}
olde=complete('test_inspect',args('old-element',session_id=new_sid,window=new_window,action='tree',element={'id':elements[0]},params={}))
check('old_element_rejected',olde['error']['code']=='stale_target',olde)
stop=complete('test_session',args('unowned-stop',session_id=new_sid,action='stop',params={}))
check('unowned_stop_denied',stop['error']['code']=='client_not_owned',stop)
print(json.dumps(dict(route=route,passed=sum(x['ok'] for x in checks),failed=sum(not x['ok'] for x in checks)),ensure_ascii=False))
if '--require-interrupted' in sys.argv:
    assert all(x['ok'] for x in checks), checks
