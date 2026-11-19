"""Prepare/check a process-kill recovery and nested TTL without replaying a UI call."""
import json
from pathlib import Path
import sys
import time
import uuid
import httpx

run=Path(__file__).resolve().parents[2]/'.local/embedded-lifecycle'
c=httpx.Client(base_url='http://127.0.0.1:17657',timeout=10)
events=[]
def call(tool,args):
    r=c.post('/api/'+tool+'?channel=queue1',json=args).json()
    events.append(dict(tool=tool,args=args,result=r))
    (run/('recovery-'+sys.argv[1]+'.json')).write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
    return r
def args(**kw):return dict(request_id=str(uuid.uuid4()),**kw)
def complete(tool,a):
    r=call(tool,a)
    for _ in range(100):
        if r['status'] not in ('queued','running','awaiting_approval'):return r
        time.sleep(.2)
        r=call('test_session',args(action='status',params={'operation_id':r['operation_id']}))['data']['operation']
    raise AssertionError(r)
if sys.argv[1]=='prepare':
    (run/'control.json').write_text(json.dumps(dict(mode='session_allow',seq=str(uuid.uuid4()))),encoding='utf-8');time.sleep(1.3)
    attached=complete('test_session',args(action='attach',params={'profile_id':'queue1'}))
    assert attached['status']=='succeeded',attached
    sid=attached['session_id']
    w=complete('test_inspect',args(session_id=sid,action='windows',params={}))
    win=next(x['window_id'] for x in w['data']['windows'] if x['active'])
    a=args(session_id=sid,window={'id':win},timeout_ms=60000,params={'condition':{'property':'title','operator':'equals','value':'never'}})
    r=call('test_expect',a);time.sleep(.5)
    assert call('test_session',args(action='status',params={'operation_id':r['operation_id']}))['data']['operation']['status']=='running'
    (run/'recovery-request.json').write_text(json.dumps(dict(args=a,operation_id=r['operation_id'])),encoding='utf-8')
    (run/'control.json').unlink()
else:
    old=json.loads((run/'recovery-request.json').read_text(encoding='utf-8'))
    r=call('test_expect',old['args'])
    assert r['operation_id']==old['operation_id'] and r['status']=='unknown',r
    a=complete('test_session',args(action='status',params={}))
    b=call('test_session',args(action='status',params={'operation_id':a['operation_id']}))
    ca=args(action='status',params={'operation_id':b['operation_id']})
    call('test_session',ca)
    (run/'control.json').write_text(json.dumps(dict(expire=a['operation_id'],seq=str(uuid.uuid4()))),encoding='utf-8');time.sleep(1.3)
    r=call('test_session',ca)
    assert r['data']['operation']['data']['operation']['error']['code']=='result_expired',r
    print('process-kill unknown/no replay and nested cached TTL passed')
