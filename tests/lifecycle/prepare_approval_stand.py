"""Isolated real confirmation form with timed, explicitly simulated user decisions."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
file_mode = '--file' in sys.argv
dest = root / ('.local/lifecycle-approval/epf-file' if file_mode else '.local/lifecycle-approval/epf')
subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('prepare_stand.py')), str(dest)], check=True)
module = dest / 'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
s = module.read_text(encoding='utf-8-sig')
s = '&НаКлиенте\nПерем ТестФормаLifecycle;\n&НаКлиенте\nПерем ТестКомандаLifecycle;\n\n' + s
s = s.replace('127.0.0.1:17653', '127.0.0.1:17654').replace('"lifecycle-test"', '"lifecycle-approval"')
if file_mode:
    s = s.replace('http://127.0.0.1:17654', 'file://' + (root / '.local/lifecycle-approval/bridge/lifecycle-approval').as_posix())
s = s.replace('    РежимПодтвержденияОпасныхОпераций = "session_allow";', '    РежимПодтвержденияОпасныхОпераций = "ask";')
s = s.replace('Процедура ДобавитьВЛог(Сообщение)\n', 'Процедура ДобавитьВЛог(Сообщение)\n\tСообщить(Сообщение);\n')
needle = 'Процедура ОбработатьКоманду(Команда)\n'
assert s.count(needle) == 1
s = s.replace(needle, needle + '''
    Если Команда.tool = "execute_code" И Команда.params.Свойство("code") Тогда
        РежимПодтвержденияОпасныхОпераций = ?(СтрНайти(Команда.params.code, "CASE_DENY") > 0, "deny", "ask");
        РежимПодтвержденияПриИзменении(Неопределено);
    КонецЕсли;
''')
needle = '\t\tЕсли ФормаРазрешения = Неопределено Тогда ВызватьИсключение "Не удалось открыть подтверждение опасной операции"; КонецЕсли;'
assert s.count(needle) == 1
s = s.replace(needle, needle + '''
        ТестФормаLifecycle = ФормаРазрешения;
        ТестКомандаLifecycle = Команда;
        ПодключитьОбработчикОжидания("ТестРешениеLifecycle", 3, Истина);
''')
s += '''
&НаКлиенте
Процедура ТестРешениеLifecycle()
    Код = ТестКомандаLifecycle.params.code;
    Если СтрНайти(Код, "CASE_STALE") > 0 Тогда
        РежимПодтвержденияПриИзменении(Неопределено);
        Решение = Истина;
    ИначеЕсли СтрНайти(Код, "CASE_ALLOW") > 0 Тогда
        Решение = Истина;
    ИначеЕсли СтрНайти(Код, "CASE_SESSION") > 0 Тогда
        Решение = "session_allow";
    ИначеЕсли СтрНайти(Код, "CASE_CLOSE") > 0 Тогда
        Решение = Неопределено;
    Иначе
        Решение = Ложь;
    КонецЕсли;
    ТестФормаLifecycle.Закрыть(Решение);
КонецПроцедуры
'''
module.write_text(s, encoding='utf-8-sig')
