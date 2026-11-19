"""Disposable real EPF polling localhost. No client adapter, no production edits."""
from pathlib import Path
import argparse
import re
import shutil

p = argparse.ArgumentParser()
p.add_argument('destination', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
dest = a.destination.resolve()
if not dest.is_relative_to(root / '.local') or dest.exists():
    p.error('Use a new .local directory')
shutil.copytree(root / '1c/MCPToolkit', dest)
module = dest / 'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
s = module.read_text(encoding='utf-8-sig')
m = re.search(r'Процедура ПриОткрытии\(Отказ\).*?КонецПроцедуры', s, re.S)
assert m
pos = m.end() - len('КонецПроцедуры')
s = s[:pos] + '\tПодключитьОбработчикОжидания("ТестLifecycleСтарт", 1, Истина);\n' + s[pos:]
s += '''
&НаКлиенте
Процедура ТестLifecycleСтарт()
    АдресСервера = "http://127.0.0.1:17653";
    ИдентификаторКанала = "lifecycle-test";
    РежимПодключения = 0;
    Подключиться(Неопределено, Ложь);
    РежимПодтвержденияОпасныхОпераций = "session_allow";
    ПодключитьОбработчикОжидания("ТестLifecycleСтоп", 1, Ложь);
КонецПроцедуры

&НаКлиенте
Процедура ТестLifecycleСтоп()
    ФайлОстановки = Новый Файл("@ROOT@/stop.txt");
    Если ФайлОстановки.Существует() Тогда
        ОтключитьсяОтСервера();
        ЗавершитьРаботуСистемы(Ложь);
    КонецЕсли;
КонецПроцедуры
'''.replace('@ROOT@', dest.as_posix())
module.write_text(s, encoding='utf-8-sig')
