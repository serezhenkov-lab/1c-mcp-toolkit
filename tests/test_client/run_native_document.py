"""7.5/7.3 native document stand; controller records only new checks."""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
import hashlib
import json
import shutil
import socket
import sys

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))


run_name='native-document-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
folder=root/'.local'/run_name
selected_route=sys.argv[1]
assert selected_route in ('http','file','embedded')
if any(flag in sys.argv for flag in ('--batch', '--record-uilog', '--probe-uilog-identity', '--finish-focus', '--finish-focus-smoke', '--task021-acceptance', '--task021-observation', '--action-input-probe', '--task021-input', '--scenario-context', '--scenario-recovery')):
    assert '--source-db' in sys.argv and '--epf' in sys.argv, 'Batch requires explicit prepared database and EPF'
(folder/selected_route/'db').mkdir(parents=True)
source_db=Path(sys.argv[sys.argv.index('--source-db')+1]) if '--source-db' in sys.argv else root/'.local/profile-runtime/db'
shutil.copy2(source_db/'1Cv8.1CD',folder/selected_route/'db/1Cv8.1CD')
toolkit_epf=Path(sys.argv[sys.argv.index('--epf')+1]) if '--epf' in sys.argv else root/'.local/queue2-final/Toolkit-production.epf'
fixture_epf=Path(sys.argv[sys.argv.index('--fixture-epf')+1]) if '--fixture-epf' in sys.argv else root/'.local/queue2-final/Fixture.epf'
source=(root/'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix=source[:source.index('try:\n    barrier =')]
prefix=prefix.replace("'.local/queue1-finish'",repr('.local/'+run_name))
prefix=prefix.replace('17669','17719').replace('17670','17720').replace('17671','17721').replace("str(stand / 'Toolkit.epf')","str(toolkit_epf)")
prefix=prefix.replace("ANONYMIZATION_ENABLED='false'","ANONYMIZATION_ENABLED='false', RESPONSE_FORMAT='json'")
exec(compile(prefix,'scenario_stand_helpers','exec'))
client=httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=20,trust_env=False)
print('stand',run,'port',port,flush=True)

try:
    proxy=start_proxy()
    command=f'"{exe}" ENTERPRISE /IBConnectionString "File=""{run / "db"}"";" /TESTCLIENT -TPort16589 /N ApiProbe /Execute "{fixture_epf}" /DisableStartupDialogs /DisableStartupMessages /Out "{run / "client.log"}"'
    hidden_startupinfo=startupinfo
    if '--visible-client' in sys.argv:
        startupinfo=subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow=1
    testclient=launch(command,'client')
    startupinfo=hidden_startupinfo
    for _ in range(120):
        assert testclient.poll() is None, 'test_client_exited_before_ready'
        # Observe our listener without sending an incomplete test-API stream.
        listeners=subprocess.check_output(['netstat','-ano','-p','tcp'],text=True,
                                          creationflags=subprocess.CREATE_NO_WINDOW)
        if any(len(parts)>=5 and parts[1].endswith(':16589') and parts[3]=='LISTENING'
               and parts[4]==str(testclient.pid) for parts in (line.split() for line in listeners.splitlines())):
            break
        time.sleep(.5)
    else:raise AssertionError('client_not_ready')
    # Listener registration precedes completion of the external form startup.
    time.sleep(2)
    manager=start_manager()
    time.sleep(3)
    assert manager.poll() is None, (run/"manager.log").read_text(encoding="utf-8-sig",errors="replace")
    print("manager started",flush=True)
    ready()
    print("ready",flush=True)
    code('ТестПрофильID="native_document"; ТестПрофильПользователь="ApiProbe"; ТестПрофильПорт=16589; ТестПрофильВключен=Истина; ТестПрофильТребуетПароль=Ложь; СохранитьПрофильТестирования(Неопределено); Результат=ТестПрофильСтатус;')
    # HTTP readiness precedes initialization of the embedded lifecycle owner.
    # Poll status only; do not retry attach or any UI mutation.
    for _ in range(40):
        availability=complete('test_session',args(action='status'))
        if (availability.get('error') or {}).get('code') != 'operation_store_unavailable':
            break
        time.sleep(.25)
    else:raise AssertionError('operation_store_not_ready')
    attached=complete('test_session',args(action='attach',params={'profile_id':'native_document'}))
    assert attached.get('status')=='succeeded',attached
    sid=attached['session_id']
    connection=code('Результат=СтрокаСоединенияИнформационнойБазы();','server')
    assert str((run/'db').resolve()).casefold().replace('\\','/') in str(connection).casefold().replace('\\','/')
    version=code('Информация=Новый СистемнаяИнформация; Результат=Информация.ВерсияПриложения;','server')
    assert version=='8.5.1.1529'
    base_id=hashlib.sha256(str((run/'db').resolve()).casefold().encode()).hexdigest()
    windows=complete('test_inspect',args(action='windows',session_id=sid))
    if not any('Action Fixture' in w['title'] for w in windows['data']['windows']):
        diagnostics=[]
        for candidate in windows['data']['windows']:
            if not candidate.get('main'):
                diagnostics.append(complete('test_inspect',args(action='tree',session_id=sid,window={'id':candidate['window_id']},params={'depth':10,'max_nodes':200})))
        (run/'fixture-startup-errors.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2),encoding='utf-8')
        raise AssertionError('fixture_not_open; see fixture-startup-errors.json')
    window={'id':next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])}
    if not any(x in sys.argv for x in ('--task021-input','--scenario-context', '--scenario-recovery')):
        opened=complete('test_open',args(session_id=sid,window=window,params={'link':'e1cib/list/Документ.T43_Required'}))
        assert opened['status']=='succeeded',opened
    windows=complete('test_inspect',args(action='windows',session_id=sid))
    (run/'state.json').write_text(json.dumps(dict(sid=sid,port=port,windows=windows,base_id=base_id,platform=version,epf_sha256=hashlib.sha256(toolkit_epf.read_bytes()).hexdigest()),ensure_ascii=False,indent=2),encoding='utf-8')
    print('READY '+str(run),flush=True)
    if any(flag in sys.argv for flag in ('--batch', '--record-uilog', '--probe-uilog-identity', '--finish-focus', '--finish-focus-smoke', '--task021-acceptance', '--task021-observation', '--action-input-probe', '--task021-input', '--scenario-context', '--scenario-recovery')):
        import subprocess
        controller=('scenario_approval_runtime.py' if '--runner-approval' in sys.argv else
                    'scenario_mutation_failure_runtime.py' if '--mutation-failure' in sys.argv else
                    'scenario_sheet_editing_runtime.py' if '--sheet-editing' in sys.argv else
                    'scenario_editing_runtime.py' if '--editing' in sys.argv else
                    'scenario_refresh_runtime.py' if '--context-refresh' in sys.argv else
                    'scenario_fields_runtime.py' if '--fields' in sys.argv else
                    'scenario_pages_runtime.py' if '--pages' in sys.argv else
                    'scenario_window_lifecycle_runtime.py' if '--window-lifecycle' in sys.argv else
                    'scenario_list_messages_runtime.py' if '--list-messages' in sys.argv else
                    'scenario_capabilities_runtime.py' if '--capabilities' in sys.argv else
                    'scenario_observation_recovery_runtime.py' if '--observation-recovery' in sys.argv else
                    'scenario_recovery_runtime.py' if '--scenario-recovery' in sys.argv else
                    'scenario_context_runtime.py' if '--scenario-context' in sys.argv else
                    'action_input_probe.py' if '--action-input-probe' in sys.argv else
                    'task021_acceptance.py' if any(x in sys.argv for x in ('--task021-acceptance', '--task021-observation', '--action-input-probe', '--task021-input', '--scenario-context', '--scenario-recovery')) else
                    'finish_focus_smoke.py' if '--finish-focus-smoke' in sys.argv else
                    'finish_focus_scenario.py' if '--finish-focus' in sys.argv else
                    'probe_uilog_identity.py' if '--probe-uilog-identity' in sys.argv else
                    'record_native_uilog.py' if '--record-uilog' in sys.argv else 'native_document_scenario.py')
        subprocess.run([sys.executable, '-B', str(root/'tests/test_client'/controller), str(run)] + (['--fields-input-only'] if '--fields-input-only' in sys.argv else []) + (['--observation-only'] if '--task021-observation' in sys.argv else []) + (['--activate-first'] if '--activate-first' in sys.argv else []) + (['--input-only'] if '--task021-input' in sys.argv else []),
                       check=True, timeout=300, startupinfo=startupinfo,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        for _ in range(600):
            if (run/'finish').exists():break
            time.sleep(1)
        else:raise AssertionError('control_timeout')
finally:
    for process in reversed(owned):stop(process)
    (run/'cleanup.json').write_text(json.dumps({'owned':[p.pid for p in owned],'all_exited':all(p.poll() is not None for p in owned)}),encoding='utf-8')
