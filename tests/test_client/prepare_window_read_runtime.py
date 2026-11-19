"""Test the bounded window observation read in a disposable EPF, without live UI actions."""
from pathlib import Path
import re
import shutil

root = Path(__file__).resolve().parents[2]
dest = root / '.local/mvp-window-read-runtime'
assert not dest.exists(), 'Inspect the existing run before repeating'
shutil.copytree(root / '1c/MCPToolkit', dest)
manager = dest / 'MCPToolkit/Forms/ФормаМенеджераТестирования/Ext/Form/Module.bsl'
text = manager.read_text(encoding='utf-8-sig')
text = '&НаКлиенте\nПерем ТестЧтения, ТестОтказы;\n' + text
stub = '''Функция СнимокОконКлиента()
    ТестЧтения = ТестЧтения + 1;
    Если ТестОтказы > 0 Тогда
        ТестОтказы = ТестОтказы - 1;
        ВызватьИсключение "TEST_WINDOW_DISPOSED";
    КонецЕсли;
    Возврат Новый Структура("items,truncated,observed_at", Новый Массив, Ложь, "test-observation");
КонецФункции'''
text, count = re.subn(r'Функция СнимокОконКлиента\(\).*?КонецФункции', stub, text, flags=re.S, count=1)
assert count == 1
text += '''
&НаКлиенте
Функция ТестОграниченногоЧтенияОкон() Экспорт
    Проверки = Новый Массив;
    ТКДиагностика = Новый Структура;
    ТестЧтения = 0; ТестОтказы = 0;
    НаблюдатьОкна();
    Если ТестЧтения <> 1 Тогда ВызватьИсключение "FAILED stable read"; КонецЕсли;
    Проверки.Добавить("stable read once");
    ТестЧтения = 0; ТестОтказы = 1;
    НаблюдатьОкна();
    Если ТестЧтения <> 2 Или ТКОкна.observed_at <> "test-observation"
        Или ТКДиагностика.window_read_retries <> 1 Тогда ВызватьИсключение "FAILED bounded retry"; КонецЕсли;
    Проверки.Добавить("transient failure rereads once");
    ТестЧтения = 0; ТестОтказы = 10; Отказ = Ложь;
    Попытка НаблюдатьОкна(); Исключение Отказ = Истина; КонецПопытки;
    Если Не Отказ Или ТестЧтения <> 2 Тогда ВызватьИсключение "FAILED permanent failure"; КонецЕсли;
    Проверки.Добавить("permanent failure propagates after two reads");
    Возврат Проверки;
КонецФункции
'''
manager.write_text(text, encoding='utf-8-sig')
module = dest / 'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
text = module.read_text(encoding='utf-8-sig')
opening = re.search(r'Процедура ПриОткрытии\(Отказ\).*?КонецПроцедуры', text, re.S)
assert opening
hook = '\tПодключитьОбработчикОжидания("ТестЧтенияОконПослеОткрытия", 1, Истина);\n'
text = text[:opening.end()-len('КонецПроцедуры')] + hook + text[opening.end()-len('КонецПроцедуры'):]
report = (root / '.local/mvp-window-read-result.json').as_posix()
text += f'''
&НаКлиенте
Процедура ТестЧтенияОконПослеОткрытия()
    Попытка
        Менеджер = ПолучитьФорму(ИмяСлужебнойФормыМенеджераТестирования(), , ЭтаФорма);
        Результат = Новый Структура("checks", Менеджер.ТестОграниченногоЧтенияОкон());
    Исключение
        Результат = Новый Структура("error", ОписаниеОшибки());
    КонецПопытки;
    Документ = Новый ТекстовыйДокумент;
    Документ.УстановитьТекст(ЗаписатьJSON2(Результат));
    Документ.Записать("{report}");
    ЗавершитьРаботуСистемы(Ложь);
КонецПроцедуры
'''
module.write_text(text, encoding='utf-8-sig')
print(dest / 'MCPToolkit.xml')
