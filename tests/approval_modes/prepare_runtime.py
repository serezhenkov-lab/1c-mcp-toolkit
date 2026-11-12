"""Prepare a disposable EPF source copy; never modify production source/runtime."""
import argparse
from pathlib import Path
import shutil
import re

parser = argparse.ArgumentParser()
parser.add_argument('destination', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
destination = args.destination.resolve()
if not destination.is_relative_to(root / '.local') or destination.exists():
    parser.error('destination must be a new directory inside the repository .local')
shutil.copytree(root / '1c' / 'MCPToolkit', destination)
module = destination / 'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
text = module.read_text(encoding='utf-8-sig')
report = (destination.parent / (destination.name + '-result.json')).as_posix()
opening = re.search(r'Процедура ПриОткрытии\(Отказ\).*?КонецПроцедуры', text, re.S)
assert opening is not None
hook = '\tПодключитьОбработчикОжидания("ТестыРежимовПослеОткрытия", 1, Истина);\n'
text = (text[:opening.end() - len('КонецПроцедуры')] + hook
        + text[opening.end() - len('КонецПроцедуры'):])
text += ('\n&НаКлиенте\nПроцедура ТестыРежимовПослеОткрытия()\n'
         f'\tВыполнитьТестыРежимов("{report}");\n'
         '\tЗавершитьРаботуСистемы(Ложь);\nКонецПроцедуры\n')
text += '\n' + Path(__file__).with_name('form_tests.bsl').read_text(encoding='utf-8')
module.write_text(text, encoding='utf-8-sig', newline='\r\n')
print(destination / 'MCPToolkit.xml')
print(report)
