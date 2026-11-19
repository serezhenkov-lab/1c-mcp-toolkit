"""Record one fresh native field edit, import and preserve review evidence. No replay."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
source = (root/'tests/test_client/native_document_scenario.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('connection = code(')], 'native_helpers', 'exec'))

def client_code(text):
    result = call('execute_code', code=text, execution_context='client')
    while isinstance(result, dict) and 'success' in result:
        assert result['success'], result
        result = result.get('data', result.get('result'))
    return result

before = rows()
save('baseline', before)
created = click({'selector': {'form_name': 'Документ.T43_Required.ФормаСписка'}}, 'ФормаСоздать')
assert created.get('status') == 'succeeded', created
w = {'selector': {'form_name': 'Документ.T43_Required.ФормаОбъекта'}}
save('before-record-tree', call('test_inspect', action='tree', window=w))
started = client_code('Результат=ФормаМенеджераТестирования.ПробаНачатьUILog();')
assert started is True, started
try:
    entered = call('test_input', action='text', window=w, element={'selector': {'name': 'ОбязательноеПоле'}}, params={'text': marker})
    save('recorded-action', entered)
finally:
    xml = client_code('Результат=ФормаМенеджераТестирования.ПробаЗавершитьUILog();')
    assert isinstance(xml, str), xml
    (run/'fresh-uilog.xml').write_bytes(xml.encode('utf-8'))
save('after-record-tree', call('test_inspect', action='tree', window=w))
after = rows()
save('after-record-data', after)
assert before == after, 'Recording must not create a document'
from onec_mcp_toolkit_proxy.scenario_import import import_uilog
report = import_uilog(xml, scenario_id='native-recording-851', policy_id='isolated-review-only')
save('import-report', report)
print(json.dumps(dict(status=report['status'], steps=len(report['candidate_steps']), issues=report['issues']), ensure_ascii=True))
