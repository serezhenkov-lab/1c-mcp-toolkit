"""Assertions about safety boundaries; performance/availability findings stay visible."""
import hashlib
import json
from pathlib import Path

run=Path(__file__).resolve().parents[2]/'.local/lifecycle-limits'
def read(name):return json.loads((run/(name+'.json')).read_text(encoding='utf-8-sig'))
seeds={x['name']:x for x in read('seeds')}
bounds=read('bounds')
assert not bounds['error']
a,b=bounds['result_bounds']
assert (a['serialized_chars'],a['state'])==(1048576,'succeeded')
assert (b['serialized_chars'],b['state'],b['error'])==(1048577,'unknown','result_storage_quota')
assert [x['id'] for x in bounds['requests']]==[a['id'],b['id']]
for name in ('appendlocked','renameblocked'):
    assert 'operation_store_unavailable' in read(name)['error'] and not read(name)['healthy']
    r=read(name+'-recovered');assert not r['error'] and r['recovered']['state']=='unknown'
    lines=(run/('journal-'+name)/'operations.jsonl').read_text(encoding='utf-8-sig').splitlines()
    assert {json.loads(json.loads(x)['payload'])['id'] for x in lines}=={r['recovered']['id']}
assert 'operation_store_unavailable' in read('over64')['error']
assert (run/'journal-over64/operations.jsonl').stat().st_size==67108865
r=read('keys9999');assert not r['error'] and r['count']==10000
assert r['requests'][0]['id']==seeds['keys9999']['keep_id']
assert r['requests'][1]['id'] and 'operation_quota_exceeded' in r['requests'][2]['error']
r=read('active');assert not r['error'] and r['count']==100 and r['direct_state']=='queued'
assert r['public_status']['error']['code']=='operation_quota_exceeded'
summary={'result_boundaries':'passed','io_recovery':'unknown / same ID','active_status_blocked':True,'benchmarks':[]}
for name in ('keys1000','keys10000','near60','over60','near64'):
    r=read(name)
    assert r['requests'][0]['id']==seeds[name]['keep_id'],(name,r)
    if name=='keys10000':
        assert r['count']==10000
        assert all('operation_quota_exceeded' in x['error'] for x in r['requests'][1:])
    if name in ('over60','near64'):
        assert all('operation_quota_exceeded' in x['error'] for x in r['requests'][1:])
    assert not r['error'] and r['healthy'],(name,r)
    assert all(not x['error'] for x in r['rounds']),name
    samples=read(name+'-http')
    summary['benchmarks'].append(dict(name=name,seed_count=seeds[name]['count'],seed_bytes=seeds[name]['bytes'],
        count=r['count'],bytes=r['bytes'],startup_ms=r['startup_ms'],compaction_ms=[x['ms'] for x in r['rounds']],
        admission_ms=[x['ms'] for x in r['requests'][1:]],http_samples=len(samples),
        http_timeouts=sum(x.get('error','').endswith('Timeout') for x in samples),
        http_503=sum(x.get('http')==503 for x in samples),
        probe_parse_errors=sum(x.get('error')=='AttributeError' for x in samples),
        status_responses=[{k:x.get(k) for k in ('phase','http','status','code','error','elapsed_ms')} for x in samples if x['endpoint']=='status']))
summary['runtime_sha256']=hashlib.sha256((run.parents[1]/'1c/MCPToolkit/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl').read_bytes()).hexdigest()
(run/'checked-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
