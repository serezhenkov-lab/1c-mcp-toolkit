"""Expire one isolated result deterministically, then verify only public responses."""
import json
import sqlite3
import sys
import time
import uuid
import os
from pathlib import Path
import httpx

route=sys.argv[1]
run=Path(os.environ.get('TOOLKIT_QUEUE1_ROOT',str(Path(__file__).resolve().parents[2]/'.local/queue1-acceptance')))/route
port={'http':17665,'file':17666,'embedded':17667}[route]
c=httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=10)
events=[]
def call(a):
    r=c.post('/api/test_session?channel=queue1',json=a).json()
    events.append(dict(args=a,result=r))
    (run/'retention.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
    return r
a=dict(request_id='ttl-'+uuid.uuid4().hex,action='status',params={})
r=call(a)
identifier=r['operation_id']
read=dict(request_id='ttl-read-'+uuid.uuid4().hex,action='status',params={'operation_id':identifier})
for _ in range(600):
    if r['status'] in ('succeeded','failed'):break
    time.sleep(.2);r=call(read)['data']['operation']
assert r['status'] in ('succeeded','failed'),r
if route=='embedded':
    pending=run/'control.next'
    pending.write_text(json.dumps(dict(seq=str(uuid.uuid4()),expire=identifier)),encoding='utf-8')
    for attempt in range(50):
        try:
            pending.replace(run/'control.json');break
        except PermissionError:
            if attempt==49:raise
            time.sleep(.05)
    time.sleep(1.3)
else:
    with sqlite3.connect(run/'journal/operations.sqlite3') as db:
        assert db.execute('UPDATE operations SET expires=1 WHERE id=?',(identifier,)).rowcount==1
expired=call(a)
assert expired['operation_id']==identifier and expired['error']['code']=='result_expired',expired
assert call(read)['data']['operation']['error']['code']=='result_expired'
assert call({**a,'timeout_ms':1})['error']['code']=='request_conflict'
print(route+': result_expired, same ID, status and conflict after TTL passed')
