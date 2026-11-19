"""Remaining 8.1/mandatory 8.2 cases only, on a separate disposable base."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("run = stand / route", "run = stand / 'ownership'").replace("'Toolkit.epf'", "'Toolkit-diagnostics.epf'")
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
    probe = code(f'Проба=ПолучитьФорму("ВнешняяОбработка.MCPToolkit.Форма.ФормаМенеджераТестирования",,,Новый УникальныйИдентификатор); Профиль=СобратьЛокальныйПрофильТестирования(НастройкаПрофиляТестирования()); Результат=Проба.ПроверкаЗапретаУправления(Профиль,{testclient.pid});')
    for item in probe:
        answer = item['answer']
        check('mismatch_blocks_' + item['action'], answer['diagnostics']['process_state'] == 'StartTimeMismatch' and not answer['owned'] and answer['error'] is not None and item['proof']['pid'] == testclient.pid and testclient.poll() is None, item)
    print(json.dumps({'route': 'ownership', 'passed': len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
