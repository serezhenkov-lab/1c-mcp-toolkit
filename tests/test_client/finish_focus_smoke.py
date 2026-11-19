"""Final production EPF: embedded schema and guarded input, no test injection."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/record_native_uilog.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('before = rows()')], 'uilog_helpers', 'exec'))
from onec_mcp_toolkit_proxy.test_client_contract import INPUT_SCHEMAS
from onec_mcp_toolkit_proxy.scenario_import import import_uilog
baseline=rows();save('baseline',baseline)
schemas=json.loads(client_code('ЗаписьПроверки=Новый ЗаписьJSON; ЗаписьПроверки.УстановитьСтроку(); ЗаписатьJSON(ЗаписьПроверки, СхемыТестированияLifecycle()); Результат=ЗаписьПроверки.Закрыть();'))
check('embedded_schemas_equal',schemas==INPUT_SCHEMAS)
raw=(root/'openspec/changes/upravlenie-test-klientom/evidence/uilog-native/fresh-uilog.xml').read_bytes()
r=import_uilog(raw,scenario_id='smoke',policy_id='isolated-review-only')
created=click({'selector':{'form_name':'Документ.T43_Required.ФормаСписка'}},'ФормаСоздать')
assert created['status']=='succeeded',created
step=r['draft']['steps'][0]
a=step['arguments'];a['window']={'selector':{'form_name':'Документ.T43_Required.ФормаОбъекта'}}
a['params']={'text':r['parameter_values']['value_001'],'finish_focus':step['finish_focus']}
reply=call('test_input',**a);save('guarded-input',reply)
check('production_embedded_guard',reply['status']=='succeeded' and reply['data']['finish_focus']=={'before_confirmed':True,'after_confirmed':True},reply)
final=rows();save('after-data',final);check('no_document_written',baseline==final)
save('finish-focus-summary',dict(checks=checks,source_sha256=r['source_sha256'],new_recording=False,fault_injection=False))
