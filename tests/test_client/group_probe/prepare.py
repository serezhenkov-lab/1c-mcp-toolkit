"""Prepare diagnostic-only group probes after prepare_runtime.py --action."""
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('run', type=Path)
parser.add_argument('fixture', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
run, fixture = args.run.resolve(), args.fixture.resolve()
assert run.is_relative_to(root / '.local') and fixture.is_relative_to(root / '.local')
module = run / 'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
s = module.read_text(encoding='utf-8-sig')
anchor = 'ТестДействиеКоманда("activate", "activate_window");'
assert s.count(anchor) == 1
s = s.replace(anchor, '''Для Каждого Проба Из ТестДрайвер.ТестСвойстваГруппUI() Цикл
            ТестПроверка(Проба.name, Проба.ok, Проба.details);
        КонецЦикла;
        ТестФиниш();''')
module.write_text(s, encoding='utf-8-sig')
driver = run / 'MCPToolkit/Forms/ФормаМенеджераТестирования/Ext/Form/Module.bsl'
with driver.open('a', encoding='utf-8') as stream:
    stream.write('\n' + Path(__file__).with_name('driver.bsl').read_text(encoding='utf-8'))
form = fixture / 'ApiFixture/Forms/Main/Ext/Form.xml'
s = form.read_text(encoding='utf-8-sig')
groups = []
for i, (name, card, link) in enumerate((('Карточка', True, True), ('Обычная', False, False), ('БезГиперссылки', True, False))):
    n = 200 + i * 2
    groups.append(f'<UsualGroup name="{name}" id="{n}"><ShowAsCard>{str(card).lower()}</ShowAsCard>'
                  f'<Hyperlink>{str(link).lower()}</Hyperlink><Events><Event name="Click">ГруппаНажатие</Event></Events>'
                  f'<ChildItems><LabelDecoration name="{name}Метка" id="{n+1}"><Title><v8:item><v8:lang>ru</v8:lang>'
                  f'<v8:content>{name}</v8:content></v8:item></Title></LabelDecoration></ChildItems></UsualGroup>')
s = s.replace('<ChildItems>', '<ChildItems>' + ''.join(groups), 1)
form.write_text(s, encoding='utf-8-sig')
fm = fixture / 'ApiFixture/Forms/Main/Ext/Form/Module.bsl'
with fm.open('a', encoding='utf-8') as stream:
    stream.write('\n&НаКлиенте\nПроцедура ГруппаНажатие(Элемент, СтандартнаяОбработка)\n'
                 '\tРезультат = Строка(Число(Результат) + 1);\nКонецПроцедуры\n')
