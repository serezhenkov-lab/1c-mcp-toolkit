"""11.3 isolated HTTP/8.5 stand; only new scenario orchestration checks."""
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
from test_scenario_runner import scenario,context_for
from onec_mcp_toolkit_proxy.scenario_contract import digest
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner

run_name='scenario-runner-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
folder=root/'.local'/run_name
(folder/'http/db').mkdir(parents=True)
shutil.copy2(root/'.local/profile-runtime/db/1Cv8.1CD',folder/'http/db/1Cv8.1CD')
toolkit_epf=root/'.local/queue2-final/Toolkit-production.epf'
fixture_epf=root/'.local/queue2-final/Fixture.epf'
source=(root/'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix=source[:source.index('try:\n    barrier =')]
prefix=prefix.replace("'.local/queue1-finish'",repr('.local/'+run_name))
prefix=prefix.replace('17669','17689').replace("str(stand / 'Toolkit.epf')","str(toolkit_epf)")
prefix=prefix.replace("ANONYMIZATION_ENABLED='false'","ANONYMIZATION_ENABLED='false', RESPONSE_FORMAT='json'")
exec(compile(prefix,'scenario_stand_helpers','exec'))


def context_for_stand(template,parameters):
    context=context_for(template,parameters)
    context.update(owner='isolated-harness',channel_id='queue1',base_id=base_id,approved_base_id=base_id,
        session_id=sid,generation=sid,profile_id='scenario',implementation_revision=epf_hash,
        capability_revision='queue2-production-evidence')
    for cap in context['capabilities'].values():
        cap.update(implementation_revision=epf_hash,evidence='queue2-local.md + task073-partial.md; same production EPF')
    return context


def guard(step,context):
    if manager.poll() is not None or testclient.poll() is not None:return {'allowed':False}
    state=complete('test_session',args(action='status',session_id=sid))
    observed=state.get('observed_state') or {}
    if state.get('status')!='succeeded' or observed.get('session_id')!=sid or observed.get('state')!='ready':
        return {'allowed':False}
    a=step['arguments']
    if a.get('element'):
        exists=complete('test_expect',args(session_id=sid,window=a['window'],element=a['element'],
            params={'condition':{'property':'exists','operator':'equals','value':True}}))
        if exists.get('status')!='succeeded':return {'allowed':False}
    # Public executor resolves unique exact targets and effective availability
    # immediately before invocation; no client observer or cached target IDs.
    return {'allowed':True,'context_digest':digest(context)}


def document_count(value):
    response=call('execute_query',dict(query='ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК n ИЗ Документ.T43_Required ГДЕ ОбязательноеПоле = &Маркер',params={'Маркер':value},limit=2))
    assert response['success'],response
    return response['data'][0]['n']


try:
    proxy=start_proxy()
    command=f'"{exe}" ENTERPRISE /IBConnectionString "File=""{run / "db"}"";" /TESTCLIENT -TPort16559 /N ApiProbe /Execute "{fixture_epf}" /DisableStartupDialogs /DisableStartupMessages /Out "{run / "client.log"}"'
    testclient=launch(command,'client')
    for _ in range(120):
        try:
            with socket.create_connection(('127.0.0.1',16559),timeout=.3):break
        except OSError:time.sleep(.5)
    else:raise AssertionError('client_not_ready')
    manager=start_manager();ready()
    code('ТестПрофильID="scenario"; ТестПрофильПользователь="ApiProbe"; ТестПрофильПорт=16559; ТестПрофильВключен=Истина; ТестПрофильТребуетПароль=Ложь; СохранитьПрофильТестирования(Неопределено); Результат=ТестПрофильСтатус;')
    attached=complete('test_session',args(action='attach',params={'profile_id':'scenario'}))
    assert attached.get('status')=='succeeded',attached
    sid=attached['session_id']
    binding=code('Результат=СтрокаСоединенияИнформационнойБазы();','server')
    assert str((run/'db').resolve()).casefold().replace('\\','/') in str(binding).casefold().replace('\\','/')
    version=code('Информация=Новый СистемнаяИнформация; Результат=Информация.ВерсияПриложения;','server')
    assert version=='8.5.1.1529'
    base_id=hashlib.sha256(str((run/'db').resolve()).casefold().encode()).hexdigest()
    epf_hash=hashlib.sha256(toolkit_epf.read_bytes()).hexdigest()
    template=scenario()
    for step in template['steps']:step['timeout_ms']=30000
    template['steps'].insert(1,dict(step_id='write',tool='test_action',arguments=dict(action='click',params={},
        window={'selector':{'title':'Action Fixture'}},element={'selector':{'name':'Диалог','type':'button'}}),on_error='stop',timeout_ms=30000))
    parameters={'marker':'SCENARIO:'+uuid.uuid4().hex}
    runner=ScenarioRunner(call,guard)
    context=context_for_stand(template,parameters)
    if '--remaining' not in sys.argv:
        invalid=deepcopy(template);invalid['steps'][-1]['tool']='execute_code'
        rejected=runner.run(invalid,parameters,context)
        check('late_invalid_no_dispatch',rejected['status']=='rejected' and rejected['dispatch_count']==0,rejected)
        first=runner.run(template,parameters,context)
        check('first_run_three_steps',first['status']=='succeeded' and len(first['steps'])==3,first)
        check('first_document_once',document_count(parameters['marker'])==1)
        replay=runner.retry_delivery(first['run_id'],'write',plan_digest=first['preflight']['plan_digest'])
        check('same_execution_same_operation',replay.get('operation_id')==first['steps'][1]['operation_id'],replay)
        check('retry_no_duplicate_document',document_count(parameters['marker'])==1)
        other={'marker':'SCENARIO:'+uuid.uuid4().hex}
        second=runner.run(template,other,context_for_stand(template,other))
        check('new_parameters_new_run_and_steps',second['status']=='succeeded' and first['run_id']!=second['run_id'] and
            all(a['request_id']!=b['request_id'] for a,b in zip(first['steps'],second['steps'])),second)
        check('second_document_once',document_count(other['marker'])==1)
    failing=deepcopy(template);failing['steps'][-1].update(tool='test_inspect',arguments=dict(action='values',params={'targets':[{'selector':{'name':'T113_MISSING_FIELD'}}]},window={'selector':{'title':'Action Fixture'}}))
    fail_params={'marker':'SCENARIO:'+uuid.uuid4().hex}
    partial=runner.run(failing,fail_params,context_for_stand(failing,fail_params))
    check('failed_read_keeps_completed_prefix',partial['status']=='partial' and partial['steps'][0]['status']=='succeeded' and partial['steps'][-1]['status']=='failed',partial)
    def lose_write(tool,arguments):
        if tool=='test_action' and arguments.get('action')=='click':
            terminal=complete(tool,arguments)
            assert terminal['status']=='succeeded',terminal
            (run/'lost-runner-reply.json').write_text(json.dumps(terminal,ensure_ascii=False,indent=2),encoding='utf-8')
            raise ConnectionError('injected loss after committed UI write')
        return call(tool,arguments)
    fault_runner=ScenarioRunner(lose_write,guard)
    fault_params={'marker':'SCENARIO:'+uuid.uuid4().hex}
    unknown=fault_runner.run(template,fault_params,context_for_stand(template,fault_params))
    check('lost_reply_unknown_no_next_step',unknown['status']=='unknown' and len(unknown['steps'])==2,unknown)
    denied=fault_runner.retry_delivery(unknown['run_id'],'write',plan_digest=unknown['preflight']['plan_digest'])
    check('unknown_replay_refused',denied.get('reason')=='reconciliation_required',denied)
    check('unknown_write_not_repeated',document_count(fault_params['marker'])==1)
    (run/'provenance.json').write_text(json.dumps(dict(platform=version,mode='file-http',base_id=base_id,
        epf_sha256=epf_hash,fixture_sha256=hashlib.sha256(fixture_epf.read_bytes()).hexdigest(),
        unknown_fault='harness drops terminal reply after UI commit; lifecycle itself succeeded'),indent=2),encoding='utf-8')
    print(json.dumps({'passed':sum(c['ok'] for c in checks),'checks':len(checks)}))
finally:
    for process in reversed(owned):stop(process)
    (run/'cleanup.json').write_text(json.dumps({'owned':[p.pid for p in owned],'all_exited':all(p.poll() is not None for p in owned)}),encoding='utf-8')
