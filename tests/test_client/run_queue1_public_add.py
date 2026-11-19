"""Remaining 8.1/mandatory 8.2 cases only, on a separate disposable base."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("run = stand / route", "run = stand / 'public-add'").replace("'Toolkit.epf'", "'Toolkit-production.epf'")
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
    added = complete('test_table', args(action='add', session_id=sid, window=window, element={'selector': {'name': 'Строки'}}, params={}, timeout_ms=120000))
    check('empty_values_reaches_existing_add_once', added['execution'] == 'invoked' and added['data']['completed_steps'] == ['add'] and (added.get('error') or {}).get('code') == 'incomplete_search', added)
    print(json.dumps({'route': 'public-add-production', 'passed': len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
