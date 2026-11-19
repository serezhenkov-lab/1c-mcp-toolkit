"""Archive bounded profile evidence, excluding database, binaries and desktop images."""
import hashlib
import json
import re
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
run = root / '.local/profile-runtime'
dest = root / 'openspec/changes/upravlenie-test-klientom/evidence'
dest.mkdir(exist_ok=True)
main = root / '1c/MCPToolkit/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
pattern = r'// BEGIN GENERATED [^\n]+\n.*?// END GENERATED [^\n]+'
old = re.findall(pattern, (run / 'main-before.bsl').read_text(encoding='utf-8-sig'), re.S)
new = re.findall(pattern, main.read_text(encoding='utf-8-sig'), re.S)
assert old and old == new, 'Unrelated legacy generated blocks changed'
stages = ('configure', 'restart', 'restored', 'password-setup', 'password-restored', 'disabled-restored')
checks = [c for stage in stages for c in json.loads((run / (stage + '.json')).read_text(encoding='utf-8'))['checks']]
assert len(checks) == 28 and all(c['ok'] for c in checks)
assert json.loads((run / 'cleanup.json').read_text(encoding='utf-8-sig'))['remaining'] == 0
paths = [p for p in run.iterdir() if p.suffix in ('.json', '.log')]
paths += [run / 'bsl-final/e89756b13ec14d48a25fe12569ca5509/summary.json']
paths += [run / 'db-source/Roles/ApiProbeAdmin/Ext/Rights.xml']
sources = [main, main.parents[3] / 'ФормаМенеджераТестирования/Ext/Form/Module.bsl',
           main.parent.parent / 'Form.xml', root / '1c/runtime/local_test_profile.bsl',
           root / '1c/runtime/generate.py', Path(__file__).resolve(),
           root / 'tests/test_client/run_profile_runtime.py', root / 'tests/test_client/profile_ui.ps1']
paths += sources
manifest = {'runtime_assertions': 28, 'legacy_blocks_unchanged': len(old), 'files': [], 'binaries': {}}
archive = dest / 'local-profile-runtime.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in sorted(set(paths)):
        data = path.read_bytes()
        name = path.relative_to(root).as_posix()
        z.writestr(name, data)
        manifest['files'].append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
for name in ('Toolkit-final.epf', 'Toolkit-verified.epf'):
    manifest['binaries'][name] = hashlib.sha256((run / name).read_bytes()).hexdigest()
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for item in manifest['files']:
        assert hashlib.sha256(z.read(item['path'])).hexdigest() == item['sha256']
manifest['archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
(dest / 'local-profile-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'files': len(paths), 'bytes': archive.stat().st_size, 'checks': len(checks), 'legacy_blocks': len(old)}))
