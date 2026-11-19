"""Prepare the bounded queue2 remainder; uses the existing isolated base/fixture."""
from pathlib import Path
import shutil
import sys
root = Path(__file__).resolve().parents[2]
run = root / '.local/queue2-rest'
refresh = '--refresh' in sys.argv
if not refresh:
    for route in ('probe', 'embedded', 'http', 'file', 'production'):
        db = run / route / 'db'
        db.mkdir(parents=True)
        shutil.copy2(root / '.local/profile-runtime/db/1Cv8.1CD', db / '1Cv8.1CD')
shutil.copytree(root / '1c/MCPToolkit', run / 'source', dirs_exist_ok=refresh)
p = run / 'source/MCPToolkit/Forms/ФормаМенеджераТестирования/Ext/Form/Module.bsl'
with p.open('a', encoding='utf8') as f:
    f.write((root / 'tests/test_client/queue2_remaining_probes.bsl').read_text(encoding='utf8'))
if not refresh:
    shutil.copytree(root / '.local/queue2/fixture', run / 'fixture')
    p = run / 'fixture/ApiFixture/Forms/Main/Ext/Form/Module.bsl'
    s = p.read_text(encoding='utf-8-sig').replace('    Текст = ""; Результат = "0";', '''    Текст = ""; Результат = "0";
    Элементы.Выбор.СписокВыбора.Добавить("A", "CHOICE_ALPHA");
    Элементы.Выбор.СписокВыбора.Добавить("B", "CHOICE_BETA");
    Элементы.Выбор.РежимВыбораИзСписка = Истина;''')
    p.write_text(s, encoding='utf-8-sig')
