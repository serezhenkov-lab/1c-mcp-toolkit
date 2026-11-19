"""Keep final and earlier interrupted proofs; exclude databases and EPF binaries."""
from pathlib import Path
import hashlib,json,zipfile

root=Path(__file__).resolve().parents[2]
run=root/'.local/lifecycle-http'
dest=root/'openspec/changes/upravlenie-test-klientom/evidence'
files={}
for pattern in ('*.json','*.log','limits/*.json','mutation/*.json','compaction/*.json','final/*.json','final-compaction/*.json',
                'final-compaction/stage-*/operations.jsonl*','final-compaction/journal-*/operations.jsonl*',
                'final/journal-mutation/operations.jsonl*','final/journal-initializing/operations.jsonl*',
                'limits/journal-keys10000/operations.jsonl*','compaction/stage-idle/operations.jsonl*'):
    for p in run.glob(pattern):files['stand/'+p.relative_to(run).as_posix()]=p
for p in (root/'1c/runtime').glob('*'):
    if p.is_file():files[p.relative_to(root).as_posix()]=p
for name in ('embedded_lifecycle.bsl','embedded_compaction.bsl','embedded_test_adapter.bsl'):
    files['before/'+name]=run/name
for p in (root/'tests/lifecycle').glob('*'):
    if p.is_file() and any(x in p.name for x in ('http','limits','compaction')):files[p.relative_to(root).as_posix()]=p
for name,revision in (('limits','epf-final'),('mutation','epf'),('compaction','epf-final'),('final','epf'),('final-compaction','epf')):
    files['fixture/'+name+'-Module.bsl']=run/name/revision/'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
files['stand/bsl-summary-final.json']=next((run/'bsl-final').glob('*/summary.json'))
files['baseline/checked-limits.json']=root/'.local/lifecycle-fast/checked-limits.json'
files['protocol/lifecycle-http.md']=dest.parent/'lifecycle-http.md'
archive=dest/'lifecycle-http-runtime.zip';assert not archive.exists(),'Preserve earlier evidence'
manifest=[]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for name,p in sorted(files.items()):
        data=p.read_bytes();z.writestr(name,data);manifest.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for row in manifest:assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
(dest/'lifecycle-http-manifest.json').write_text(json.dumps(dict(archive=archive.name,
    sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=manifest),ensure_ascii=False,indent=2),encoding='utf-8')
print(len(manifest),'files; verified;',archive.stat().st_size,'bytes')
