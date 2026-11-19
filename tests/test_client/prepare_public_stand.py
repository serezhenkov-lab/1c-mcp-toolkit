"""Disposable local profile and autoconnection; production dispatch remains unchanged."""
from pathlib import Path
import re
import shutil
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--file', action='store_true')
parser.add_argument('--revision', default='epf')
parser.add_argument('--fresh-bridge', action='store_true')
args = parser.parse_args()
if not re.fullmatch(r'epf(?:-[a-z0-9]+)?', args.revision):
    parser.error('revision must be epf or epf-<suffix>')

root = Path(__file__).resolve().parents[2]
run = root / ('.local/queue1-file' if args.file else '.local/queue1')
dest = run / args.revision
if dest.exists():
    raise SystemExit('Use a new stand; preserve previous evidence')
shutil.copytree(root / '1c/MCPToolkit', dest)
module = dest / 'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
s = module.read_text(encoding='utf-8-sig')
s = '&НаКлиенте\nПерем ТестФормаПубличногоРазрешения;\n' + s
# Close real approval forms through their normal callback, only in this disposable fixture.
for name in ('ЗапроситьРазрешениеТестирования', 'ПринятьПубличнуюКомандуТестирования'):
    pattern = r'(?:Функция|Процедура) ' + name + r'\(.*?Конец(?:Функции|Процедуры)'
    match = re.search(pattern, s, re.S)
    before = match.group()
    after = before.replace('Возврат ОткрытьФорму(', 'ТестФормаПубличногоРазрешения = ОткрытьФорму(')
    end = 'РежимОткрытияОкнаФормы.Независимый);'
    after = after.replace(end, end + ('\n\tТестФормаПубличногоРазрешения = ФормаРазрешения;' if name.startswith('Принять') else '')
                          + '\n\tПодключитьОбработчикОжидания("ТестОтветПубличногоРазрешения", 3, Истина);'
                          + ('\n\tВозврат ТестФормаПубличногоРазрешения;' if name.startswith('Запросить') else ''))
    s = s[:match.start()] + after + s[match.end():]
opening = re.search(r'Процедура ПриОткрытии\(Отказ\).*?КонецПроцедуры', s, re.S)
pos = opening.end() - len('КонецПроцедуры')
s = s[:pos] + '\tПодключитьОбработчикОжидания("ТестПубличныйСтарт", 1, Истина);\n' + s[pos:]
s += '''
&НаКлиенте
Процедура ТестПубличныйСтарт()
    Профиль = Новый Структура("id,exe,connection,user,port,receipt_path", "queue1",
        КаталогПрограммы() + "1cv8c.exe", СтрокаСоединенияИнформационнойБазы(), "ApiProbe", 16539, "@ROOT@/receipt.json");
    ПолучитьМенеджерТестирования(Профиль);
    АдресСервера = "http://127.0.0.1:17655";
    ИдентификаторКанала = "queue1";
    РежимПодключения = 0;
    Подключиться(Неопределено, Ложь);
    // The fixture explicitly allows only its first manager; restart must reset it.
    Если Не (Новый Файл("@ROOT@/started.txt")).Существует() Тогда
        РежимПодтвержденияОпасныхОпераций = "session_allow";
        Текст = Новый ТекстовыйДокумент; Текст.УстановитьТекст("started"); Текст.Записать("@ROOT@/started.txt");
    КонецЕсли;
КонецПроцедуры

&НаКлиенте
Процедура ТестОтветПубличногоРазрешения()
    Разрешить = Новый Файл("@ROOT@/allow.txt");
    Если ТестФормаПубличногоРазрешения.Открыта() Тогда
        ТестФормаПубличногоРазрешения.Закрыть(Разрешить.Существует());
    КонецЕсли;
КонецПроцедуры
'''.replace('@ROOT@', run.as_posix())
# BSL cannot call a method on a parenthesized constructor on every supported syntax parser.
s = s.replace('Если Не (Новый Файл("' + run.as_posix() + '/started.txt")).Существует() Тогда',
              'ФайлСтарта = Новый Файл("' + run.as_posix() + '/started.txt");\n    Если Не ФайлСтарта.Существует() Тогда')
if args.file:
    bridge = 'bridge-final/queue1' if args.fresh_bridge else 'bridge/queue1'
    s = s.replace('"http://127.0.0.1:17655"', '"file://' + (run / bridge).as_posix() + '"')
    s = s.replace('"ApiProbe", 16539,', '"ApiProbe", 16540,')
module.write_text(s, encoding='utf-8-sig')
