"""Create a disposable form-unit-test EPF; no live MCP calls or client launch."""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
dest = ROOT / '.local/ui-log-runtime'
assert not dest.exists(), 'Use a fresh test directory; inspect previous run first'
shutil.copytree(ROOT / '1c/MCPToolkit', dest)
module = dest / 'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
text = module.read_text(encoding='utf-8-sig')
# Only the journal owner is stubbed. Public dispatch/callback/logging remain real.
text, count = re.subn(r'Процедура LifecycleЗавершить\([^\n]*\).*?КонецПроцедуры',
    'Процедура LifecycleЗавершить(Канал, Ид, Результат)\n\tВозврат;\nКонецПроцедуры', text, count=1, flags=re.S)
assert count == 1
opening = re.search(r'Процедура ПриОткрытии\(Отказ\).*?КонецПроцедуры', text, re.S)
assert opening
hook = '\tПодключитьОбработчикОжидания("ТестЖурналаПослеОткрытия", 1, Истина);\n'
text = text[:opening.end()-len('КонецПроцедуры')] + hook + text[opening.end()-len('КонецПроцедуры'):]
text += '\n' + Path(__file__).with_name('log_tests.bsl').read_text(encoding='utf-8')
report = (ROOT / '.local/ui-log-result.json').as_posix()
text += ('\n&НаКлиенте\nПроцедура ТестЖурналаПослеОткрытия()\n\tПопытка\n'
         f'\t\tВыполнитьТестыЖурнала("{report}");\n'
         '\tИсключение\n\t\tДокумент = Новый ТекстовыйДокумент;\n'
         '\t\tДокумент.УстановитьТекст(ЗаписатьJSON2(Новый Структура("error", ОписаниеОшибки())));\n'
         f'\t\tДокумент.Записать("{report}");\n'
         '\tКонецПопытки;\n\tЗавершитьРаботуСистемы(Ложь);\nКонецПроцедуры\n')
module.write_text(text, encoding='utf-8-sig')
print(dest / 'MCPToolkit.xml')
