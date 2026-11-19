"""Archive bounded evidence and provenance, not databases or installation files."""
import ast
import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
run = root / '.local/queue1-finish'
evidence = root / 'openspec/changes/upravlenie-test-klientom/evidence'
paths = []
for p in run.rglob('*'):
    relative = p.relative_to(run)
    if not p.is_file() or 'db' in relative.parts or any(x.startswith('bsl') for x in relative.parts[:-1]):
        continue
    if p.suffix in ('.json', '.jsonl', '.log', '.out', '.err', '.bsl', '.diff') or p.name.endswith('.running'):
        paths.append(p)
scripts = list((root / 'tests/test_client').glob('*queue1*finish*'))
scripts += list((root / 'tests/test_client').glob('*queue1*diagnostics*'))
scripts += [root / 'tests/test_client/resume_queue1_file.py', root / 'tests/test_client/run_queue1_ownership.py', root / 'tests/test_client/run_queue1_public_add.py']
paths += scripts
driver = root / '1c/MCPToolkit/MCPToolkit/Forms/ФормаМенеджераТестирования/Ext/Form/Module.bsl'
paths.append(driver)
for script in scripts:
    if script.suffix == '.py':
        ast.parse(script.read_text(encoding='utf-8-sig'), filename=str(script))
manifest = {'files': [], 'binaries': {}, 'runtime': {},
            'limitations': ['file startup with unresolved .running requires explicit recovery',
                            'AccessDenied and connect races injected at test boundary',
                            'local file database only; observer and anonymization deferred']}
for route in ('embedded', 'http', 'file', 'diagnostics', 'ownership', 'public-add'):
    data = json.loads((run / route / 'results.json').read_text(encoding='utf-8'))
    assert all(c['ok'] for c in data['checks']), route
    manifest['runtime'][route] = {'passed': len(data['checks'])}
    cleanup = run / route / ('cleanup-recovery.json' if route == 'file' else 'cleanup.json')
    assert json.loads(cleanup.read_text(encoding='utf-8'))['all_exited'], route
for p in run.glob('*.epf'):
    manifest['binaries'][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
report = json.loads((run / 'bsl-release-result.json').read_text(encoding='utf-8-sig'))
assert report['errorCount'] == 0 and report['status'] == 'findings'
manifest['bsl'] = {k: report[k] for k in ('status', 'diagnosticCount', 'errorCount')}
archive = evidence / 'queue1-finish-runtime.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in sorted(set(paths)):
        name = p.relative_to(root).as_posix()
        data = p.read_bytes()
        z.writestr(name, data)
        manifest['files'].append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)})
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
manifest['archive'] = {'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'bytes': archive.stat().st_size}
(evidence / 'queue1-finish-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'files': len(paths), **manifest['archive'], 'runtime': manifest['runtime']}))
