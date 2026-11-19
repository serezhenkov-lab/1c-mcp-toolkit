"""Verify final stand evidence and keep one durable row for the interrupted key."""
import ast
import hashlib
import json
from pathlib import Path
import sqlite3

root=Path(__file__).resolve().parents[2]
run=root/'.local/queue1-file-restart'
folder=run/'file'
report=json.loads((folder/'acceptance.json').read_text(encoding='utf-8'))
assert len(report['checks'])==23 and all(x['ok'] for x in report['checks'])
restart=next(x for x in report['events'] if x['tool']=='restart_1c_session')
assert restart['ms']<60000
request=next(x for x in report['events'] if x['tool']=='test_expect' and x['args']['request_id'].endswith('-interrupted'))
with sqlite3.connect((folder/'journal/operations.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    rows=[dict(row) for row in db.execute('SELECT id,request_key,fingerprint,tool,state,event_seq FROM operations WHERE request_key=?',(request['args']['request_id'],))]
assert len(rows)==1 and rows[0]['id']==request['result']['operation_id'] and rows[0]['state']=='unknown'
assert not list((folder/'bridge').rglob('*.running'))
retention=json.loads((folder/'retention.json').read_text(encoding='utf-8'))
assert retention[-1]['result']['error']['code']=='request_conflict'
assert retention[-2]['result']['data']['operation']['error']['code']=='result_expired'
assert retention[-3]['result']['error']['code']=='result_expired'
cleanup=json.loads((run/'cleanup-final.json').read_text(encoding='utf-8-sig'))
assert not cleanup['remaining'] and cleanup['platform']=='8.5.1.1529'
for name,count in [('unit-file-final2.log',25),('unit-http.log',3),('unit-lifecycle.log',19),('unit-public.log',10)]:
    log=(run/name).read_text(encoding='utf-8-sig')
    assert f'Ran {count} tests' in log and '\nOK' in log,name
files=['onec_mcp_toolkit_proxy/command_queue.py','onec_mcp_toolkit_proxy/file_transport.py','tests/test_file_transport.py']
hashes={}
for name in files:
    path=root/name;ast.parse(path.read_text(encoding='utf-8-sig'))
    hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
summary=dict(runtime_checks=23,python_tests=57,restart_ms=restart['ms'],interrupted=rows,
             production_hashes=hashes,remaining_processes=0,platform=cleanup['platform'])
(run/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
