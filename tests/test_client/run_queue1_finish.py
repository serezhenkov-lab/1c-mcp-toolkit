"""One isolated batch: negative diagnostics, resolver, commit-before-journal crash."""
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[2]
stand = root / '.local/queue1-finish'
route = sys.argv[1]
run = stand / route
port = {'http': 17669, 'file': 17670, 'embedded': 17671}[route]
exe = r'C:\Program Files\1cv8\8.5.1.1529\bin\1cv8c.exe'
assert not (run / 'results.json').exists(), 'Preserve previous evidence'
owned = []
startupinfo = subprocess.STARTUPINFO()
startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startupinfo.wShowWindow = 0

def launch(command, name, env=None):
    log = (run / (name + '.out')).open('ab')
    p = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=log,
                         startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
    log.close()
    owned.append(p)
    return p

def stop(p):
    if p and p.poll() is None:
        p.terminate()
        p.wait(timeout=20)

def start_proxy():
    if route == 'embedded':
        return None
    env = os.environ.copy()
    env.update(OPERATION_JOURNAL_DIR=str(run / 'journal'), PORT=str(port),
               ANONYMIZATION_ENABLED='false', FILE_BRIDGE_ROOT='', FILE_BRIDGE_CHANNELS='')
    if route == 'file':
        env.update(FILE_BRIDGE_ROOT=str(run / 'bridge'), FILE_BRIDGE_CHANNELS='queue1')
    return launch([sys.executable, '-B', '-m', 'uvicorn', 'onec_mcp_toolkit_proxy.server:app',
                   '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'], 'proxy', env)

def start_manager():
    if route == 'embedded':
        startup = f'startup;mode=embedded;port={port};url=127.0.0.1;auth=password;pwd=;danger_confirm=false'
    else:
        url = f'http://127.0.0.1:{port}' if route == 'http' else 'file://' + (run / 'bridge/queue1').as_posix()
        startup = f'startup;mode=proxy;url={url};channel=queue1;auth=password;pwd=;danger_confirm=false'
    return launch([exe, 'ENTERPRISE', '/F', str(run / 'db'), '/N', 'ApiProbe', '/TESTMANAGER',
                   '/Execute', str(stand / 'Toolkit.epf'), '/C', startup, '/DisableStartupDialogs',
                   '/Out', str(run / 'manager.log')], 'manager')

# Reuse only definitions of the prior test; do not run its already confirmed checks.
shared = (root / 'tests/test_client/run_lost_response.py').read_text(encoding='utf-8')
definitions = shared[shared.index('def save():'):shared.index('for _ in range(60):')]
client = httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=30)
marker = f'UNKNOWN:{route}:{uuid.uuid4().hex}'
events, checks = [], []
exec(compile(definitions, 'lost_response_helpers', 'exec'))

def ready():
    for _ in range(90):
        try:
            if client.get('/health', timeout=1).status_code == 200:
                time.sleep(2)
                code('ФорматОтветаВстроенный=0; ИспользоватьТочнуюАнонимизацию=Ложь; РежимПодтвержденияОпасныхОпераций="session_allow"; Результат=Истина;')
                return
        except (httpx.HTTPError, AssertionError):
            pass
        time.sleep(1)
    raise AssertionError('not ready')

try:
    barrier = stand / 'barrier.json'
    if barrier.exists():
        barrier.rename(run / 'previous-barrier.json')
    proxy = start_proxy()
    # Explicit string preserves the production identity check's /IBConnectionString grammar.
    command = f'"{exe}" ENTERPRISE /IBConnectionString "File=""{run / "db"}"";" /TESTCLIENT -TPort16549 /N ApiProbe /Execute "{stand / "Fixture.epf"}" /DisableStartupDialogs /DisableStartupMessages /Out "{run / "client.log"}"'
    testclient = launch(command, 'client')
    import socket
    for _ in range(120):
        try:
            with socket.create_connection(('127.0.0.1', 16549), timeout=.3):
                break
        except OSError:
            time.sleep(.5)
    else:
        raise AssertionError('TESTCLIENT not ready')
    manager = start_manager()
    ready()
    result = code('ТестПрофильID="queue1_finish"; ТестПрофильПользователь="ApiProbe"; ТестПрофильПорт=16549; ТестПрофильВключен=Истина; ТестПрофильТребуетПароль=Ложь; СохранитьПрофильТестирования(Неопределено); Результат=ТестПрофильСтатус;')
    check('profile', str(result).startswith('Профиль сохранён'), result)
    for _ in range(40):
        state = complete('test_session', args(action='status'))
        if (state.get('error') or {}).get('code') != 'operation_store_unavailable':
            break
        time.sleep(.25)
    attached = complete('test_session', args(action='attach', params={'profile_id': 'queue1_finish'}))
    check('attach', attached.get('status') == 'succeeded', attached)
    sid = attached['session_id']
    windows = complete('test_inspect', args(action='windows', session_id=sid))
    window = {'id': next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])}
    if route == 'embedded':
        probe = code(f'Проба=ПолучитьФорму("ВнешняяОбработка.MCPToolkit.Форма.ФормаМенеджераТестирования",,,Новый УникальныйИдентификатор); Результат=Проба.ПроверкаПричинПроцесса({testclient.pid});')
        for case in probe[:5]:
            check('process_' + case['case'], case['state'] == case['case'] and
                  (case['value'] is True if case['case'] == 'Alive' else case['value'] is False if case['case'] == 'Exited' else case['exception'] is not None), case)
        check('mismatch_stop_unknown_no_ownership', probe[-1]['state'] == 'disconnected' and not probe[-1]['owned'] and probe[-1]['operation']['status'] == 'unknown', probe[-1])
        check('safe_process_error', 'PRIVATE_TEST_SECRET' not in json.dumps(probe), probe)
        props = code('Результат=ФормаМенеджераТестирования.ПроверкаСвойствПредков();')
        check('native_hidden_parent', props[0]['visible']['value'] is False, props[0])
        check('native_child_does_not_inherit_disabled_parent', props[1]['enabled']['value'] is True, props[1])
        tree = complete('test_inspect', args(action='tree', session_id=sid, window=window))
        check('tree_read', tree.get('status') == 'succeeded', tree)
        ambiguous = complete('test_action', args(action='click', session_id=sid, window=window, element={'selector': {'title': 'Одинаковый кандидат'}}))
        resolution = ambiguous.get('data', {}).get('resolution', {})
        check('bounded_ambiguous_candidates', (ambiguous.get('error') or {}).get('code') == 'ambiguous_target' and len(resolution.get('candidates', [])) == 20 and resolution.get('truncated') and resolution.get('exact_matches') == 25, ambiguous)
        check('candidates_readonly_hints', resolution.get('suggestions_only') and ambiguous.get('execution') == 'not_started' and all('path' in c and 'unavailable_reasons' in c for c in resolution['candidates']), resolution)
        for name in ('СкрытаяКнопка', 'НедоступнаяКнопка'):
            denied = complete('test_action', args(action='click', session_id=sid, window=window, element={'selector': {'name': name}}))
            check('parent_guard_' + name, (denied.get('error') or {}).get('code') == 'target_unavailable' and denied.get('execution') == 'not_started', denied)
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
    (run / 'barrier.json').write_text(json.dumps(fault, ensure_ascii=False, indent=2), encoding='utf-8')
    check('callback_success', fault['answer']['status'] == 'succeeded', fault['answer'])
    # File bridge serializes ordinary execute_code behind the unfinished command.
    # The fixture writes its committed trace only after the database write returns.
    before = query() if route != 'file' else [{'reference': traces()[-1]['reference']}]
    check('real_commit_before_crash', len(before) == 1 and len(traces()) == 2, {'rows': before, 'trace': traces()})
    current = call('test_session', args(action='status', params={'operation_id': accepted['operation_id']}))
    check('journal_still_running', current.get('data', {}).get('operation', {}).get('status') == 'running', current)
    stop(manager)
    stop(proxy)
    proxy = start_proxy()
    manager = start_manager()
    ready()
    for _ in range(40):
        state = complete('test_session', args(action='status'))
        if (state.get('error') or {}).get('code') != 'operation_store_unavailable':
            break
        time.sleep(.25)
    for n in range(2):
        replay = call('test_action', write_args)
        check('replay_unknown_' + str(n), replay.get('operation_id') == accepted['operation_id'] and replay.get('status') == 'unknown', replay)
    rows = query()
    check('no_second_document_or_handler', len(rows) == 1 and rows[0]['reference'] == before[0]['reference'] and len(traces()) == 2, {'rows': rows, 'trace': traces()})
    print(json.dumps({'route': route, 'passed': len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
