"""Archive explicit test evidence only: no databases, credentials or installed binaries."""
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

root = Path(__file__).resolve().parents[2]
dest = root / 'openspec/changes/upravlenie-test-klientom/evidence'
dest.mkdir(exist_ok=True)
files = []
for folder, names in {
    'queue1': ['public-probe.json', 'restart.json', 'restart-mode.json', 'restart-probe.json',
               'interrupted-probe.json', 'processes-after-restart.json', 'cleanup.json',
               'unit-final.log', 'contracts-final.log', 'public-final.log', 'source-check.json',
               'build2.log', 'main-before.bsl', 'driver-before.bsl', 'journal-before.py'],
    'queue1-file': ['public-probe.json', 'approval-probe-first.json', 'approval-probe.json',
                    'final-probe-first.json', 'final-probe.json', 'final-probe2.log',
                    'approval-probe2.log', 'build.log', 'build-final.log', 'build-recovery.log', 'fixture-error.lgp'],
}.items():
    run = root / '.local' / folder
    for name in names:
        path = run / name
        if not path.is_file():
            raise SystemExit('Missing evidence: ' + str(path))
        files.append((path, folder + '/' + name))
    with sqlite3.connect((run / 'journal/operations.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute("SELECT id,request_key,tool,state,event_seq,context,error_code FROM operations "
                                               "WHERE request_key LIKE '%approval%' OR request_key LIKE '%final-%' "
                                               "OR request_key LIKE 'restart-%' OR request_key LIKE 'interrupted-%' OR request_key='public-start'")]
    snapshot = run / 'journal-evidence.json'
    snapshot.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    files.append((snapshot, folder + '/journal-evidence.json'))

archive = dest / 'queue1-public-runtime.zip'
if archive.exists():
    raise SystemExit('Evidence archive already exists; preserve it')
manifest = []
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
    for path, name in files:
        bundle.write(path, name)
        manifest.append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size})
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
(dest / 'queue1-public-manifest.json').write_text(json.dumps({
    'archive': archive.name, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'files': manifest,
}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'files': len(files), 'bytes': archive.stat().st_size, 'archive': str(archive)}, ensure_ascii=False))
