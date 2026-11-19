"""Only unaccepted TASK-021 transport/form/policy cells. No recording or writes."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/record_native_uilog.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('before = rows()')], 'uilog_helpers', 'exec'))
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from onec_mcp_toolkit_proxy.scenario_contract import preflight_scenario,command_scope,capability_key,digest
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner
from onec_mcp_toolkit_proxy.scenario_import import import_uilog
observation_only='--observation-only' in sys.argv
input_only='--input-only' in sys.argv
baseline=rows();save('baseline',baseline)
raw=(root/'openspec/changes/upravlenie-test-klientom/evidence/uilog-native/fresh-uilog.xml').read_bytes()
imported=import_uilog(raw,scenario_id='task021-acceptance',policy_id='isolated-review-only')
p=imported['parameter_values']
template=deepcopy(imported['draft']);template.pop('recording_review');template['state']='reviewed';template['revision']=3
if run.name=='file':
    w={'selector':{'form_name':'Документ.T43_Required.ФормаОбъекта'}}
    created=click({'selector':{'form_name':'Документ.T43_Required.ФормаСписка'}},'ФормаСоздать')
    assert created['status']=='succeeded',created
    template['steps'][0]['arguments']['window']=w
else:
    assert run.name=='embedded'
    w={'selector':{'title':'Action Fixture'}}
    # Authored scenario on another known fixture, not a reinterpretation of the XML.
    template['scenario_id']='task021-fixture-continue'
    template['steps'][0]['arguments']['window']=w
    template['steps'][0]['arguments']['element']={'selector':{'name':'Текст','type':'field'}}
    template['steps'][0]['finish_focus']={'selector':{'name':'Флаг','type':'field'},'same_form':True}
    template['steps'][0]['arguments']['params']['text']={'$param':'value_001'}
    p={'value_001':'TASK021_FIXTURE:'+uuid.uuid4().hex}
save('before-tree',call('test_inspect',action='tree',window=w))
def step(sid,tool,args,policy='stop'):
    return dict(step_id=sid,tool=tool,arguments=args,on_error=policy,timeout_ms=10000)
el=template['steps'][0]['arguments']['element']
template['steps'].append(step('readback','test_expect',dict(window=w,element=el,params={'condition':{'property':'value','operator':'equals','value':{'$param':'value_001'}}})))
if run.name=='embedded':
    template['steps'] += [step('missing_observation','test_expect',dict(window=w,element={'selector':{'name':'TASK021_NOT_PRESENT'}},params={'condition':{'property':'value','operator':'equals','value':'x'}}),'continue_observation'),
      step('must_skip_mutation','test_input',dict(action='text',window=w,element=el,params={'text':'MUST_NOT_APPEAR'})),
      step('remaining_observation','test_inspect',dict(action='values',window=w,params={'targets':[el]}))]
if input_only:
    template['steps']=template['steps'][:2]
if observation_only:
    assert run.name=='embedded'
    template['steps']=template['steps'][1:]
    p={'value_001':''}
# Fixed known fixture cases are authorized by this isolated acceptance controller.
def resolve(v):
    if isinstance(v,dict):
        if set(v)=={'$param'}:return p[v['$param']]
        return {k:resolve(x) for k,x in v.items()}
    if isinstance(v,list):return [resolve(x) for x in v]
    return v
materialized=resolve(template['steps']);now=datetime.now(timezone.utc)
context=dict(owner='isolated-task021',channel_id='queue1',base_id=state['base_id'],approved_base_id=state['base_id'],profile_id='native_document',session_id=sid,generation='1',implementation_revision=state['epf_sha256'],platform=state['platform'],mode='file-'+run.name,policy_id=template['data_scope']['policy_id'],capability_revision='task021-candidate-acceptance',observed_at=now.isoformat(),expires_at=(now+timedelta(minutes=3)).isoformat(),scope_digests=[command_scope(s) for s in materialized],capabilities={},manager_mode=True,session_ready=True,allow_mutation=True,approval_available=True)
for s in materialized:
    context['capabilities'][capability_key(s)]=dict(status='supported',platform=state['platform'],mode=context['mode'],implementation_revision=state['epf_sha256'],evidence='source-reviewed candidate under acceptance; result must be confirmed by this run')
save('template',template);save('context',context);save('parameters',p)
preflight=preflight_scenario(template,p,context);save('preflight',preflight)
check('new_cell_preflight_ready',preflight['status']=='ready',preflight)
def guard(s,c):
    windows=call('test_inspect',action='windows')
    found=[x for x in windows['data']['windows'] if all(x.get(k)==v for k,v in w['selector'].items())]
    return dict(allowed=len(found)==1 and c['session_id']==sid and c['base_id']==state['base_id'],context_digest=digest(c))
dispatches=[]
def transport(tool,args):
    dispatches.append(dict(tool=tool,args=args))
    return call(tool,**args)
result=ScenarioRunner(transport,guard).run(template,p,context);save('runner-result',result);save('dispatches',dispatches)
if run.name=='file' or input_only:
    check('fixture_input_readback' if input_only else 'file_imported_scenario',result['status']=='succeeded' and result['dispatch_count']==2 and result['steps'][0]['result']['data']['finish_focus']['after_confirmed'],result)
else:
    if not observation_only:check('other_form_guarded_input',result['steps'][0]['status']=='succeeded' and result['steps'][0]['result']['data']['finish_focus']['after_confirmed'],result)
    check('continue_observation_preserves_failure',result['status']=='partial' and [s['status'] for s in result['steps']]==(['succeeded','failed','skipped','succeeded'] if observation_only else ['succeeded','succeeded','failed','skipped','succeeded']),result)
    check('mutation_not_dispatched',result['dispatch_count']==(3 if observation_only else 4) and not any(x['args'].get('params',{}).get('text')=='MUST_NOT_APPEAR' for x in dispatches),dispatches)
    verify=call('test_expect',window=w,element=el,params={'condition':{'property':'value','operator':'equals','value':p['value_001']}})
    check('value_preserved_after_partial',verify['status']=='succeeded',verify)
final=rows();save('after-data',final);check('documents_unchanged',baseline==final)
save('acceptance-summary',dict(checks=checks,route=run.name,source_sha256=imported['source_sha256'],new_recording=False,observation_only=observation_only,input_only=input_only,scope='new transport/form/policy cells only; harness context, not product context provider'))
