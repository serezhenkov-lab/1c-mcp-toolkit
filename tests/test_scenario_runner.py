from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import unittest

from onec_mcp_toolkit_proxy.scenario_contract import preflight_scenario,command_scope,capability_key,digest
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner


def scenario():
    window={'selector':{'title':'Action Fixture'}}
    element={'selector':{'name':'Текст','type':'field'}}
    return dict(version=1,scenario_id='runner',revision=1,state='reviewed',
        parameters={'marker':dict(type='string',required=True)},
        data_scope=dict(policy_id='fixture',purpose='Test',mutation='ui_write'),
        steps=[dict(step_id='input',tool='test_input',arguments=dict(action='text',params={'text':{'$param':'marker'}},window=window,element=element),on_error='stop',timeout_ms=1000),
               dict(step_id='expect',tool='test_expect',arguments=dict(params={'condition':{'property':'value','operator':'equals','value':{'$param':'marker'}}},window=window,element=element),on_error='stop',timeout_ms=1000)])


def context_for(template,parameters):
    def resolve(v):
        if isinstance(v,dict):
            if set(v)=={'$param'}:return parameters[v['$param']]
            return {k:resolve(x) for k,x in v.items()}
        if isinstance(v,list):return [resolve(x) for x in v]
        return v
    steps=resolve(template['steps'])
    now=datetime.now(timezone.utc)
    context=dict(owner='owner',channel_id='channel',base_id='base',approved_base_id='base',
        profile_id='profile',session_id='session',generation='1',implementation_revision='revision',
        platform='8.5.1.1529',mode='file-http',policy_id='fixture',capability_revision='evidence-v1',
        observed_at=now.isoformat(),expires_at=(now+timedelta(minutes=20)).isoformat(),
        scope_digests=[command_scope(s) for s in steps],capabilities={},manager_mode=True,
        session_ready=True,allow_mutation=True,approval_available=True)
    for step in steps:
        context['capabilities'][capability_key(step)]=dict(status='supported',platform=context['platform'],
            mode=context['mode'],implementation_revision='revision',evidence='local-test-double')
    return context


class Transport:
    def __init__(self):self.requests=[];self.ops={};self.mutations=0;self.fail=None
    def __call__(self,tool,args):
        if tool=='test_session':return {'data':{'operation':deepcopy(self.ops.get(args['params']['operation_id'],{}))}}
        self.requests.append((tool,deepcopy(args)))
        key=args['request_id']
        if key in self.ops:return deepcopy(self.ops[key])
        if tool=='test_input':self.mutations+=1
        if self.fail: return self.fail(tool,args)
        reply=dict(status='succeeded',request_id=key,operation_id=key)
        self.ops[key]=reply;return deepcopy(reply)


def guard(step,context):return dict(allowed=True,context_digest=digest(context))


class ScenarioTests(unittest.TestCase):
    def test_new_run_new_ids_and_exact_retry(self):
        t=scenario();p={'marker':'one'};c=context_for(t,p);tr=Transport();runner=ScenarioRunner(tr,guard)
        first=runner.run(t,p,c)
        self.assertEqual(first['status'],'succeeded')
        retried=runner.retry_delivery(first['run_id'],'input',plan_digest=first['preflight']['plan_digest'])
        self.assertEqual(retried['operation_id'],first['steps'][0]['operation_id']);self.assertEqual(tr.mutations,1)
        second=runner.run(t,{'marker':'two'},context_for(t,{'marker':'two'}))
        self.assertNotEqual(first['run_id'],second['run_id']);self.assertEqual(tr.mutations,2)
        self.assertNotEqual(first['steps'][0]['request_id'],second['steps'][0]['request_id'])

    def test_unknown_last_step_prevents_first_mutation(self):
        t=scenario();c=context_for(t,{'marker':'one'});t['steps'][-1]['tool']='execute_code';tr=Transport()
        r=ScenarioRunner(tr,guard).run(t,{'marker':'one'},c)
        self.assertEqual(r['status'],'rejected');self.assertEqual(tr.requests,[])

    def test_parameter_and_runtime_binding_errors(self):
        t=scenario();c=context_for(t,{'marker':'one'})
        for p in ({},{'marker':True},{'marker':'one','extra':'x'}):
            self.assertEqual(preflight_scenario(t,p,c)['status'],'rejected')
        t['steps'][-1]['arguments']['window']={'id':'old'}
        self.assertEqual(preflight_scenario(t,{'marker':'one'},c)['status'],'rejected')

    def test_capability_scope_draft_and_generation_context(self):
        t=scenario();p={'marker':'one'};c=context_for(t,p)
        for key,value in [('capabilities',{}),('scope_digests',[]),('base_id','foreign'),('session_ready',False),('allow_mutation',False),('approval_available',False)]:
            with self.subTest(key=key):
                self.assertEqual(preflight_scenario(t,p,dict(c,**{key:value}))['status'],'blocked')
        t['state']='draft';self.assertEqual(preflight_scenario(t,p,c)['status'],'blocked')

    def test_unknown_after_mutation_stops_without_retry(self):
        t=scenario();p={'marker':'one'};tr=Transport()
        def lost(tool,args):raise ConnectionError('private')
        tr.fail=lost;runner=ScenarioRunner(tr,guard);r=runner.run(t,p,context_for(t,p))
        self.assertEqual(r['status'],'unknown');self.assertEqual(tr.mutations,1);self.assertEqual(len(r['steps']),1)
        denied=runner.retry_delivery(r['run_id'],'input',plan_digest=r['preflight']['plan_digest'])
        self.assertEqual(denied['reason'],'reconciliation_required');self.assertEqual(tr.mutations,1)
        self.assertNotIn('private',json.dumps(r))

    def test_success_without_operation_identity_is_unknown(self):
        t=scenario();p={'marker':'one'};tr=Transport()
        tr.fail=lambda tool,args:dict(status='succeeded')
        r=ScenarioRunner(tr,guard).run(t,p,context_for(t,p))
        self.assertEqual(r['status'],'unknown');self.assertEqual(len(r['steps']),1)

    def test_unknown_tail_forbids_replay_of_successful_prefix(self):
        t=scenario();p={'marker':'one'};tr=Transport()
        def transport(tool,args):
            if tool=='test_expect':raise ConnectionError()
            return tr(tool,args)
        runner=ScenarioRunner(transport,guard);r=runner.run(t,p,context_for(t,p))
        self.assertEqual(r['status'],'unknown')
        self.assertEqual(runner.retry_delivery(r['run_id'],'input',plan_digest=r['preflight']['plan_digest'])['reason'],'reconciliation_required')
        self.assertEqual(tr.mutations,1)

    def test_failed_observation_keeps_failure_and_skips_mutation(self):
        t=scenario();t['steps'].reverse();t['steps'][0]['on_error']='continue_observation'
        tr=Transport();tr.fail=lambda tool,args:dict(status='failed',error={'code':'assertion_failed'})
        r=ScenarioRunner(tr,guard).run(t,{'marker':'one'},context_for(t,{'marker':'one'}))
        self.assertEqual(r['status'],'partial');self.assertEqual(tr.mutations,0)
        self.assertEqual([s['status'] for s in r['steps']],['failed','skipped'])

    def test_approval_rejection_always_stops(self):
        t=scenario();t['steps'].reverse();t['steps'][0]['on_error']='continue_observation';tr=Transport()
        tr.fail=lambda tool,args:dict(status='failed',error={'code':'permission_denied'})
        r=ScenarioRunner(tr,guard).run(t,{'marker':'one'},context_for(t,{'marker':'one'}))
        self.assertEqual(r['status'],'failed');self.assertEqual(len(r['steps']),1)

    def test_runtime_guard_stops_partial_run_on_context_change(self):
        t=scenario();p={'marker':'one'};tr=Transport()
        def changed(step,context):
            return dict(allowed=True,context_digest=digest(context) if step['step_id']=='input' else 'new-generation')
        r=ScenarioRunner(tr,changed).run(t,p,context_for(t,p))
        self.assertEqual(r['status'],'partial');self.assertEqual(len(tr.requests),1)

    def test_lost_runner_state_expiry_and_modified_retry_plan_are_refused(self):
        t=scenario();p={'marker':'one'};tr=Transport();runner=ScenarioRunner(tr,guard)
        r=runner.run(t,p,context_for(t,p))
        self.assertEqual(runner.retry_delivery(r['run_id'],'input',plan_digest='changed')['status'],'rejected')
        tr.ops.clear()
        self.assertEqual(runner.retry_delivery(r['run_id'],'input',plan_digest=r['preflight']['plan_digest'])['status'],'blocked')
        self.assertEqual(ScenarioRunner(tr,guard).retry_delivery(r['run_id'],'input',plan_digest=r['preflight']['plan_digest'])['reason'],'run_state_unavailable')

    def test_json_budgets_duplicate_keys_and_schema_copy(self):
        t=scenario();p={'marker':'one'};c=context_for(t,p)
        self.assertEqual(preflight_scenario('{"version":1,"version":1}',p,c)['status'],'rejected')
        p={'marker':'x'*65537};self.assertEqual(preflight_scenario(t,p,c)['status'],'rejected')
        shipped=json.loads(Path('onec_mcp_toolkit_proxy/scenario-v1.schema.json').read_text(encoding='utf-8'))
        original=json.loads(Path('openspec/changes/upravlenie-test-klientom/contracts/scenario-v1.schema.json').read_text(encoding='utf-8'))
        self.assertEqual(shipped,original)


if __name__=='__main__':unittest.main()
