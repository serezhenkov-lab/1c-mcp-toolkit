"""Archive exact implementation and stand evidence without database binaries."""
import hashlib
import json
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parents[2]
run=root/'.local/queue1-file-restart'
dest=root/'openspec/changes/upravlenie-test-klientom/evidence'
archive=dest/'file-restart-runtime.zip'
assert not archive.exists()
files=[]
for directory in (run,run/'file',run/'file-before-final'):
    for p in directory.iterdir():
        if p.is_file() and p.suffix in ('.json','.log','.err','.out'):
            files.append((p,p.relative_to(run).as_posix()))
for directory in (run/'file/epf-final',run/'file-before-final/epf-final'):
    for p in directory.rglob('Module.bsl'):
        files.append((p,p.relative_to(run).as_posix()))
for name in ('command_queue.py','file_transport.py'):
    files.append((root/'onec_mcp_toolkit_proxy'/name,'production/'+name))
files.append((root/'tests/test_file_transport.py','tests/test_file_transport.py'))
for p in (root/'tests/test_client').glob('*queue1*'):
    if p.is_file():files.append((p,'scripts/'+p.name))
for name in ('check_file_restart.py','archive_file_restart.py','prepare_embedded_stand.py'):
    files.append((root/'tests/test_client'/name,'scripts/'+name))
manifest=[]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p,name in files:
        data=p.read_bytes();z.writestr(name,data)
        manifest.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for item in manifest:assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
(dest/'file-restart-manifest.json').write_text(json.dumps(dict(archive=archive.name,
    sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=manifest),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(files=len(files),bytes=archive.stat().st_size)))
