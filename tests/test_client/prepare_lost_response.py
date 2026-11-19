"""Fresh disposable bases, unchanged production EPF, and a UI write fixture."""
import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[2]
run = root / '.local/lost-response'
assert not run.exists(), 'Preserve existing evidence'
run.mkdir()
manifest = json.loads((root / 'openspec/changes/upravlenie-test-klientom/evidence/local-profile-manifest.json').read_text(encoding='utf-8'))
for item in manifest['files']:
    if item['path'].startswith('1c/'):
        assert hashlib.sha256((root / item['path']).read_bytes()).hexdigest() == item['sha256'], item['path']
epf = root / '.local/profile-runtime/Toolkit-verified.epf'
assert hashlib.sha256(epf.read_bytes()).hexdigest() == manifest['binaries']['Toolkit-verified.epf']
shutil.copy2(epf, run / 'Toolkit.epf')
for route in ('http', 'file', 'embedded'):
    (run / route / 'db').mkdir(parents=True)
    shutil.copy2(root / '.local/profile-runtime/db/1Cv8.1CD', run / route / 'db/1Cv8.1CD')
shutil.copytree(root / 'tests/test_client/permission_fixture', run / 'fixture')
p = run / 'fixture/ApiFixture/Forms/Main/Ext/Form/Module.bsl'
s = p.read_text(encoding='utf-8-sig')
s = s.replace('    Документ = Документы["T43_Required"].СоздатьДокумент();', '    ТрассаЗаписи("invoked");\n    Документ = Документы["T43_Required"].СоздатьДокумент();')
s = s.replace('    Документ.Записать();', '    Документ.Записать();\n    ТрассаЗаписи("committed", Строка(Документ.Ссылка.УникальныйИдентификатор()));')
s += f'''
&НаСервере
Процедура ТрассаЗаписи(Этап, Ссылка = "")
    ЗаписьJSON = Новый ЗаписьJSON;
    ЗаписьJSON.УстановитьСтроку();
    ЗаписатьJSON(ЗаписьJSON, Новый Структура("stage,marker,reference", Этап, Текст, Ссылка));
    СтрокаJSON = ЗаписьJSON.Закрыть();
    ФайлТрассы = Новый ЗаписьТекста("{run.as_posix()}/ui-invocations.jsonl", КодировкаТекста.UTF8, Символы.ПС, Истина);
    ФайлТрассы.ЗаписатьСтроку(СтрокаJSON);
    ФайлТрассы.Закрыть();
КонецПроцедуры
'''
p.write_text(s, encoding='utf-8-sig')
(run / 'provenance.json').write_text(json.dumps({'production_epf_sha256': hashlib.sha256(epf.read_bytes()).hexdigest(),
    'database_source': '.local/profile-runtime/db/1Cv8.1CD', 'fixture': 'permission_fixture + invocation/commit trace only',
    'routes': ['http', 'file', 'embedded']}, ensure_ascii=False, indent=2), encoding='utf-8')
print(run)
