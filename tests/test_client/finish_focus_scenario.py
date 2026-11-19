"""Finish-focus runtime acceptance, no recorder, isolated stand only."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/record_native_uilog.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('before = rows()')], 'uilog_helpers', 'exec'))
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from onec_mcp_toolkit_proxy.scenario_contract import preflight_scenario, command_scope, capability_key, digest
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner
from onec_mcp_toolkit_proxy.scenario_import import import_uilog
baseline=rows();save('baseline',baseline)
raw=(root/'openspec/changes/upravlenie-test-klientom/evidence/uilog-native/fresh-uilog.xml').read_bytes()
recording=import_uilog(raw,scenario_id='native-finish-focus',policy_id='isolated-review-only')
params=recording['parameter_values'];text=params['value_001']
w={'selector':{'form_name':'Документ.T43_Required.ФормаОбъекта'}}
el={'selector':{'name':'ОбязательноеПоле','type':'field'}}
finish={'selector':{'name':'Номер','title':'Номер','type':'field'},'same_form':True}
created=click({'selector':{'form_name':'Документ.T43_Required.ФормаСписка'}},'ФормаСоздать')
check('create',created['status']=='succeeded',created)
def input_text(value, condition):
    return call('test_input',action='text',window=w,element=el,params={'text':value,'finish_focus':condition})
def value_is(value):
    return call('test_expect',window=w,element=el,params={'condition':{'property':'value','operator':'equals','value':value}})['status']=='succeeded'
wrong=deepcopy(finish);wrong['selector']={'name':'Дата','type':'field'}
r=input_text(text,wrong);save('before-mismatch',r)
check('wrong_finish_no_mutation',r['status']=='failed' and r['error']['code']=='finish_focus_mismatch' and r['data']['completed_steps']==[] and value_is(''),r)
missing=deepcopy(finish);missing['selector']['name']='НетТакогоПоля'
r=input_text(text,missing);save('before-missing',r)
check('missing_finish_no_mutation',r['status']=='failed' and r['data']['completed_steps']==[] and value_is(''),r)
r=input_text(text,finish);save('guarded-input',r)
check('before_and_after_confirmed',r['status']=='succeeded' and r['data']['finish_focus']=={'before_confirmed':True,'after_confirmed':True} and value_is(text),r)
client_code('ФормаМенеджераТестирования.ПробаНарушитьФокус(); Результат=Истина;')
r=input_text(text+':POST',finish);save('after-mismatch',r)
check('post_mismatch_no_retry',r['status']=='failed' and r['error']['code']=='finish_focus_mismatch' and r['data']['completed_steps']==['activate','input_text','finish_edit'] and r['data']['finish_focus']=={'before_confirmed':True,'after_confirmed':False} and value_is(text+':POST'),r)
# Explicit reviewed local derivative; original recording and draft are preserved.
template=deepcopy(recording['draft']);template.pop('recording_review');template['state']='reviewed';template['revision']=2
template['steps'][0]['arguments']['window']=w
step=deepcopy(template['steps'][0]);step['arguments']['params']['text']=text
now=datetime.now(timezone.utc)
context=dict(owner='isolated-harness',channel_id='queue1',base_id=state['base_id'],approved_base_id=state['base_id'],profile_id='native_document',session_id=sid,generation='1',implementation_revision=state['epf_sha256'],platform=state['platform'],mode='file-http',policy_id=template['data_scope']['policy_id'],capability_revision='finish-focus-runtime-v1',observed_at=now.isoformat(),expires_at=(now+timedelta(minutes=3)).isoformat(),scope_digests=[command_scope(step)],capabilities={},manager_mode=True,session_ready=True,allow_mutation=True,approval_available=True)
context['capabilities'][capability_key(step)]=dict(status='supported',platform=state['platform'],mode='file-http',implementation_revision=state['epf_sha256'],evidence=str(run/'guarded-input.json'))
save('reviewed-template',template);save('runtime-context',context)
save('draft-preflight',preflight_scenario(recording['draft'],params,context))
report=preflight_scenario(template,params,context);save('reviewed-preflight',report)
check('reviewed_preflight_ready',report['status']=='ready',report)
def guard(s,c):
    windows=call('test_inspect',action='windows')
    found=[x for x in windows['data']['windows'] if x['form_name']==w['selector']['form_name']]
    return {'allowed':len(found)==1 and c['session_id']==sid and c['base_id']==state['base_id'],'context_digest':digest(c)}
def transport(tool,args):return call(tool,**args)
result=ScenarioRunner(transport,guard).run(template,params,context);save('runner-result',result)
check('reviewed_scenario_one_dispatch',result['status']=='succeeded' and result['dispatch_count']==1 and result['steps'][0]['result']['data']['finish_focus']['after_confirmed'],result)
final=rows();save('after-data',final);check('no_document_written',baseline==final)
save('finish-focus-summary',{'checks':checks,'source_sha256':recording['source_sha256'],'new_recording':False,'fault_injection':'test EPF only, activate original field after finish_edit','review_scope':'local native form with explicit form_name; original draft remains draft'})
print(json.dumps({'checks':len(checks),'passed':all(c['ok'] for c in checks)},ensure_ascii=True))
