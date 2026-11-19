"""Keep reports, exact fixtures and hashes; exclude databases and EPF binaries."""
import hashlib
import json
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parents[2]
run=root/'.local/queue1-acceptance'
dest=root/'openspec/changes/upravlenie-test-klientom/evidence'
archive=dest/'queue1-acceptance-runtime.zip'
assert not archive.exists(),'Preserve previous archive'
files=[]
for path in run.glob('*.json'):
    files.append((path,path.relative_to(run).as_posix()))
for route in ('http','file','embedded','file-attempt1'):
    folder=run/route
    for path in folder.iterdir():
        if path.is_file() and path.suffix in ('.json','.log','.err','.out'):
            files.append((path,path.relative_to(run).as_posix()))
    for path in (folder/'epf-final').rglob('Module.bsl'):
        files.append((path,path.relative_to(run).as_posix()))
for path in (root/'tests/test_client').glob('*queue1*'):
    if path.is_file():files.append((path,'scripts/'+path.name))
for name in ('prepare_embedded_stand.py','run_embedded_contract.py'):
    files.append((root/'tests/test_client'/name,'scripts/'+name))
for path in (root/'1c/runtime').glob('embedded*.bsl'):
    files.append((path,'runtime/'+path.name))
manifest=[]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
    for path,name in files:
        data=path.read_bytes();bundle.writestr(name,data)
        manifest.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    for item in manifest:
        assert hashlib.sha256(bundle.read(item['path'])).hexdigest()==item['sha256']
(dest/'queue1-acceptance-manifest.json').write_text(json.dumps(dict(archive=archive.name,
    sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=manifest),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(files=len(files),bytes=archive.stat().st_size)))
