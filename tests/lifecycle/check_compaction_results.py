"""Validate actual platform outputs and on-disk payload removal."""
from pathlib import Path
import json
import sys

run=Path(__file__).resolve().parents[2]/'.local/lifecycle-compaction'
if len(sys.argv)>1:run=Path(sys.argv[1])
def result(name):return json.loads((run/(name+'.json')).read_text(encoding='utf-8-sig'))
checks=0
for name in ['normal','prepared','committed','old_removed','installed','legacy','quota','growth','idle','locked']:
    first=result(name)
    fault=name in ('prepared','committed','old_removed','installed','locked')
    assert bool(first['error'])==fault,(name,first['error'])
    assert all(x['passed'] for x in first['checks']),name
    checks+=len(first['checks'])
    if name not in ('quota','growth'):
        restored=result(name+'-recovered')
        assert restored['error'] is None,(name,restored['error'])
        assert all(x['passed'] for x in restored['checks'])
        checks+=len(restored['checks'])
        before={x['request_id']:(x['id'],x['fingerprint'],x['event_seq']) for x in first['records']}
        after={x['request_id']:(x['id'],x['fingerprint'],x['event_seq']) for x in restored['records']}
        assert before==after,name
        folder=run/('journal-'+name)
        assert not list(folder.glob('*.next')) and not list(folder.glob('*.commit')),name
        data=(folder/'operations.jsonl').read_bytes()
        assert b'MARKER_expired' not in data,name
        assert b'MARKER_keep' in data and b'MARKER_unknown' in data,name
for name in ('badmarker','badnext'):
    value=result(name)
    assert value['error'] and not value['healthy'] and not value['checks'],name
    assert (run/('journal-'+name)/'operations.jsonl.commit').exists()
orphan=result('orphan')
assert not orphan['error'] and all(x['passed'] for x in orphan['checks'])
checks+=len(orphan['checks'])
assert b'MARKER_expired' not in (run/'journal-orphan/operations.jsonl').read_bytes()
growth=result('growth')
summary=dict(platform='8.5.1.1529',bsl_assertions=checks,stages=4,corrupt_committed_cases=2,
             uncommitted_orphan_recovered=True,keys_and_fingerprints_preserved=True,
             expired_payload_absent=True,growth_before=growth['bytes_before'],growth_after=growth['bytes_after'])
(run/'checked-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
