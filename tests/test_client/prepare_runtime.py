"""Build a disposable copy of the real Toolkit with client-side lifecycle tests."""
import argparse
from pathlib import Path
import re
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('destination', type=Path)
parser.add_argument('--ui', action='store_true')
parser.add_argument('--input', action='store_true')
parser.add_argument('--action', action='store_true')
parser.add_argument('--permission', action='store_true')
parser.add_argument('--table-add', action='store_true')
parser.add_argument('--table-failure', choices=['unknown', 'readback', 'disconnect'])
parser.add_argument('--lifecycle-gate', action='store_true')
parser.add_argument('--transport-gate', action='store_true')
parser.add_argument('--data-policy', action='store_true')
parser.add_argument('--screenshot-target', action='store_true')
parser.add_argument('--acceptance-preflight', action='store_true')
args = parser.parse_args()
if args.acceptance_preflight:
    args.lifecycle_gate = True
if args.screenshot_target:
    args.transport_gate = True
if args.data_policy:
    args.transport_gate = True
if args.transport_gate:
    args.lifecycle_gate = True
if args.lifecycle_gate:
    args.table_add = True
if args.table_failure:
    args.table_add = True
if args.table_add:
    args.input = True
if args.permission:
    args.action = True
if args.action:
    args.input = True
if args.input:
    args.ui = True
root = Path(__file__).resolve().parents[2]
dest = args.destination.resolve()
if not dest.is_relative_to(root / '.local') or dest.exists():
    parser.error('destination must be new and inside .local')
shutil.copytree(root / '1c/MCPToolkit', dest)
module = dest / 'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
text = module.read_text(encoding='utf-8-sig')
text = '\n'.join('&НаКлиенте\nПерем ' + name + ';' for name in
    ['ТестДрайвер', 'ТестЭтап', 'ТестРезультаты', 'ТестСеанс', 'ТестСрок', 'ТестЧужой', 'ТестПрофиль',
     'ТестОкноUI', 'ТестПолеUI', 'ТестСтароеОкноUI', 'ТестСообщенияUI', 'ТестПутьUI', 'ТестОчередьUI']) + '\n' + text
opening = re.search(r'Процедура ПриОткрытии\(Отказ\).*?КонецПроцедуры', text, re.S)
assert opening
end = opening.end() - len('КонецПроцедуры')
text = text[:end] + '\tПодключитьОбработчикОжидания("ТестСеансаСтарт", 1, Истина);\n' + text[end:]
if args.ui:
    text = text.replace('ПодключитьОбработчикОжидания("ТестСеансаСтарт", 1, Истина);',
                        'РежимПодтвержденияОпасныхОпераций = "session_allow";\n\tПодключитьОбработчикОжидания("ТестСеансаСтарт", 1, Истина);')
if args.ui:
    text = text.replace('ПодключитьОбработчикОжидания("ТестСеансаСтарт", 1, Истина);',
                        'ПодключитьОбработчикОжидания("ТестUIСтарт", 1, Истина);')
harness = Path(__file__).with_name('session_tests.bsl').read_text(encoding='utf-8')
harness = harness.replace('@ROOT@', dest.as_posix())
if args.ui:
    harness += '\n' + Path(__file__).with_name('ui_tests.bsl').read_text(encoding='utf-8').replace('@ROOT@', dest.as_posix())
if args.input:
    text = text.replace('"ТестUIСтарт", 1, Истина', '"ТестВводСтарт", 1, Истина')
    harness += '\n' + Path(__file__).with_name('table_add_tests.bsl' if args.table_add else 'input_tests.bsl').read_text(encoding='utf-8').replace('@ROOT@', dest.as_posix())
if args.action:
    text = text.replace('"ТестВводСтарт", 1, Истина', '"ТестДействиеСтарт", 1, Истина')
    harness += '\n' + Path(__file__).with_name('action_tests.bsl').read_text(encoding='utf-8').replace('@ROOT@', dest.as_posix())
if args.permission:
    text = '&НаКлиенте\nПерем ТестИсходноеЧислоДокументов;\n&НаКлиенте\nПерем ТестРешениеРазрешения;\n&НаКлиенте\nПерем ТестОкноРазрешения;\n&НаКлиенте\nПерем ТестЧислоРазрешений;\n' + text
    text = text.replace('"ТестДействиеСтарт", 1, Истина', '"ТестРазрешениеСтарт", 1, Истина')
    anchor = 'Возврат ОткрытьФорму("ВнешняяОбработка.MCPToolkit.Форма.ФормаПодтверждения", Опции, ЭтаФорма,'
    assert text.count(anchor) == 1
    text = text.replace(anchor, 'ТестОкноРазрешения = ОткрытьФорму("ВнешняяОбработка.MCPToolkit.Форма.ФормаПодтверждения", Опции, ЭтаФорма,')
    anchor = 'Токен, , , Новый ОписаниеОповещения("ПослеРазрешенияТестирования", ЭтаФорма, Контекст), РежимОткрытияОкнаФормы.Независимый);'
    text = text.replace(anchor, anchor + '\n\tПодключитьОбработчикОжидания("ТестОтветРазрешения", 1, Истина);\n\tВозврат ТестОкноРазрешения;')
    harness += '\n' + Path(__file__).with_name('permission_tests.bsl').read_text(encoding='utf-8').replace('@ROOT@', dest.as_posix())
    harness = harness.replace('"ТестДействиеГотовность"', '"ТестРазрешениеГотовность"')
if args.lifecycle_gate:
    old = Path(__file__).with_name('table_add_tests.bsl').read_text(encoding='utf-8').replace('@ROOT@', dest.as_posix())
    new = Path(__file__).with_name('lifecycle_gate_tests.bsl').read_text(encoding='utf-8').replace('@ROOT@', dest.as_posix())
    assert harness.count(old) == 1
    harness = harness.replace(old, new)
    text = '&НаКлиенте\nПерем ТестВызовыFallback;\n' + text
    text = text.replace('РежимПодтвержденияОпасныхОпераций = "session_allow";', 'ТестВызовыFallback = 0;\n\tРежимПодтвержденияОпасныхОпераций = "session_allow";', 1)
    method = re.search(r'Функция ВыполнитьКомандуСУчетомКонтекста\(.*?КонецФункции', text, re.S)
    assert method
    original = method.group(0)
    changed = original.replace('Если ПланировщикФормы <> Неопределено Тогда', 'ТестВызовыFallback = ТестВызовыFallback + 1;\n\tВызватьИсключение "TEST_UNSAFE_FALLBACK";\n\tЕсли ПланировщикФормы <> Неопределено Тогда')
    assert changed != original
    text = text.replace(original, changed, 1)
if args.table_failure:
    old = Path(__file__).with_name('table_add_tests.bsl').read_text(encoding='utf-8').replace('@ROOT@', dest.as_posix())
    new = Path(__file__).with_name('table_failure_tests.bsl').read_text(encoding='utf-8').replace('@ROOT@', dest.as_posix()).replace('@FAILURE@', args.table_failure)
    assert harness.count(old) == 1
    harness = harness.replace(old, new)
if args.transport_gate:
    harness = harness.replace('ТестПубличныйОтказ();', 'ТестТранспортныйОтказ(); ТестПубличныйОтказ();')
    harness += '\n' + Path(__file__).with_name('transport_gate_tests.bsl').read_text(encoding='utf-8')
if args.data_policy:
    harness = harness.replace('ТестТранспортныйОтказ();', 'ТестПолитикаДанных(); ТестТранспортныйОтказ();')
    harness += '\n' + Path(__file__).with_name('data_policy_tests.bsl').read_text(encoding='utf-8')
if args.screenshot_target:
    harness = harness.replace('ТестТранспортныйОтказ(); ТестПубличныйОтказ();', 'ТестЦелиСнимка();')
    harness += '\n' + Path(__file__).with_name('screenshot_tests.bsl').read_text(encoding='utf-8').replace('@ROOT@', dest.as_posix())
if args.acceptance_preflight:
    harness = harness.replace('ТестПубличныйОтказ();', 'ТестПриемкаПодготовка();')
    query = Path(__file__).with_name('acceptance-result.sdbl').read_text(encoding='utf-8').strip()
    query_bsl = query.replace('"', '""').replace('\n', '\n\t|')
    harness += '\n' + Path(__file__).with_name('acceptance_preflight_tests.bsl').read_text(encoding='utf-8').replace('@ROOT@', dest.as_posix()).replace('@QUERY@', query_bsl)
module.write_text(text + '\n' + harness, encoding='utf-8-sig')
driver = dest / 'MCPToolkit/Forms/ФормаМенеджераТестирования/Ext/Form/Module.bsl'
driver_text = driver.read_text(encoding='utf-8-sig')
if args.acceptance_preflight:
    driver_text += '\n' + Path(__file__).with_name('acceptance_preflight_probes.bsl').read_text(encoding='utf-8')
if args.data_policy:
    driver_text += '\n' + Path(__file__).with_name('data_policy_probes.bsl').read_text(encoding='utf-8')
if args.action:
    driver_text = '&НаКлиенте\nПерем ТестСбойДействия;\n' + driver_text
    anchor = 'НаблюдатьДействиеUI(Шаг, ЦелевоеОкно.ref);'
    assert driver_text.count(anchor) == 1
    driver_text = driver_text.replace(anchor, 'ТестПослеДействияUI();\n\t' + anchor)
if args.input:
    anchor = '+ " /DisableStartupDialogs /DisableStartupMessages";'
    assert driver_text.count(anchor) == 1
    driver_text = driver_text.replace(anchor, '+ " /Execute " + АргументЗапуска("' + dest.as_posix() + '/InputFixture.epf") ' + anchor)
    driver_text = '&НаКлиенте\nПерем ТестОтказВвода;\n&НаКлиенте\nПерем ТестЧислоВводов;\n' + driver_text
    anchor = 'Поле.ВвестиТекст(Данные.expected);'
    assert driver_text.count(anchor) == 1
    driver_text = driver_text.replace(anchor, anchor + ' ТестПослеВводаUI();')
    anchor = 'Данные.actual = Неопределено;\n\tДанные.actual = ЗначениеВводаUI(Поле, Флажок);'
    assert driver_text.count(anchor) == 1
    driver_text = driver_text.replace(anchor, 'Данные.actual = Неопределено;\n\tТестПередЧтениемUI();\n\tДанные.actual = ЗначениеВводаUI(Поле, Флажок);')
if args.ui:
    driver_text = '&НаКлиенте\nПерем ТестСменаСтроки;\n&НаКлиенте\nПерем ТестЧислоСмен;\n' + driver_text
    anchor = 'ТекстЯчейки = Таблица.ПолучитьТекстЯчейки(Отбор.column);'
    assert driver_text.count(anchor) == 1
    driver_text = driver_text.replace(anchor, anchor + '\n\t\t\tТестМеждуЧтениямиUI(Таблица);')
    driver_text = driver_text.replace('Код = КодИсключенияUI(ОписаниеОшибки());\n\t\tШаг.result.status',
        'Шаг.result.messages.Добавить(ОписаниеОшибки());\n\t\tКод = КодИсключенияUI(ОписаниеОшибки());\n\t\tШаг.result.status')
if args.table_failure:
    driver_text = ''.join('&НаКлиенте\nПерем ' + n + ';\n' for n in
                          ['ТестСбойТаблицы', 'ТестВызовыТаблицы', 'ТестПоколениеТаблицы', 'ТестКлиентЗавершен']) + driver_text
    anchor = 'Таблица.ДобавитьСтроку();'
    assert driver_text.count(anchor) == 1
    driver_text = driver_text.replace(anchor, anchor + '\n\tТестПослеДобавленияСтроки();')
    anchor = 'ШагНаблюдения.status = "unknown";'
    assert driver_text.count(anchor) == 1
    driver_text = driver_text.replace(anchor, anchor + '\n\tТестПередНаблюдениемСтроки();')
    driver_text += '\n' + Path(__file__).with_name('table_failure_probes.bsl').read_text(encoding='utf-8')
driver.write_text(driver_text + '\n' +
    Path(__file__).with_name('driver_probes.bsl').read_text(encoding='utf-8') + '\n' +
    (Path(__file__).with_name('ui_probes.bsl').read_text(encoding='utf-8') if args.ui else '') + '\n' +
    (Path(__file__).with_name('input_probes.bsl').read_text(encoding='utf-8') if args.input else '') + '\n' +
    (Path(__file__).with_name('action_probes.bsl').read_text(encoding='utf-8') if args.action else ''), encoding='utf-8-sig')
if args.permission:
    with driver.open('a', encoding='utf-8') as stream:
        stream.write('\n' + Path(__file__).with_name('permission_probes.bsl').read_text(encoding='utf-8'))
print(dest / 'MCPToolkit.xml')
