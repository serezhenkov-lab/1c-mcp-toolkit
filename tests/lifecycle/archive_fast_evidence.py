"""Archive the isolated optimization proof without databases or working binaries."""
from pathlib import Path
import hashlib,json,zipfile

root=Path(__file__).resolve().parents[2]
run=root/'.local/lifecycle-fast'
dest=root/'openspec/changes/upravlenie-test-klientom/evidence'
files={}
for pattern in ('*.json','*.log','limits/*.json','ttl/*.json','compaction/*.json',
                'compaction/stage-*/operations.jsonl*','compaction/journal-*/operations.jsonl*'):
    for p in run.glob(pattern):files['stand/'+p.relative_to(run).as_posix()]=p
for name in ('appendlocked','renameblocked','active','badhash-middle','badhash-last'):
    p=run/'limits'/('journal-'+name)/'operations.jsonl'
    files['stand/'+p.relative_to(run).as_posix()]=p
for p in (root/'1c/runtime').glob('*'):
    if p.is_file():files[p.relative_to(root).as_posix()]=p
for name in ('embedded_lifecycle.bsl','embedded_compaction.bsl','embedded_test_adapter.bsl'):
    files['before/'+name]=run/name
for p in (root/'tests/lifecycle').glob('*'):
    if p.is_file() and any(x in p.name for x in ('fast','limits','compaction')):
        files[p.relative_to(root).as_posix()]=p
for name in ('tests/test_public_test_operations.py','onec_mcp_toolkit_proxy/test_client_operations.py'):
    files[name]=root/name
for name in ('limits','ttl','compaction'):
    files['fixture/'+name+'-Module.bsl']=run/name/'epf/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
files['baseline/checked-results.json']=root/'.local/lifecycle-limits/checked-results.json'
files['baseline/seeds.json']=root/'.local/lifecycle-limits/seeds.json'
files['stand/bsl-summary.json']=next((run/'bsl').glob('*/summary.json'))
files['protocol/lifecycle-fast.md']=dest.parent/'lifecycle-fast.md'
archive=dest/'lifecycle-fast-runtime.zip'
assert not archive.exists(),'Preserve previous evidence'
manifest=[]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for name,p in sorted(files.items()):
        data=p.read_bytes();z.writestr(name,data)
        manifest.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for row in manifest:assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
(dest/'lifecycle-fast-manifest.json').write_text(json.dumps(dict(archive=archive.name,
    sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=manifest),ensure_ascii=False,indent=2),encoding='utf-8')
print(len(manifest),'files; verified;',archive.stat().st_size,'bytes')
