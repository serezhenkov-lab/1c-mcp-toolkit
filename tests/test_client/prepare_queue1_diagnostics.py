"""Follow-up cases only; preserve completed commit/restart evidence."""
import shutil
from pathlib import Path
root = Path(__file__).resolve().parents[2]
stand = root / '.local/queue1-finish'
(stand / 'diagnostics/db').mkdir(parents=True)
shutil.copy2(root / '.local/profile-runtime/db/1Cv8.1CD', stand / 'diagnostics/db/1Cv8.1CD')
shutil.copytree(root / '1c/MCPToolkit', stand / 'diagnostics-source')
p = stand / 'diagnostics-source/MCPToolkit/Forms/ФормаМенеджераТестирования/Ext/Form/Module.bsl'
s = p.read_text(encoding='utf-8-sig')
s = s.replace('Функция ДанныеПроцесса(ИдПроцесса)', 'Функция ДанныеПроцесса(ИдПроцесса)\n\tЕсли ИдПроцесса = -81 Тогда ВызватьИсключение "80041003 PRIVATE_TEST_SECRET"; КонецЕсли;')
s = s.replace('ТКПриложение.УстановитьСоединение();', 'Если ТКПрофиль.id = "fault_connect" Тогда ВызватьИсключение "PRIVATE_TEST_SECRET"; КонецЕсли;\n\t\t\t\t\t\tТКПриложение.УстановитьСоединение();')
s = s.replace('ПослеПодключения = ПроцессПорта();', 'ПослеПодключения = ПроцессПорта();\n\t\t\t\t\t\tЕсли ТКПрофиль.id = "fault_endpoint" Тогда ПослеПодключения.created = "mismatch"; КонецЕсли;')
s += (root / 'tests/test_client/queue1_finish_probes.bsl').read_text(encoding='utf-8-sig')
p.write_text(s, encoding='utf-8-sig')
shutil.copytree(stand / 'fixture', stand / 'diagnostics-fixture')
p = stand / 'diagnostics-fixture/ApiFixture/Forms/Main/Ext/Form/Module.bsl'
s = p.read_text(encoding='utf-8-sig')
needle = '    Для Каждого Имя Из СтрРазделить'
insert = '''    Страницы = Элементы.Добавить("Вкладки", Тип("ГруппаФормы"));
    Страницы.Вид = ВидГруппыФормы.Страницы;
    Для Индекс = 1 По 2 Цикл
        Страница = Элементы.Добавить("Вкладка" + Формат(Индекс, "ЧГ=0"), Тип("ГруппаФормы"), Страницы);
        Страница.Вид = ВидГруппыФормы.Страница;
        Страница.Заголовок = Страница.Имя;
        Кнопка = Элементы.Добавить("КнопкаВкладки" + Формат(Индекс, "ЧГ=0"), Тип("КнопкаФормы"), Страница);
        Кнопка.ИмяКоманды = "Проверить";
    КонецЦикла;
'''
s = s.replace(needle, insert + needle)
s = s.replace('        Кнопка.ИмяКоманды = "Проверить";\n        Если Имя', '''        Кнопка.ИмяКоманды = "Проверить";
        Поле = Элементы.Добавить(Имя + "Поле", Тип("ПолеФормы"), Группа);
        Поле.Вид = ВидПоляФормы.ПолеВвода;
        Поле.ПутьКДанным = "Текст";
        Таблица = Элементы.Добавить(Имя + "Таблица", Тип("ТаблицаФормы"), Группа);
        Таблица.ПутьКДанным = "Строки";
        Если Имя''')
p.write_text(s, encoding='utf-8-sig')
