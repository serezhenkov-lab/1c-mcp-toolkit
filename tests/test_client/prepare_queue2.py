"""Isolated native/UI diagnostics stand; no hooks in delivered EPF."""
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
run = root / '.local/queue2'
for route in (() if '--refresh' in sys.argv else ('embedded', 'http', 'file')):
    db = run / route / 'db'
    db.mkdir(parents=True)
    shutil.copy2(root / '.local/profile-runtime/db/1Cv8.1CD', db / '1Cv8.1CD')
shutil.copytree(root / '1c/MCPToolkit', run / 'source', dirs_exist_ok='--refresh' in sys.argv)
p = run / 'source/MCPToolkit/Forms/ФормаМенеджераТестирования/Ext/Form/Module.bsl'
s = p.read_text(encoding='utf-8-sig')
s = '&НаКлиенте\nПерем ТестДиагностика;\n' + s
s = s.replace('Процедура НаблюдатьДействиеUI(Шаг, ИсходноеОкно)', 'Процедура НаблюдатьДействиеUI(Шаг, ИсходноеОкно)\n\tЕсли ТестДиагностика = "observe" Тогда ТестДиагностика = ""; ОшибкаUI("value_unavailable"); КонецЕсли;')
s = s.replace('Процедура ДополнитьДиагностикуUI(Шаг)\n\tПопытка', '''Процедура ДополнитьДиагностикуUI(Шаг)
	Попытка
		Если ТестДиагностика = "diagnostic" Тогда ТестДиагностика = ""; ВызватьИсключение "TEST_DIAGNOSTIC_FAILURE"; КонецЕсли;
		Если ТестДиагностика = "budget" Тогда
			ТестДиагностика = "";
			ТекстБюджета = "XXXXXXXX"; Для ИндексБюджета = 1 По 14 Цикл ТекстБюджета = ТекстБюджета + ТекстБюджета; КонецЦикла;
			Шаг.diagnostic_before.Вставить("injected", ТекстБюджета);
		КонецЕсли;''')
s = s.replace('Если Элемент <> Форма.ПолучитьТекущийЭлемент() Тогда', 'Если ТестДиагностика = "editor_changed" И ТипЗнч(Элемент) = Тип("ТестируемаяТаблицаФормы") Тогда ТестДиагностика = ""; Элемент.ПерейтиКСледующемуЭлементу(); КонецЕсли;\n\t\tЕсли Элемент <> Форма.ПолучитьТекущийЭлемент() Тогда')
s += (root / 'tests/test_client/queue2_probes.bsl').read_text(encoding='utf-8-sig')
p.write_text(s, encoding='utf-8-sig')
if '--refresh' in sys.argv:
    raise SystemExit(0)
shutil.copytree(root / 'tests/test_client/permission_fixture', run / 'fixture')
p = run / 'fixture/ApiFixture/Forms/Main/Ext/Form/Module.bsl'
s = p.read_text(encoding='utf-8-sig').replace('Текст = ""; Результат = "0";', '''Текст = ""; Результат = "0";
    Строка = Строки.Добавить(); Строка.Ключ = "ROW1"; Строка.Значение = "COLUMN";
    КомандаОшибки = Команды.Добавить("ОшибкаПриложения");
    КомандаОшибки.Действие = "ОшибкаПриложенияОбработка";
    Кнопка = Элементы.Добавить("ОшибкаПриложения", Тип("КнопкаФормы"));
    Кнопка.ИмяКоманды = "ОшибкаПриложения";
    Кнопка.Заголовок = "QUEUE2 APPLICATION ERROR";''')
s += '''
&НаКлиенте
Процедура ОшибкаПриложенияОбработка(Команда)
    ВызватьИсключение "QUEUE2_APPLICATION_ERROR";
КонецПроцедуры
'''
p.write_text(s, encoding='utf-8-sig')
