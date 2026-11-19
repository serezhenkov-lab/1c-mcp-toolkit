"""Prepare research-only probes; never inject them into the production source."""
from pathlib import Path
import subprocess
import sys
import shutil

dest = Path(sys.argv[1]).resolve()
subprocess.run([sys.executable, str(Path(__file__).with_name('prepare_runtime.py')), str(dest), '--input'], check=True)
main = dest / 'MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
text = main.read_text(encoding='utf-8-sig')
anchor = 'ТестВводКоманда("text", "text", Новый Структура("text", "Введено"), "Текст");'
assert text.count(anchor) == 1
text = text.replace(anchor, '''Попытка
            Поиск = ТестДрайвер.ТестНаправленногоПоискаUI();
            ТестПроверка("directed_search_observed", Истина, Поиск);
            Маркер = ТестДрайвер.ТестВыделенияКакМаркераUI();
            ТестПроверка("selection_marker_observed", Истина, Маркер);
            Нативные = ТестДрайвер.ТестНативногоНаблюдателяUI();
            ТестПроверка("native_ids_observed", Истина, Нативные);
        Исключение
            ТестПроверка("row_probe_exception", Ложь, ОписаниеОшибки());
        КонецПопытки;
        ТестФиниш();''')
main.write_text(text, encoding='utf-8-sig')
driver = dest / 'MCPToolkit/Forms/ФормаМенеджераТестирования/Ext/Form/Module.bsl'
with driver.open('a', encoding='utf-8') as out:
    out.write('\n' + Path(__file__).with_name('row_identity_probes.bsl').read_text(encoding='utf-8'))
shutil.copytree(Path(__file__).with_name('input_fixture'), dest / 'fixture')
fixture = dest / 'fixture/ApiFixture/Forms/Main/Ext/Form/Module.bsl'
text = fixture.read_text(encoding='utf-8-sig')
anchor = 'Процедура ПроверитьОбработка(Команда)'
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + '\n    Если Лев(Текст, 9) = "__native_" Тогда Результат = ИсследоватьНативныеСтроки(); Возврат; КонецЕсли;')
fixture.write_text(text + '\n' + Path(__file__).with_name('native_row_observer.bsl').read_text(encoding='utf-8'), encoding='utf-8-sig')
