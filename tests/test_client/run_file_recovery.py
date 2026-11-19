"""Isolated Windows/1C stand: proxy crash after UI commit, fenced recovery."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
toolkit_epf = root / '.local/file-recovery-20261117/Toolkit-fault.epf'
sys.argv[1:] = ['file']
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("'.local/queue1-finish'", "'.local/file-recovery-20261117'")
prefix = prefix.replace('17670', '17730').replace("str(stand / 'Toolkit.epf')", 'str(toolkit_epf)')
prefix = prefix.replace("ANONYMIZATION_ENABLED='false'", "ANONYMIZATION_ENABLED='false', RESPONSE_FORMAT='json'")
prefix = prefix.replace('timeout=30)', 'timeout=30, trust_env=False)')
exec(compile(prefix, 'file_recovery_helpers', 'exec'))

def wait_health(predicate):
    for _ in range(60):
        try:
            result = client.get('/health', timeout=2).json()
            if predicate(result):
                return result
        except httpx.HTTPError:
            pass
        time.sleep(.5)
    raise AssertionError('recovery health deadline')

try:
    barrier = stand / 'barrier.json'
    assert not barrier.exists(), 'Preserve earlier evidence'
    proxy = start_proxy()
    command = f'"{exe}" ENTERPRISE /IBConnectionString "File=""{run / "db"}"";" /TESTCLIENT -TPort16609 /N ApiProbe /Execute "{stand / "Fixture.epf"}" /DisableStartupDialogs /DisableStartupMessages /Out "{run / "client.log"}"'
    testclient = launch(command, 'client')
    import socket
    for _ in range(120):
        try:
            with socket.create_connection(('127.0.0.1', 16609), timeout=.3):
                break
        except OSError:
            time.sleep(.5)
    else:
        raise AssertionError('TESTCLIENT not ready')
    manager = start_manager()
    time.sleep(3)
    assert manager.poll() is None, 'Manager exited before probe'
    ready()
    version = code('Результат = Новый СистемнаяИнформация; Результат = Результат.ВерсияПриложения;')
    check('platform', version == '8.5.1.1529', version)
    result = code('ТестПрофильID="file_recovery"; ТестПрофильПользователь="ApiProbe"; ТестПрофильПорт=16609; ТестПрофильВключен=Истина; ТестПрофильТребуетПароль=Ложь; СохранитьПрофильТестирования(Неопределено); Результат=ТестПрофильСтатус;')
    check('profile', str(result).startswith('Профиль сохранён'), result)
    attached = complete('test_session', args(action='attach', params={'profile_id': 'file_recovery'}))
    check('attach', attached.get('status') == 'succeeded', attached)
    sid = attached['session_id']
    windows = complete('test_inspect', args(action='windows', session_id=sid))
    window = {'id': next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])}
    filled = complete('test_input', args(action='text', session_id=sid, window=window, element={'selector': {'name': 'Текст'}}, params={'text': marker}))
    check('ui_marker', filled.get('status') == 'succeeded', filled)
    check('before_commit_empty', query() == [] and traces() == [])
    write_args = args(request_id='unknown-' + uuid.uuid4().hex, action='click', session_id=sid, window=window, element={'selector': {'name': 'Диалог'}})
    accepted = call('test_action', write_args)
    for _ in range(120):
        if barrier.exists():
            break
        time.sleep(.25)
    check('callback_before_journal_reached', barrier.exists(), accepted)
    fault = json.loads(barrier.read_text(encoding='utf-8-sig'))
    check('callback_success', fault['answer']['status'] == 'succeeded', fault['answer'])
    check('real_ui_commit', len(traces()) == 2, traces())
    original_reference = traces()[-1]['reference']
    channel = run / 'bridge/queue1'
    pointer = json.loads((channel / 'current.json').read_text(encoding='utf-8-sig'))
    old = channel / pointer['session']
    running = list(old.glob('*.running'))
    check('fenced_running', len(running) == 1 and running[0].with_suffix('.fence.json').exists())
    # Hard process kill; no graceful session cleanup and no manager termination yet.
    proxy.kill()
    proxy.wait(timeout=20)
    proxy = start_proxy()
    health = wait_health(lambda h: any(r.get('reason') == 'executor_busy' for r in h.get('file_recovery', [])))
    check('http_available_while_executor_busy', manager.poll() is None, health)
    check('old_session_revoked_pointer_retained', not (old / 'session.json').exists() and json.loads((channel / 'current.json').read_text()) == pointer)
    replay = call('test_action', write_args)
    check('retry_unknown_while_busy', replay.get('operation_id') == accepted['operation_id'] and replay.get('status') == 'unknown', replay)
    check('no_replay_while_busy', len(traces()) == 2 and running[0].exists())
    stop(manager)
    health = wait_health(lambda h: any(r.get('state') == 'ready' for r in h.get('file_recovery', [])))
    new_pointer = json.loads((channel / 'current.json').read_text())
    check('automatic_new_session', new_pointer['session'] != pointer['session'], health)
    check('old_evidence_preserved', running[0].exists() and (old / 'retired-current.json').exists())
    toolkit_epf = stand / 'Toolkit-production.epf'
    manager = start_manager()
    time.sleep(3)
    assert manager.poll() is None
    ready()
    replay = call('test_action', write_args)
    check('retry_unknown_after_recovery', replay.get('operation_id') == accepted['operation_id'] and replay.get('status') == 'unknown', replay)
    rows = query()
    check('exactly_one_document_and_handler', len(rows) == 1 and rows[0]['reference'] == original_reference and len(traces()) == 2, {'rows': rows, 'trace': traces()})
    import hashlib
    provenance = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (stand / 'Toolkit-fault.epf', toolkit_epf, stand / 'Fixture.epf')}
    (run / 'provenance.json').write_text(json.dumps({'platform': version, 'mode': 'file', 'artifacts': provenance}, indent=2), encoding='utf-8')
    print(json.dumps({'passed': len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
