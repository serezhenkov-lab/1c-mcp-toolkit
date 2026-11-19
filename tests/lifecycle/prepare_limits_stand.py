"""Synthetic persisted journals; real owner/API and platform execute the probes."""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

root=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--run-dir',default='.local/lifecycle-limits')
parser.add_argument('--seeds-only',action='store_true')
parser.add_argument('--fixture-only',action='store_true')
parser.add_argument('--revision',default='epf')
parser.add_argument('--interleave-writes',action='store_true')
args=parser.parse_args()
run=(root/args.run_dir).resolve()
assert run.is_relative_to(root.resolve()/'.local')
run.mkdir(exist_ok=True,parents=True)
assert re.fullmatch(r'epf(?:-[a-z0-9]+)?',args.revision)
if not args.seeds_only:
    assert not (run/args.revision).exists()
    shutil.copytree(root/'1c/MCPToolkit',run/args.revision)
    p=run/args.revision/'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
    s=p.read_text(encoding='utf-8-sig')
    s='&НаКлиенте\nПерем ТестЛимитСлучай;\n&НаКлиенте\nПерем ТестЛимитОтчет;\n&НаКлиенте\nПерем ТестЛимитРаунд;\n'+s
    m=re.search(r'Процедура ПриОткрытии\(Отказ\).*?КонецПроцедуры',s,re.S)
    pos=m.end()-len('КонецПроцедуры')
    s=s[:pos]+'ПодключитьОбработчикОжидания("ТестЛимитыСтарт", 1, Истина);\n'+s[pos:]
    s+='\n'+(root/'tests/lifecycle/limits_fixture.bsl').read_text(encoding='utf-8')
    if args.interleave_writes:
        s=s.replace('    Работа = ОбщийLifecycle.compaction;','    ТестЗаписьМеждуШагами();\n    Работа = ОбщийLifecycle.compaction;',1)
        s+='\n'+(root/'tests/lifecycle/http_interleave_fixture.bsl').read_text(encoding='utf-8')
    p.write_text(s.replace('@ROOT@',run.as_posix()),encoding='utf-8-sig')
    (run/'db').mkdir(exist_ok=True)
    if not (run/'db/1Cv8.1CD').exists():
        shutil.copy2(root/'.local/lifecycle-approval/db/1Cv8.1CD',run/'db/1Cv8.1CD')
if args.fixture_only:
    raise SystemExit(0)
source=root/'.local/lifecycle-compaction/stage-normal/operations.jsonl'
records=[json.loads(json.loads(x)['payload']) for x in source.read_text(encoding='utf-8-sig').splitlines()]
template=next(x for x in records if x['request_id']=='keep')

def packet(row):
    text=json.dumps(row,ensure_ascii=False,indent=4)
    value=dict(payload=text,hash=base64.b64encode(hashlib.sha256(text.encode()).digest()).decode())
    return (json.dumps(value,ensure_ascii=False,indent=4).replace('\n','')+'\n').encode()

def seed(name,count,target=None):
    folder=run/('journal-'+name);folder.mkdir(exist_ok=True)
    path=folder/'operations.jsonl'
    if path.exists():
        assert not target or path.stat().st_size==target
        return dict(name=name,count=count,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),keep_id=template['id'])
    rows=[]
    for i in range(count):
        row=copy.deepcopy(template)
        if i:
            row.update(id=str(uuid.uuid4()),key=hashlib.sha256((name+str(i)).encode()).hexdigest(),request_id=f'seed-{i}')
        row.update(revision=1,state='succeeded' if target else 'result_expired',expires=90000000000000)
        if target:
            row['result']={'success':True,'data':{'contract_version':'1','request_id':row['request_id'],'operation_id':row['id'],
                'session_id':'seed-session','status':'succeeded','execution':'not_started','verification':'not_requested',
                'observed_at':None,'observed_state':None,'data':{'text':''},'messages':[],'error':None}}
        else: row['result']=None
        rows.append(row)
    data=[packet(x) for x in rows]
    if target:
        remaining=target-3-sum(map(len,data))
        width,extra=divmod(remaining,count)
        assert 0<width<1000000
        for i,row in enumerate(rows):
            row['result']['data']['data']['text']='x'*(width+(extra if i==count-1 else 0))
        data=[packet(row) for row in rows]
    with path.open('wb') as f:
        f.write(b'\xef\xbb\xbf')
        for line in data:f.write(line)
    assert not target or path.stat().st_size==target
    return dict(name=name,count=count,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),keep_id=template['id'])

manifest=[seed('keys1000',1000),seed('keys10000',10000),seed('keys9999',9999),
          seed('near60',74,60*1024*1024-4096),seed('over60',75,60*1024*1024+4096),
          seed('near64',79,64*1024*1024-4096)]
folder=run/'journal-over64';folder.mkdir()
with (folder/'operations.jsonl').open('wb') as f:f.truncate(64*1024*1024+1)
manifest.append(dict(name='over64',bytes=64*1024*1024+1,synthetic_sparse_oversize=True))
(run/'seeds.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print([(x['name'],x['bytes']) for x in manifest])
