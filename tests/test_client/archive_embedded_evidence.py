"""Preserve explicit disposable-stand evidence without databases or credentials."""
import hashlib
import json
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parents[2]
run=root/'.local/embedded-lifecycle'
dest=root/'openspec/changes/upravlenie-test-klientom/evidence'
names=['public-probe.json','embedded-probe.json','embedded-probe-first-attempt.json',
       'embedded-probe-port-attempt.json','embedded-probe-file-restart-failure.json',
       'contract-probe.json','recovery-prepare.json','recovery-check.json','recovery-request.json',
       'lock-probe.json','corruption-probe.json','source-check.json','bsl-final.json',
       'verification.json','cleanup.json','journal-v2/operations.jsonl']
files=[(run/name,'stand/'+name) for name in names]
for name in ['1c/runtime/generate.py','1c/runtime/embedded_lifecycle.bsl','1c/runtime/embedded_test_adapter.bsl',
             'tests/test_client/prepare_embedded_stand.py','tests/test_client/run_public_probe.py',
             'tests/test_client/run_embedded_probe.py','tests/test_client/run_embedded_contract.py',
             'tests/test_client/run_embedded_recovery.py']:
    files.append((root/name,name))
assert all(path.is_file() for path,_ in files)
archive=dest/'embedded-lifecycle-runtime.zip'
assert not archive.exists(), 'Preserve existing evidence'
manifest=[]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for path,name in files:
        z.write(path,name)
        manifest.append(dict(path=name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
(dest/'embedded-lifecycle-manifest.json').write_text(json.dumps(dict(archive=archive.name,
    sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=manifest),ensure_ascii=False,indent=2),encoding='utf-8')
print(f'{len(files)} files; {archive.stat().st_size} bytes; ZIP integrity passed')
