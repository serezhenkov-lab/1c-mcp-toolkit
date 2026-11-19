"""Remaining 8.1/mandatory 8.2 cases only, on a separate disposable base."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("run = stand / route", "run = stand / 'diagnostics'").replace("'Toolkit.epf'", "'Toolkit-diagnostics.epf'")
exec(compile(prefix, 'queue1_helpers', 'exec'))

def flat(nodes):
    for node in nodes:
        yield node
        yield from flat(node.get('children', []))

try:
    import socket
    command = f'"{exe}" ENTERPRISE /IBConnectionString "File=""{run / "db"}"";" /TESTCLIENT -TPort16549 /N ApiProbe /Execute "{stand / "Fixture-diagnostics.epf"}" /DisableStartupDialogs /DisableStartupMessages /Out "{run / "client.log"}"'
    testclient = launch(command, 'client')
    for _ in range(120):
        try:
            with socket.create_connection(('127.0.0.1', 16549), timeout=.3):
                break
        except OSError:
            time.sleep(.5)
    manager = start_manager()
    ready()
    code('ТестПрофильID="queue1_finish"; ТестПрофильПользователь="ApiProbe"; ТестПрофильПорт=16549; ТестПрофильВключен=Истина; ТестПрофильТребуетПароль=Ложь; СохранитьПрофильТестирования(Неопределено); Результат=ТестПрофильСтатус;')
    for case, pid in [('endpoint_mismatch', manager.pid), ('fault_connect', testclient.pid), ('fault_endpoint', testclient.pid)]:
        result = code(f'Проба=ПолучитьФорму("ВнешняяОбработка.MCPToolkit.Форма.ФормаМенеджераТестирования",,,Новый УникальныйИдентификатор); Профиль=СобратьЛокальныйПрофильТестирования(НастройкаПрофиляТестирования()); Результат=Проба.ПроверкаEndpoint(Профиль,{pid},"{case}");')
        if case == 'endpoint_mismatch':
            check(case, result['state'] == 'failed' and result['error']['code'] == 'database_mismatch' and not result['owned'], result)
            check('requested_observed_distinct', result['diagnostics']['requested_endpoint']['port'] == 16549 and result['diagnostics']['observed_endpoint']['process_id'] == testclient.pid, result['diagnostics'])
        else:
            expected = 'endpoint_changed' if case == 'fault_endpoint' else 'api_call_failed'
            error = result['diagnostics']['last_api_error']
            check(case, error['code'] == expected and error['stage'] == 'connect_api' and not result['owned'] and 'PRIVATE_TEST_SECRET' not in json.dumps(result), result)
    for _ in range(40):
        state = complete('test_session', args(action='status'))
        if (state.get('error') or {}).get('code') != 'operation_store_unavailable':
            break
        time.sleep(.25)
    attached = complete('test_session', args(action='attach', params={'profile_id': 'queue1_finish'}))
    check('attach_after_faults', attached.get('status') == 'succeeded', attached)
    sid = attached['session_id']
    windows = complete('test_inspect', args(action='windows', session_id=sid))
    window = {'id': next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])}
    before = code('Результат=ФормаМенеджераТестирования.ПроверкаАктивногоВвода(Истина);')
    tree = complete('test_inspect', args(action='tree', session_id=sid, window=window, timeout_ms=120000))
    check('tree_during_active_input', tree.get('status') == 'succeeded', tree)
    after = code('Результат=ФормаМенеджераТестирования.ПроверкаАктивногоВвода();')
    check('inspect_preserves_active_editor', before == after and before['current'] == 'Текст', {'before': before, 'after': after})
    nodes = {n.get('name'): n for n in flat(tree['data']['tree'])}
    check('unavailable_editing_is_explicit', nodes['Текст']['editing'] is None and nodes['Текст']['unavailable_reasons']['editing'] == 'property_read_failed', nodes['Текст'])
    check('inactive_page_observed_without_activation', nodes['КнопкаВкладки2']['visible'] is False and nodes['КнопкаВкладки1']['visible'] is True, {n: nodes[n]['visible'] for n in ('КнопкаВкладки1', 'КнопкаВкладки2')})
    denied = complete('test_action', args(action='click', session_id=sid, window=window, element={'selector': {'name': 'КнопкаВкладки2'}}, timeout_ms=120000))
    check('inactive_page_action_not_invoked', (denied.get('error') or {}).get('code') == 'target_unavailable' and denied['execution'] == 'not_started', denied)
    for tool, action, name, params in [('test_input', 'text', 'НедоступнаяПоле', {'text': 'MUST_NOT_ENTER'}), ('test_table', 'add', 'НедоступнаяТаблица', {})]:
        denied = complete(tool, args(action=action, session_id=sid, window=window, element={'selector': {'name': name}}, params=params, timeout_ms=120000))
        check('disabled_parent_' + action, (denied.get('error') or {}).get('code') == 'target_unavailable' and denied['execution'] == 'not_started', denied)
    fuzzy = complete('test_action', args(action='click', session_id=sid, window=window, element={'selector': {'name': 'кандидат1'}}, timeout_ms=120000))
    check('no_casefold_fuzzy_selection', (fuzzy.get('error') or {}).get('code') == 'element_not_found' and fuzzy['execution'] == 'not_started' and fuzzy['data']['resolution']['suggestions_only'], fuzzy)
    limited = complete('test_inspect', args(action='tree', session_id=sid, window=window, params={'max_nodes': 1}))
    check('limited_tree_explicit', limited['data']['truncated'] and not limited['data']['complete'] and limited['data']['reason'] == 'max_nodes', limited)
    print(json.dumps({'route': 'diagnostics', 'passed': len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
