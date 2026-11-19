"""Validate and archive the three-route UI commit/response-loss evidence."""
import ast
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
stand = root / '.local/lost-response'
dest = root / 'openspec/changes/upravlenie-test-klientom/evidence'
manifest = {'routes': {}, 'files': []}
for route in ('embedded', 'http', 'file'):
    run = stand / route
    report = json.loads((run / 'results.json').read_text(encoding='utf-8'))
    assert len(report['checks']) == 20 and all(x['ok'] for x in report['checks'])
    fault = json.loads((run / 'dropped-response.json').read_text(encoding='utf-8'))
    assert fault['reply_bytes_sent'] == 0 and fault['terminal']['status'] == 'succeeded'
    assert json.loads((run / 'cleanup.json').read_text(encoding='utf-8-sig'))['remaining'] == 0
    row = {'passed': 20, 'marker': report['marker'], 'request_id': fault['terminal']['request_id'],
           'operation_id': fault['terminal']['operation_id'], 'bytes_delivered_to_caller': 0}
    if route != 'embedded':
        db = run / 'journal/operations.sqlite3'
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as con:
            rows = con.execute('SELECT id,state,tool FROM operations WHERE channel=? AND request_key=?', ('queue1', row['request_id'])).fetchall()
        assert rows == [(row['operation_id'], 'succeeded', 'test_action')], rows
        row['journal_rows_for_request'] = len(rows)
    manifest['routes'][route] = row
paths = [p for p in stand.rglob('*') if p.is_file() and p.suffix in ('.json', '.jsonl', '.log', '.out', '.err', '.bsl', '.xml')
         and 'bridge' not in p.parts and 'db' not in p.parts]
paths += [p for p in (root / 'tests/test_client').glob('*lost_response*') if p.is_file()]
paths += [root / 'onec_mcp_toolkit_proxy' / name for name in ('test_client_operations.py', 'operation_journal.py', 'command_queue.py', 'file_transport.py')]
for p in paths:
    if p.suffix == '.py':
        ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))
archive = dest / 'lost-response-runtime.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in sorted(set(paths)):
        data = path.read_bytes()
        name = path.relative_to(root).as_posix()
        z.writestr(name, data)
        manifest['files'].append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for item in manifest['files']:
        assert hashlib.sha256(z.read(item['path'])).hexdigest() == item['sha256']
manifest['archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
(dest / 'lost-response-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'assertions': 60, 'files': len(manifest['files']), 'bytes': archive.stat().st_size, 'routes': manifest['routes']}, ensure_ascii=False))
