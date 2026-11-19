"""Prepare a disposable permission/UI run with a uniquely identified document.

The client remains the existing test fixture, not a Toolkit client adapter.
Use only a separate disposable database: the UI write is committed.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

p = argparse.ArgumentParser()
p.add_argument('destination', type=Path)
a = p.parse_args()
here = Path(__file__).resolve().parent
dest = a.destination.resolve()
subprocess.run([sys.executable, str(here / 'prepare_runtime.py'), str(dest), '--permission'], check=True)
run_id = uuid.uuid4().hex
number = 'T73' + run_id[:8]
marker = 'TASK073:' + run_id
fixture = dest / 'fixture'
shutil.copytree(here / 'permission_fixture', fixture)
fp = fixture / 'ApiFixture/Forms/Main/Ext/Form/Module.bsl'
s = fp.read_text(encoding='utf-8-sig')
anchor = 'Документ.Дата = ТекущаяДата();'
assert s.count(anchor) == 1
s = s.replace(anchor, f'Документ.Дата = Дата(2026, 11, 14, 12, 0, 0);\n    Документ.Номер = "{number}";')
fp.write_text(s, encoding='utf-8-sig')
main = dest / 'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
s = main.read_text(encoding='utf-8-sig')
assert s.count('"TASK043"') == 1
s = s.replace('"TASK043"', f'"{marker}"')
anchor = 'ТестРежимUI("deny");\n\t\tТестРазрешениеКоманда("deny");'
assert s.count(anchor) == 1
s = s.replace(anchor, 'Если Не ТестПриемкаИсходныеДанные() Тогда ТестФиниш(); Возврат; КонецЕсли;\n\t\t' + anchor)
anchor = 'ТестРазрешениеКоманда("fill_required",'
assert s.count(anchor) == 1
s = s.replace(anchor, 'ТестПроверка("unique_after_refusal", ТестПриемкаЗапрос().Количество() = 0, "zero rows");\n\t\t\t' + anchor)
anchor = 'ЗавершитьСеансРазрешений(); ТестПроверка("session_grant_reset"'
assert s.count(anchor) == 1
s = s.replace(anchor, 'ТестПриемкаИтог();\n\t\t\t' + anchor)
query = (here / 'acceptance-result.sdbl').read_text(encoding='utf-8').strip()
bsl = (here / 'acceptance_ui_tests.bsl').read_text(encoding='utf-8')
for key, value in {'@ROOT@': dest.as_posix(), '@NUMBER@': number, '@MARKER@': marker,
                   '@QUERY@': query.replace('"', '""').replace('\n', '\n\t|')}.items():
    bsl = bsl.replace(key, value)
main.write_text(s + '\n' + bsl, encoding='utf-8-sig')
driver = dest / 'MCPToolkit/Forms/ФормаМенеджераТестирования/Ext/Form/Module.bsl'
with driver.open('a', encoding='utf-8') as out:
    out.write('\n' + (here / 'acceptance_preflight_probes.bsl').read_text(encoding='utf-8'))
(dest / 'acceptance-plan.json').write_text(json.dumps(dict(number=number, marker=marker,
    date='2026-11-14T12:00:00', query=query, scope='local fixture UI, committed disposable database write'),
    ensure_ascii=False, indent=2), encoding='utf-8')
