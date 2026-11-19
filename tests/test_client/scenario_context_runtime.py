"""Product provider + CLI acceptance; harness only starts a disposable stand/grant."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/record_native_uilog.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('before = rows()')], 'uilog_helpers', 'exec'))
from datetime import datetime,timedelta,timezone
from copy import deepcopy
import subprocess,os
from onec_mcp_toolkit_proxy.scenario_context import ScenarioContextProvider,ContextUnavailable
from onec_mcp_toolkit_proxy.scenario_contract import command_scope,preflight_scenario
baseline=rows();save('baseline',baseline)
path=run/'approved-policy.json'
provider=ScenarioContextProvider(f'http://127.0.0.1:{state["port"]}','queue1',path)
binding=provider.binding();save('live-binding',binding)
check('live_session_binding',binding['session_id']==sid and binding['generation']==sid and binding['platform']=='8.5.1.1529' and binding['transport']==run.name,binding)
w={'selector':{'title':'Action Fixture'}};el={'selector':{'name':'Текст','type':'field'}}
text='CONTEXT:'+uuid.uuid4().hex
first=dict(step_id='input',tool='test_input',arguments=dict(action='text',window=w,element=el,params={'text':text}),finish_focus={'selector':{'name':'Флаг','type':'field'},'same_form':True},on_error='stop',timeout_ms=10000)
second=dict(step_id='readback',tool='test_expect',arguments=dict(window=w,element=el,params={'condition':{'property':'value','operator':'equals','value':text}}),on_error='stop',timeout_ms=10000)
template=dict(version=1,scenario_id='product-context-acceptance',revision=1,state='reviewed',parameters={},data_scope={'policy_id':'stand-approved','purpose':'Explicit isolated fixture acceptance','mutation':'ui_write'},steps=[first,second])
# Explicit local authority grants only these two known fixture commands. This is
# not an API that creates grants from an arbitrary caller's scenario.
policy=dict(version=1,channel_id='queue1',approved_base_id=binding['base_id'],profile_id=binding['profile_id'],policy_id='stand-approved',allow_mutation=True,scope_digests=[command_scope(first),command_scope(second)],expires_at=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat())
def policy_write(p):path.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
policy_write(policy)
context=provider.create();save('product-context',context)
check('context_sourced_from_status',all(context[k]==binding[k] for k in ('owner','base_id','profile_id','session_id','generation','implementation_revision','platform')),context)
if run.name=='embedded':
    wrong=deepcopy(policy);wrong['approved_base_id']='other-base';policy_write(wrong)
    try:provider.create();rejected=False
    except ContextUnavailable as err:rejected=str(err)=='base_mismatch'
    check('wrong_base_rejected',rejected)
    wrong=deepcopy(policy);wrong['scope_digests']=[];policy_write(wrong)
    report,newcontext=provider.preflight(template,{})
    check('missing_scope_blocks_before_input',report['status']=='blocked' and report['dispatch_count']==0,report)
    check('policy_change_invalidates_context',provider.guard(first,context)['allowed'] is False)
policy_write(policy)
save('template',template);save('parameters',{})
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
completed=subprocess.run([sys.executable,'-B','-m','onec_mcp_toolkit_proxy.scenario_context','--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(path),'--template',str(run/'template.json'),'--parameters',str(run/'parameters.json'),'--run'],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
(run/'cli.stdout').write_text(completed.stdout,encoding='utf-8');(run/'cli.stderr').write_text(completed.stderr,encoding='utf-8')
result=json.loads(completed.stdout);save('cli-result',result)
check('product_cli_two_steps',completed.returncode==0 and result['status']=='succeeded' and result['dispatch_count']==2 and result['steps'][0]['result']['data']['finish_focus']['after_confirmed'],result)
final=rows();save('after-data',final);check('no_document_written',baseline==final)
if run.name=='embedded':
    detached=call('test_session',action='detach');save('detached',detached)
    try:provider.create();blocked=False
    except ContextUnavailable:blocked=True
    check('detached_session_blocks_context',blocked)
provider.close()
save('provider-summary',dict(checks=checks,product_entrypoint='python -m onec_mcp_toolkit_proxy.scenario_context --run',context_dict_from_harness=False,grant_source='explicit local policy for isolated fixture',new_recording=False))
