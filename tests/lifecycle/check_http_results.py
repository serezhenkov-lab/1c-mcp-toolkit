"""Actual 8.5 evidence: HTTP availability, interleaved writes and initialization."""
from pathlib import Path
import json

root=Path(__file__).resolve().parents[2]
run=root/'.local/lifecycle-http/final'
def read(name):return json.loads((run/(name+'.json')).read_text(encoding='utf-8-sig'))
seeds={x['name']:x for x in read('seeds')}
summary={'cases':[]}
for name in ('keys1000','keys10000','near64','initializing','mutation'):
    report=read(name);samples=read(name+'-http');native=read(name+'-native')
    assert not report['error'] and report['healthy'] and not report['initializing'],name
    assert report['rounds'] and all(x['ms']>0 and not x['error'] for x in report['rounds']),name
    assert all(x.get('http')==200 and 'error' not in x for x in samples),(name,[x for x in samples if x.get('http')!=200 or 'error' in x])
    during=[x for x in samples if x['phase'].startswith('round-')]
    assert any(x['endpoint']=='health' for x in during) and any(x['endpoint']=='status' for x in during)
    status=[x for x in samples if x['endpoint']=='status']
    if name!='initializing':assert all(x['status']=='succeeded' for x in status),name
    else:
        assert report['status_before_ready']['error']['code']=='operation_store_unavailable'
        assert any(x['status']=='failed' and x['code']=='operation_store_unavailable' for x in status)
        assert status[-1]['status']=='succeeded' and native['target_status']=='unknown'
    assert native['status']=='succeeded' and native['target_id']==native['operation_id']==seeds[name]['keep_id']
    expected=seeds[name]['count']+(3 if name=='mutation' else 2 if name=='keys1000' else 0)
    assert report['count']==expected,(name,report['count'],expected)
    assert not list((run/('journal-'+name)).glob('*.next')) and not list((run/('journal-'+name)).glob('*.commit'))
    summary['cases'].append(dict(name=name,records=report['count'],startup_ms=report['startup_ms'],
        compaction_ms=[x['ms'] for x in report['rounds']],http_samples=len(samples),http_timeouts=0,http_503=0,
        max_http_ms=max(x['elapsed_ms'] for x in samples),max_status_ms=max(x['elapsed_ms'] for x in status),native_status=native['status']))
mutation=read('mutation');restored=read('mutation-recovered')
assert mutation['interleavings']==['write','verify','verify_again','commit']
assert not restored['error'] and restored['count']==mutation['count']
rows={}
for line in (run/'journal-mutation/operations.jsonl').read_text(encoding='utf-8-sig').splitlines():
    row=json.loads(json.loads(line)['payload']);rows[row['id']]=row
row=rows[mutation['mutation_id']]
assert row['state']=='succeeded' and row['event_seq']==2 and row['result']['data']['data']['text']=='INTERLEAVED_RESULT_PRESERVED'
assert row['fingerprint']==mutation['mutation_record']['fingerprint']
summary['interleaved_writes']='admission, awaiting_approval, running, result preserved after restart'
(run.parent/'checked-http.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
