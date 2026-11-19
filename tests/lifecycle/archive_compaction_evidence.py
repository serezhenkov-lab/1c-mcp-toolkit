"""Archive explicit test reports and controlled fault snapshots, never the database."""
from pathlib import Path
import hashlib
import json
import zipfile

root=Path(__file__).resolve().parents[2]
run=root/'.local/lifecycle-compaction'
dest=root/'openspec/changes/upravlenie-test-klientom/evidence'
files=[]
for pattern in ('*.json','*.log','stage-*/operations.jsonl*','journal-*/operations.jsonl*','public/*probe.json','public/*run.log'):
    for path in run.glob(pattern):
        if path.name!='case.json':files.append((path,'stand/'+path.relative_to(run).as_posix()))
for name in ('embedded_lifecycle.bsl','embedded_compaction.bsl','embedded_test_adapter.bsl','generate.py'):
    path=root/'1c/runtime'/name;files.append((path,path.relative_to(root).as_posix()))
for name in ('prepare_compaction_stand.py','compaction_fixture.bsl','run_compaction_stand.ps1','check_compaction_results.py'):
    path=root/'tests/lifecycle'/name;files.append((path,path.relative_to(root).as_posix()))
for name in ('prepare_embedded_stand.py','run_public_probe.py','run_embedded_probe.py','run_embedded_contract.py'):
    path=root/'tests/test_client'/name;files.append((path,path.relative_to(root).as_posix()))
archive=dest/'lifecycle-compaction-runtime.zip'
assert not archive.exists(), 'Preserve earlier evidence'
assert len({name for _,name in files})==len(files)
manifest=[]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for path,name in files:
        z.write(path,name)
        manifest.append(dict(path=name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
(dest/'lifecycle-compaction-manifest.json').write_text(json.dumps(dict(archive=archive.name,
    sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=manifest),ensure_ascii=False,indent=2),encoding='utf-8')
print(f'{len(files)} files; {archive.stat().st_size} bytes; ZIP integrity passed')
