"""Audit captured native MCP results, not a replacement for the live acceptance run."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / '.local/http-mvp'
evidence = json.loads((RUN / 'native-mcp-final-20261117.json').read_text(encoding='utf-8'))
addendum = json.loads((RUN / 'native-mcp-addendum-20261117.json').read_text(encoding='utf-8'))
evidence['calls'].extend(addendum['calls'])
a = evidence['assertions']
checks = []

def decode(result):
    if 'content' not in result:
        return result
    for block in result['content']:
        if block.get('type') == 'text':
            try:
                return json.loads(block['text'])
            except json.JSONDecodeError:
                pass
    return {}

def check(name, condition):
    assert condition, name
    checks.append(name)

operations = {}
for call in evidence['calls']:
    value = decode(call['result'])
    operation = value.get('data', {}).get('operation') if isinstance(value.get('data'), dict) else None
    if not isinstance(operation, dict) or 'request_id' not in operation:
        operation = value
    if 'request_id' in operation:
        operations[operation['request_id']] = operation

cat = decode(a['mvp_catalog_query'])['data']
doc = decode(a['mvp_doc_query'])['data']
check('catalog persisted at exact UID', len(cat) == 1 and cat[0]['Ссылка']['УникальныйИдентификатор'] == '409c3b76-e283-11f1-bb22-88f4dac657c2')
check('document persisted without posting', len(doc) == 1 and doc[0]['Номер'] == 'MVP171101' and doc[0]['СуммаПоДокументу'] == 13.75 and doc[0]['Проведен'] is False and doc[0]['Дата'] == '2099-11-17T10:00:00Z')
check('report result read', any(v.get('value') == 'MVP_RESULT=19,00;VAR=B;DETAIL=0' for v in a['mvp_report_result']['data']['values']))
check('processor changed exact graph day', decode(a['mvp_graph_created'])['data'] == [{'Дата': '2099-01-05T00:00:00Z', 'Значение': 8}])
check('settings restored after reopen', all(v['available'] and v['value'] == '' for v in a['mvp_settings_restored']['data']['values']))
check('clear same native form succeeds', a['mvp_clear_fix_clear']['status'] == 'succeeded' and a['mvp_clear_fix_clear']['data']['actual'] == '')
check('real modal still blocks input', a['mvp_real_modal_final']['data']['input_completion'] == 'blocked_by_other_window')
check('persisted profile starts after restart', a['mvp_profile_restart_result']['data']['state'] == 'ready' and a['mvp_profile_restart_result']['data']['owned'])
check('old UI identity rejected', a['mvp_old_ids_rejected']['error']['code'] == 'stale_target' and a['mvp_old_ids_rejected']['execution'] == 'not_started')
for kind in ('report', 'processor'):
    check('final short link opens ' + kind, a['mvp_final1802_open_' + kind]['status'] == 'succeeded')
check('final activate observed', a['mvp_final1802_activate']['data']['target_active'])
check('final owned client exited', a['mvp_release_stop']['data']['state'] == 'stopped' and a['mvp_release_stop']['data']['diagnostics']['process_state'] == 'Exited' and not a['mvp_release_stop']['data']['owned'])
persisted_stop = decode(a['mvp_package_verified'])['data']['operation']
check('stop survives packaged launcher restart', persisted_stop['operation_id'] == a['mvp_release_stop']['operation_id'] and persisted_stop['status'] == 'succeeded')
check('released mode is ask and journal ready', decode(addendum['mode'])['data'] == {'mode': 'ask', 'healthy': True, 'initializing': False})
user = decode(json.loads((RUN / 'mvp-user-check.json').read_text(encoding='utf-8')))['data']
check('test user full role and disabled platform warning', user == {'user': 'MVPTester', 'warn_dangerous_actions': False, 'full_role': True})
for request_id in ('mvp-catalog-save-fresh-1634', 'mvp-doc-save-1710'):
    deliveries = [c for c in evidence['calls'] if c['tool'] == 'test_action' and c['arguments'].get('request_id') == request_id]
    check('identical replay ' + request_id, len(deliveries) == 2 and deliveries[0]['arguments'] == deliveries[1]['arguments'] and decode(deliveries[0]['result'])['operation_id'] == decode(deliveries[1]['result'])['operation_id'])
for request_id in ('mvp-ask-refuse-detach-1744', 'mvp-deny-open-1744'):
    op = operations[request_id]
    check('permission denies before action ' + request_id, op['execution'] == 'not_started' and op['error']['code'] == 'permission_denied')
check('real menu and section used', any(c['tool'] == 'test_action' and c['arguments'].get('element', {}).get('selector', {}).get('scope') == 'command_interface' for c in evidence['calls']))
check('command bars used', any(c['tool'] == 'test_action' and c['arguments'].get('element', {}).get('selector', {}).get('scope') == 'command_bars' for c in evidence['calls']))
check('screenshot belongs to test client', any('"capture_complete": true' in b['text'] and '"process_id": 43140' in b['text'] and '"target": "test_client"' in b['text'] for b in evidence['screenshot_metadata']))
(RUN / 'native-mcp-audit.json').write_text(json.dumps({'checks': checks, 'passed': len(checks), 'scope': 'captured native evidence; limitations remain in the protocol'}, indent=2), encoding='utf-8')
print(f'{len(checks)} native evidence checks passed')
