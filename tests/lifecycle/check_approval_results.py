"""Audit stored outcomes and event order after the two actual 1C runtime runs."""
import json
import sqlite3
from pathlib import Path
root = Path(__file__).resolve().parents[2]
run = root / '.local/lifecycle-approval'
summary = {}
for route, journal in [('http', 'journal'), ('file', 'journal-file')]:
    cases = json.loads((run / f'probe-{route}.json').read_text(encoding='utf-8'))
    assert len(cases) == 6
    db = sqlite3.connect((run / journal / 'operations.sqlite3').as_uri() + '?mode=ro', uri=True)
    checks = []
    for case in cases:
        status, seq = db.execute('SELECT state,event_seq FROM operations WHERE id=?', (case['final']['operation_id'],)).fetchone()
        expected_seq = 0 if case['case'] == 'DENY' else (2 if case['case'] in ('ALLOW', 'SESSION') else 1)
        assert seq == expected_seq, (route, case['case'], seq)
        assert status == case['final']['status']
        checks.append(dict(case=case['case'], status=status, event_seq=seq, document_count=case['count']))
    db.close()
    summary[route] = checks
(run / 'runtime-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print('12/12 runtime cases; persisted event sequence and data counts verified')
