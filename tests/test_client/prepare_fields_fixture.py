"""Prepare the isolated field-state fixture; build it with the standard EPF tool."""
from pathlib import Path
import shutil
import sys
root=Path(__file__).resolve().parents[2]
out=Path(sys.argv[1]).resolve()
assert out.is_relative_to(root/'.local'), 'Fixture preparation is restricted to .local'
shutil.copytree(root/'tests/test_client/action_fixture',out,dirs_exist_ok=True)
p=out/'ApiFixture/Forms/Main/Ext/Form/Module.bsl'
s=p.read_text(encoding='utf-8-sig')
old='Текст = "Начальное"; Результат = "0";'
assert s.count(old)==1
p.write_text(s.replace(old,old+'\n    Элементы.Результат.Доступность = Ложь;'),encoding='utf-8')
