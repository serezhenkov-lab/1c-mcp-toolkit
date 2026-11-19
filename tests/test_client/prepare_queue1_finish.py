"""Disposable queue1 stand; fault hooks never go into production sources."""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[2]
run = root / '.local/queue1-finish'
for route in ('embedded', 'http', 'file'):
    db = run / route / 'db'
    db.mkdir(parents=True, exist_ok=True)
    assert not (db / '1Cv8.1CD').exists()
    shutil.copy2(root / '.local/profile-runtime/db/1Cv8.1CD', db / '1Cv8.1CD')
shutil.copytree(root / '1c/MCPToolkit', run / 'source')
main = run / 'source/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
s = main.read_text(encoding='utf-8-sig')
needle = 'Процедура ПослеПубличногоТестирования(Ответ, Команда) Экспорт'
hook = '''
	Если Команда.Свойство("params") И Команда.params.Свойство("request_id")
		И Лев(Команда.params.request_id, 8) = "unknown-" Тогда
		Запись = Новый ЗаписьJSON;
		Запись.ОткрытьФайл("BARRIER");
		ЗаписатьJSON(Запись, Новый Структура("answer,command", Ответ, Команда));
		Запись.Закрыть();
		Возврат; // Injected crash boundary: UI callback completed; lifecycle not finalized.
	КонецЕсли;
'''.replace('BARRIER', (run / 'barrier.json').as_posix())
assert s.count(needle) == 1
s = s.replace(needle, needle + hook)
main.write_text(s, encoding='utf-8-sig')
driver = run / 'source/MCPToolkit/Forms/ФормаМенеджераТестирования/Ext/Form/Module.bsl'
s = driver.read_text(encoding='utf-8-sig')
s = s.replace('Функция ДанныеПроцесса(ИдПроцесса)', 'Функция ДанныеПроцесса(ИдПроцесса)\n\tЕсли ИдПроцесса = -81 Тогда ВызватьИсключение "80041003 PRIVATE_TEST_SECRET"; КонецЕсли;')
s += (root / 'tests/test_client/queue1_finish_probes.bsl').read_text(encoding='utf-8-sig')
driver.write_text(s, encoding='utf-8-sig')
shutil.copytree(root / '.local/lost-response/fixture', run / 'fixture')
p = run / 'fixture/ApiFixture/Forms/Main/Ext/Form/Module.bsl'
s = p.read_text(encoding='utf-8-sig').replace('/.local/lost-response/', '/.local/queue1-finish/')
# Server-created UI fixtures; native effective properties are observed by test manager.
s = s.replace('Текст = ""; Результат = "0";', '''Текст = ""; Результат = "0";
    Для Индекс = 1 По 25 Цикл
        Кнопка = Элементы.Добавить("Кандидат" + Формат(Индекс, "ЧГ=0"), Тип("КнопкаФормы"));
        Кнопка.ИмяКоманды = "Проверить";
        Кнопка.Заголовок = "Одинаковый кандидат";
    КонецЦикла;
    Для Каждого Имя Из СтрРазделить("Скрытая,Недоступная", ",") Цикл
        Группа = Элементы.Добавить(Имя, Тип("ГруппаФормы"));
        Группа.Вид = ВидГруппыФормы.ОбычнаяГруппа;
        Кнопка = Элементы.Добавить(Имя + "Кнопка", Тип("КнопкаФормы"), Группа);
        Кнопка.ИмяКоманды = "Проверить";
        Если Имя = "Скрытая" Тогда Группа.Видимость = Ложь; Иначе Группа.Доступность = Ложь; КонецЕсли;
    КонецЦикла;''')
p.write_text(s, encoding='utf-8-sig')
print(run)
