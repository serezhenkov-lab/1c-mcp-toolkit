"""Isolated 8.5 EPF fixture. Fault injection is added only to this copy."""
from pathlib import Path
import argparse
import re
import shutil

root=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--run-dir',default='.local/lifecycle-compaction')
parser.add_argument('--revision',default='epf')
args=parser.parse_args()
run=(root/args.run_dir).resolve()
assert run.is_relative_to(root.resolve()/'.local')
run.mkdir(parents=True,exist_ok=True)
assert re.fullmatch(r'epf(?:-[a-z0-9]+)?',args.revision)
dest=run/args.revision
assert not dest.exists()
shutil.copytree(root/'1c/MCPToolkit',dest)
path=dest/'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
s=path.read_text(encoding='utf-8-sig')
s='&НаКлиенте\nПерем ТестСбой;\n&НаКлиенте\nПерем ТестПроверки;\n&НаКлиенте\nПерем ТестОтложенныйОтчет;\n'+s
for phase in ('prepared','committed','old_removed','installed'):
    s=re.sub(r'(// Барьер: '+phase+r'[^\n]*\n)',r'\1        ТестСбойКомпактации("'+phase+'");\n',s)
m=re.search(r'Процедура ПриОткрытии\(Отказ\).*?КонецПроцедуры',s,re.S)
pos=m.end()-len('КонецПроцедуры')
s=s[:pos]+'ПодключитьОбработчикОжидания("ТестКомпактации", 1, Истина);\n'+s[pos:]
s+='\n'+(root/'tests/lifecycle/compaction_fixture.bsl').read_text(encoding='utf-8')
s=s.replace('@ROOT@',run.as_posix())
path.write_text(s,encoding='utf-8-sig')
(run/'db').mkdir(exist_ok=True)
if not (run/'db/1Cv8.1CD').exists():
    shutil.copy2(root/'.local/lifecycle-approval/db/1Cv8.1CD',run/'db/1Cv8.1CD')
