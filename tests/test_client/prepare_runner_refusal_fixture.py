"""Build source for a disposable form that corrects input and counts OnChange."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[2]
stand = root / '.local/runner-refusal-20261117'
fixture = stand / 'fixture'
shutil.copytree(root / 'tests/test_client/action_fixture', fixture)
module = fixture / 'ApiFixture/Forms/Main/Ext/Form/Module.bsl'
source = module.read_text(encoding='utf-8-sig')
needle = 'Процедура ТекстПриИзменении(Элемент)\nКонецПроцедуры'
assert source.count(needle) == 1
source = source.replace(needle, '''Процедура ТекстПриИзменении(Элемент)
    Если СтрНачинаетсяС(Текст, "RUNNER_REJECT:") Тогда
        Текст = СтрЗаменить(Текст, "RUNNER_REJECT:", "RUNNER_CORRECTED:");
        Результат = Строка(Число(Результат) + 1);
    КонецЕсли;
КонецПроцедуры''')
module.write_text(source, encoding='utf-8-sig')
(stand / 'db').mkdir()
shutil.copy2(root / '.local/native-document-20261117T073429/http/db/1Cv8.1CD', stand / 'db/1Cv8.1CD')
print(stand)
