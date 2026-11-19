from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from test_scenario_runner import scenario,context_for,Transport,guard
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner
from onec_mcp_toolkit_proxy.scenario_store import RunStore
import test_scenario_context as fixture

class Clock(datetime):
 value=None
 @classmethod
 def now(cls,tz=None):return cls.value

class RenewalTests(unittest.TestCase):
 def setUp(self):
  self.t=scenario();self.p={'marker':'once'};self.c=context_for(self.t,self.p);self.c.update(policy_revision='policy-v1',approval_mode='session_allow')
  Clock.value=datetime.now(timezone.utc);self.c['expires_at']=(Clock.value+timedelta(seconds=1)).isoformat()
  for name in ('onec_mcp_toolkit_proxy.scenario_runner.datetime','onec_mcp_toolkit_proxy.scenario_contract.datetime'):
   p=patch(name,Clock);p.start();self.addCleanup(p.stop)
  self.tr=Transport();self.renewals=0;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'runs.sqlite'
 def transport(self,tool,args):
  r=self.tr(tool,args)
  if tool=='test_input':Clock.value+=timedelta(seconds=2)
  return r
 def renew(self,old):
  self.renewals+=1
  return dict(deepcopy(old),observed_at=Clock.value.isoformat(),expires_at=(Clock.value+timedelta(seconds=60)).isoformat())
 def runner(self,**kw):return ScenarioRunner(self.transport,kw.pop('guard',guard),store_path=self.path,refresh_context=kw.pop('refresh_context',self.renew),**kw)
 def test_expired_context_renewed_without_replaying_prefix(self):
  r=self.runner().run(self.t,self.p,self.c)
  self.assertEqual(r['status'],'succeeded');self.assertEqual(r['dispatch_count'],2);self.assertEqual(self.tr.mutations,1)
  self.assertEqual(self.renewals,1);self.assertEqual(r['context_refreshes'][0]['before_step'],'expect')
  saved=RunStore(self.path).load(r['run_id']);self.assertEqual(len(saved['entries']),2)
  self.assertEqual(saved['output']['steps'][0]['operation_id'],self.tr.requests[0][1]['request_id'])
 def test_multiple_renewals_keep_single_mutation(self):
  self.t['steps'].append(deepcopy(self.t['steps'][1]));self.t['steps'][-1]['step_id']='last_read'
  self.c=context_for(self.t,self.p);self.c['observed_at']=Clock.value.isoformat();self.c['expires_at']=(Clock.value+timedelta(seconds=1)).isoformat()
  def slow(tool,args):
   result=self.tr(tool,args);Clock.value+=timedelta(seconds=61);return result
  runner=self.runner();runner._transport=slow;r=runner.run(self.t,self.p,self.c)
  self.assertEqual(r['status'],'succeeded');self.assertEqual(self.renewals,2);self.assertEqual(self.tr.mutations,1);self.assertEqual(r['dispatch_count'],3)
 def test_new_mutation_after_refresh_has_new_id_without_prefix_retry(self):
  self.t['steps'][1]=deepcopy(self.t['steps'][0]);self.t['steps'][1]['step_id']='next_input';self.t['steps'][1]['arguments']['params']['text']='next'
  self.c=context_for(self.t,self.p);self.c['observed_at']=Clock.value.isoformat();self.c['expires_at']=(Clock.value+timedelta(seconds=1)).isoformat()
  r=self.runner().run(self.t,self.p,self.c)
  self.assertEqual(r['status'],'succeeded');self.assertEqual(self.renewals,1);self.assertEqual(len(self.tr.requests),2);self.assertEqual(len({s['request_id'] for s in r['steps']}),2)
 def test_every_authority_change_blocks_new_dispatch(self):
  for k in ('owner','channel_id','base_id','approved_base_id','profile_id','session_id','generation','implementation_revision','platform','mode','policy_id','policy_revision','approval_mode','capability_revision','scope_digests','capabilities','allow_mutation','approval_available','manager_mode','session_ready'):
   with self.subTest(k=k):
    self.tr=Transport();self.c['expires_at']=(Clock.value+timedelta(seconds=1)).isoformat()
    def changed(old):
     fresh=self.renew(old);fresh[k]='different';return fresh
    r=self.runner(refresh_context=changed).run(self.t,self.p,self.c)
    self.assertEqual(r['status'],'partial');self.assertEqual(r['steps'][-1]['result']['error']['code'],'context_refresh_binding_mismatch');self.assertEqual(len(self.tr.requests),1)
 def test_expired_refresh_and_provider_failure_stop(self):
  for callback in (lambda old:old,lambda old: (_ for _ in ()).throw(ValueError('private'))):
   self.tr=Transport();self.c['expires_at']=(Clock.value+timedelta(seconds=1)).isoformat()
   r=self.runner(refresh_context=callback).run(self.t,self.p,self.c)
   self.assertEqual(r['status'],'partial');self.assertEqual(len(self.tr.requests),1);self.assertNotIn('private',str(r))
 def test_extending_expiry_without_new_observation_is_rejected(self):
  def forged(old):
   fresh=self.renew(old);fresh['observed_at']=old['observed_at'];return fresh
  r=self.runner(refresh_context=forged).run(self.t,self.p,self.c)
  self.assertEqual(r['steps'][-1]['result']['error']['code'],'context_refresh_not_fresh');self.assertEqual(len(self.tr.requests),1)
 def test_approval_wait_does_not_renew_or_repeat(self):
  self.tr.fail=lambda *_:dict(status='awaiting_approval')
  r=self.runner().run(self.t,self.p,self.c)
  self.assertEqual(r['status'],'awaiting_approval');self.assertEqual(self.renewals,0);self.assertEqual(self.tr.mutations,1)
 def test_guard_denial_does_not_trigger_refresh_retry(self):
  r=self.runner(guard=lambda *_:{'allowed':False}).run(self.t,self.p,self.c)
  self.assertEqual(r['status'],'blocked');self.assertEqual(self.renewals,0);self.assertEqual(self.tr.requests,[])
 def test_expiry_during_guard_prevents_dispatch(self):
  def slow(step,ctx):Clock.value+=timedelta(seconds=2);return guard(step,ctx)
  r=self.runner(guard=slow).run(self.t,self.p,self.c)
  self.assertEqual(r['status'],'blocked');self.assertEqual(self.renewals,0);self.assertEqual(self.tr.requests,[])
 def test_unknown_is_not_renewal_or_replay(self):
  self.tr.fail=lambda *_:dict(status='unknown')
  r=self.runner().run(self.t,self.p,self.c)
  self.assertEqual(r['status'],'unknown');self.assertEqual(self.renewals,0);self.assertEqual(self.tr.mutations,1)
 def test_persistence_failure_prevents_remaining_dispatch(self):
  runner=self.runner();save=runner._save
  def fail(state):
   if state['output'].get('context_refreshes'):raise OSError('store failed')
   save(state)
  runner._save=fail
  with self.assertRaises(OSError):runner.run(self.t,self.p,self.c)
  self.assertEqual(len(self.tr.requests),1)
 def test_crash_after_refresh_commit_can_resume_without_replay(self):
  class Lost(BaseException):pass
  runner=self.runner();save=runner._save
  def crash(state):
   save(state)
   if state['output'].get('context_refreshes'):raise Lost()
  runner._save=crash
  with self.assertRaises(Lost):runner.run(self.t,self.p,self.c)
  rid=RunStore(self.path).list_runs()[0]['run_id'];state=RunStore(self.path).load(rid)
  r=self.runner().recover(rid,state['context'],resume=True)
  self.assertEqual(r['status'],'succeeded');self.assertEqual(self.tr.mutations,1);self.assertEqual(len(self.tr.requests),2)
 def test_continue_observation_skips_mutations_even_after_renewal(self):
  self.t['steps'][0]['on_error']='continue_observation';self.t['steps'][0],self.t['steps'][1]=self.t['steps'][1],self.t['steps'][0]
  self.t['steps'][0]['on_error']='continue_observation';self.t['steps'][1]['on_error']='stop'
  self.t['steps'].append(deepcopy(self.t['steps'][0]));self.t['steps'][-1]['step_id']='tail'
  self.c=context_for(self.t,self.p);self.c['observed_at']=Clock.value.isoformat();self.c['expires_at']=(Clock.value+timedelta(seconds=1)).isoformat()
  calls=[]
  def transport(tool,args):
   calls.append(tool);reply=self.tr(tool,args)
   if len(calls)==1:Clock.value+=timedelta(seconds=2);reply.update(status='failed',error={'code':'expectation_timeout'})
   return reply
  runner=self.runner();runner._transport=transport;r=runner.run(self.t,self.p,self.c)
  self.assertEqual(r['status'],'partial',r);self.assertEqual(calls,['test_expect','test_expect']);self.assertEqual(self.renewals,1);self.assertEqual(r['steps'][1]['status'],'skipped')

class ProviderRenewalTests(unittest.TestCase):
 def setUp(self):fixture.ContextTests.setUp(self)
 def tearDown(self):fixture.ContextTests.tearDown(self)
 save=fixture.ContextTests.save
 def test_refresh_only_issued_context_and_live_policy(self):
  c=self.provider.create();self.assertEqual(self.provider.refresh(c)['session_id'],c['session_id'])
  forged=deepcopy(c);forged['owner']='other'
  with self.assertRaises(ValueError):self.provider.refresh(forged)
 def test_expired_policy_is_not_extended(self):
  c=self.provider.create();self.policy['expires_at']='2000-01-01T00:00:00Z';self.save()
  with self.assertRaises(ValueError):self.provider.refresh(c)
