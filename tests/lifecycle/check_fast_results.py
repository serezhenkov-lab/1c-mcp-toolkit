"""Check fixed lifecycle boundaries against real 8.5 reports; retain latency data."""
from pathlib import Path
import json

root=Path(__file__).resolve().parents[2]
run=root/'.local/lifecycle-fast/limits'
old=root/'.local/lifecycle-limits'
def read(name,folder=run):return json.loads((folder/(name+'.json')).read_text(encoding='utf-8-sig'))

active=read('active')
assert not active['error'] and active['count']==100
assert 'operation_quota_exceeded' in active['requests'][0]['error']
assert active['public_status']['data']['operation']['status']=='queued'
assert active['public_status_refreshed']['data']['operation']['status']=='awaiting_approval'
assert active['public_status']['operation_id']==active['public_status_refreshed']['operation_id']
assert active['public_status_conflict']['error']['code']=='request_conflict'
assert active['public_status_foreign']['error']['code']=='permission_denied'
bounds=read('bounds');a,b=bounds['result_bounds']
assert not bounds['error'] and (a['serialized_chars'],a['state'])==(1048576,'succeeded')
assert (b['serialized_chars'],b['state'],b['error'])==(1048577,'unknown','result_storage_quota')
assert [x['id'] for x in bounds['requests']]==[a['id'],b['id']]
for name in ('appendlocked','renameblocked'):
    assert 'operation_store_unavailable' in read(name)['error'] and not read(name)['healthy']
    value=read(name+'-recovered');assert not value['error'] and value['recovered']['state']=='unknown'
    ids={json.loads(json.loads(x)['payload'])['id'] for x in (run/('journal-'+name)/'operations.jsonl').read_text(encoding='utf-8-sig').splitlines()}
    assert ids=={value['recovered']['id']}
assert 'operation_store_unavailable' in read('over64')['error']
assert (run/'journal-over64/operations.jsonl').stat().st_size==67108865
r=read('keys9999');assert not r['error'] and r['count']==10000
assert r['requests'][1]['id'] and 'operation_quota_exceeded' in r['requests'][2]['error']
seeds={x['name']:x for x in read('seeds')}
summary=dict(active_status='queued -> awaiting_approval; no extra record',benchmarks=[])
for name in ('keys1000','keys10000','near60','over60','near64'):
    r=read(name);before=read(name,old);native=read(name+'-native')
    assert not r['error'] and r['healthy'] and all(not x['error'] for x in r['rounds'])
    assert r['requests'][0]['id']==seeds[name]['keep_id']
    expected=seeds[name]['count']+(2 if name in ('keys1000','near60') else 0)
    assert r['count']==expected,(name,r['count'])
    if name in ('keys10000','over60','near64'):
        assert all('operation_quota_exceeded' in x['error'] for x in r['requests'][1:])
    assert native['status']=='succeeded' and native['target_id']==native['operation_id']==seeds[name]['keep_id']
    samples=read(name+'-http')
    baseline=next(x for x in samples if x['phase']=='baseline' and x['endpoint']=='status')
    assert baseline['http']==200 and baseline['status']=='succeeded',(name,baseline)
    summary['benchmarks'].append(dict(name=name,startup_ms=r['startup_ms'],old_startup_ms=before['startup_ms'],
        compaction_ms=[x['ms'] for x in r['rounds']],old_compaction_ms=[x['ms'] for x in before['rounds']],
        admission_ms=[x['ms'] for x in r['requests'][1:]],status_baseline_ms=baseline['elapsed_ms'],
        http_timeouts=sum(x.get('error','').endswith('Timeout') for x in samples),http_503=sum(x.get('http')==503 for x in samples),
        native_status=native['status'],records=r['count']))
for name in ('badhash-middle','badhash-last'):
    r=read(name);assert 'operation_store_unavailable' in r['error'] and not r['healthy']
summary['bad_hash_batches']='middle and final rejected'
ttl=read('ttl',run.parent/'ttl')
assert not ttl['error'] and ttl['count']==79
assert ttl['before_bytes']==ttl['after_read_bytes']>60*1024*1024
assert ttl['after_cleanup_bytes']<ttl['after_read_bytes']
assert ttl['public_status']['status']=='succeeded'
assert ttl['public_status']['data']['operation']['error']['code']=='result_expired'
assert ttl['repeat_id']==ttl['public_status']['operation_id']
summary['ttl_read_without_append']=dict(before=ttl['before_bytes'],after_read=ttl['after_read_bytes'],after_cleanup=ttl['after_cleanup_bytes'])
(run.parent/'checked-limits.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
