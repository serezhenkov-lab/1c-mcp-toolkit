"""12.2 native counter API probe on an isolated stand."""
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
from onec_mcp_toolkit_proxy.step_metrics import StepMetrics
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner
from onec_mcp_toolkit_proxy.scenario_contract import digest
from test_scenario_runner import scenario,context_for


run_name='step-metrics-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
folder=root/'.local'/run_name
(folder/'http/db').mkdir(parents=True)
shutil.copy2(root/'.local/profile-runtime/db/1Cv8.1CD',folder/'http/db/1Cv8.1CD')
toolkit_epf=root/'.local/queue2-final/Toolkit-production.epf'
fixture_epf=root/'.local/queue2-final/Fixture.epf'
source=(root/'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix=source[:source.index('try:\n    barrier =')]
prefix=prefix.replace("'.local/queue1-finish'",repr('.local/'+run_name))
prefix=prefix.replace('17669','17709').replace("str(stand / 'Toolkit.epf')","str(toolkit_epf)")
prefix=prefix.replace("ANONYMIZATION_ENABLED='false'","ANONYMIZATION_ENABLED='false', RESPONSE_FORMAT='json'")
exec(compile(prefix,'scenario_stand_helpers','exec'))
client=httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=20,trust_env=False)
print('stand',run,'port',port,flush=True)

try:
    proxy=start_proxy()
    command=f'"{exe}" ENTERPRISE /IBConnectionString "File=""{run / "db"}"";" /TESTCLIENT -TPort16579 /N ApiProbe /Execute "{fixture_epf}" /DisableStartupDialogs /DisableStartupMessages /Out "{run / "client.log"}"'
    testclient=launch(command,'client')
    for _ in range(120):
        try:
            with socket.create_connection(('127.0.0.1',16579),timeout=.3):break
        except OSError:time.sleep(.5)
    else:raise AssertionError('client_not_ready')
    manager=start_manager()
    time.sleep(3)
    assert manager.poll() is None, (run/"manager.log").read_text(encoding="utf-8-sig",errors="replace")
    print("manager started",flush=True)
    ready()
    print("ready",flush=True)
    code('ТестПрофильID="step_metrics"; ТестПрофильПользователь="ApiProbe"; ТестПрофильПорт=16579; ТестПрофильВключен=Истина; ТестПрофильТребуетПароль=Ложь; СохранитьПрофильТестирования(Неопределено); Результат=ТестПрофильСтатус;')
    attached=complete('test_session',args(action='attach',params={'profile_id':'step_metrics'}))
    assert attached.get('status')=='succeeded',attached
    sid=attached['session_id']
    connection=code('Результат=СтрокаСоединенияИнформационнойБазы();','server')
    assert str((run/'db').resolve()).casefold().replace('\\','/') in str(connection).casefold().replace('\\','/')
    version=code('Информация=Новый СистемнаяИнформация; Результат=Информация.ВерсияПриложения;','server')
    assert version=='8.5.1.1529'
    base_id=hashlib.sha256(str((run/'db').resolve()).casefold().encode()).hexdigest()
    if '--runner' not in sys.argv:
        metrics=code('ПробаМетрик=Новый ТестируемоеПриложение("localhost",16579); ПробаМетрик.УстановитьСоединение(); Результат=Новый Массив; Результат.Добавить(ПробаМетрик.ПолучитьНакопленныеПоказателиПроизводительности(Ложь)); Результат.Добавить(ПробаМетрик.ПолучитьНакопленныеПоказателиПроизводительности(Ложь)); ПробаМетрик.РазорватьСоединение();')
        (run/'native-metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'run':str(run),'metrics':metrics},ensure_ascii=False))
    else:
        samples=[]
        def reader():
            values=code('ПробаМетрик=Новый ТестируемоеПриложение("localhost",16579); ПробаМетрик.УстановитьСоединение(); Результат=ПробаМетрик.ПолучитьНакопленныеПоказателиПроизводительности(Ложь); ПробаМетрик.РазорватьСоединение();')
            value=dict(binding=dict(session_id=sid,client_instance=str(testclient.pid)+':'+run_name,counter_epoch=run_name),values=values)
            samples.append(value)
            return value
        template=scenario();template['steps']=template['steps'][:1]
        step=template['steps'][0];step.update(tool='test_action',arguments=dict(action='select_page',params={},window={'selector':{'title':'Action Fixture'}},element={'selector':{'name':'Вторая'}}),timeout_ms=30000)
        parameters={'marker':'metrics'}
        context=context_for(template,parameters)
        context.update(session_id=sid,base_id=base_id,approved_base_id=base_id,owner='isolated-harness',channel_id='queue1',profile_id='step_metrics')
        def guard(step,context):
            return dict(allowed=manager.poll() is None and testclient.poll() is None,context_digest=digest(context))
        result=ScenarioRunner(call,guard,metrics=StepMetrics(reader)).run(template,parameters,context)
        check('runner_step_result_preserved',result['status']=='succeeded',result)
        metrics=result['steps'][0]['metrics']
        check('metrics_bound_to_execution',metrics['operation_id']==result['steps'][0]['operation_id'] and metrics['step_execution_id']==result['steps'][0]['step_execution_id'],metrics)
        check('native_deltas_available',all(v['available'] and v['value']>=0 for v in metrics['indicators'].values()),metrics)
        def unavailable():raise RuntimeError('injected diagnostic failure')
        degraded=ScenarioRunner(call,guard,metrics=StepMetrics(unavailable)).run(template,parameters,context)
        check('diagnostic_failure_preserves_step',degraded['status']=='succeeded' and not degraded['steps'][0]['metrics']['indicators']['Вызовы']['available'],degraded)
        (run/'runner-metrics.json').write_text(json.dumps(dict(result=result,degraded=degraded,samples=samples),ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'run':str(run),'passed':len(checks)}),flush=True)
    (run/'provenance.json').write_text(json.dumps(dict(platform=version,mode='file-http',base_id=base_id,epf_sha256=hashlib.sha256(toolkit_epf.read_bytes()).hexdigest(),metrics_sha256=hashlib.sha256((root/'onec_mcp_toolkit_proxy/step_metrics.py').read_bytes()).hexdigest(),runner_sha256=hashlib.sha256((root/'onec_mcp_toolkit_proxy/scenario_runner.py').read_bytes()).hexdigest()),indent=2),encoding='utf-8')

finally:
    for process in reversed(owned):stop(process)
    (run/'cleanup.json').write_text(json.dumps({'owned':[p.pid for p in owned],'all_exited':all(p.poll() is not None for p in owned)}),encoding='utf-8')
