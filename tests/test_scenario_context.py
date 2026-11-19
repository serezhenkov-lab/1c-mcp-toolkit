from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json,tempfile,unittest
from pathlib import Path
import httpx
from onec_mcp_toolkit_proxy.scenario_context import ScenarioContextProvider,ContextUnavailable
from onec_mcp_toolkit_proxy.scenario_contract import command_scope,preflight_scenario

class ContextTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'policy.json'
  self.binding=dict(owner='owner',base_id='base',profile_id='profile',generation='session',implementation_revision='scenario-context-v1',base_mode='file',channel_id='channel',transport='embedded',approval_mode='session_allow')
  self.policy=dict(version=1,channel_id='channel',approved_base_id='base',profile_id='profile',policy_id='policy',allow_mutation=True,scope_digests=[],expires_at=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat())
  self.step=dict(step_id='input',tool='test_input',arguments=dict(action='text',window={'selector':{'title':'Fixture'}},element={'selector':{'name':'Text','type':'field'}},params={'text':'test'}),finish_focus={'same_form':True,'selector':{'name':'Finish','type':'field'}},on_error='stop',timeout_ms=1000)
  self.policy['scope_digests']=[command_scope(self.step)];self.save()
  self.calls=[]
  def handle(req):
   args=json.loads(req.content);self.calls.append((req.url.path,args))
   if req.url.path.endswith('test_session'):
    data=dict(state='ready',session_id='session',manager_mode=True,supported=True,platform_version='8.5.1.1529',observed_at=datetime.now(timezone.utc).isoformat(),scenario_binding=self.binding)
   else:data=dict(complete=True,tree=[{'name':'Text','type':'field','visible':True,'enabled':True}])
   return httpx.Response(200,json=dict(status='succeeded',session_id='session',request_id=args['request_id'],data=data))
  self.client=httpx.Client(base_url='http://local',transport=httpx.MockTransport(handle))
  self.provider=ScenarioContextProvider('http://local','channel',self.path,client=self.client)
 def tearDown(self):self.client.close();self.tmp.cleanup()
 def save(self):self.path.write_text(json.dumps(self.policy))
 def template(self):return dict(version=1,scenario_id='test',revision=1,state='reviewed',parameters={},data_scope={'policy_id':'policy','purpose':'test','mutation':'ui_write'},steps=[self.step])
 def test_live_binding_and_guard(self):
  c=self.provider.create();self.assertEqual(c['generation'],'session');self.assertTrue(self.provider.guard(self.step,c)['allowed']);self.assertEqual(preflight_scenario(self.template(),{},c)['status'],'ready')
  self.assertEqual({p for p,a in self.calls},{'/api/test_session','/api/test_inspect'})
 def test_wrong_base_profile_channel_fail_closed(self):
  for field in ('base_id','profile_id','channel_id'):
   old=self.binding[field];self.binding[field]='different'
   with self.assertRaises(ContextUnavailable):self.provider.create()
   self.binding[field]=old
 def test_unknown_revision_has_no_capabilities(self):
  self.binding['implementation_revision']='old';c=self.provider.create();self.assertEqual(c['capabilities'],{});self.assertEqual(preflight_scenario(self.template(),{},c)['status'],'blocked')
 def test_unknown_platform_or_mode(self):
  self.binding['base_mode']='client_server';self.assertEqual(self.provider.create()['capabilities'],{})
 def test_no_implicit_scope_or_mutation_grant(self):
  self.policy['scope_digests']=[];self.policy['allow_mutation']=False;self.save();c=self.provider.create()
  self.assertEqual(preflight_scenario(self.template(),{},c)['status'],'blocked')
 def test_policy_change_invalidates_guard(self):
  c=self.provider.create();self.policy['allow_mutation']=False;self.save();self.assertFalse(self.provider.guard(self.step,c)['allowed'])
 def test_binding_change_invalidates_guard(self):
  for field in ('owner','generation','approval_mode'):
   c=self.provider.create();old=self.binding[field];self.binding[field]='changed';self.assertFalse(self.provider.guard(self.step,c)['allowed']);self.binding[field]=old
 def test_forged_context_not_issued(self):
  c=self.provider.create();c['scope_digests'].append('0'*64);self.assertFalse(self.provider.guard(self.step,c)['allowed'])
 def test_expired_policy_and_denied_approval(self):
  self.binding['approval_mode']='deny';c=self.provider.create();self.assertFalse(c['approval_available']);self.assertFalse(c['allow_mutation'])
  self.policy['expires_at']='2000-01-01T00:00:00Z';self.save()
  with self.assertRaises(ContextUnavailable):self.provider.create()
 def test_context_expiry_is_bounded_by_observation_and_grant(self):
  from onec_mcp_toolkit_proxy.scenario_context import stamp
  self.policy['expires_at']=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat();self.save()
  c=self.provider.create()
  self.assertLessEqual(stamp(c['expires_at']),stamp(c['observed_at'])+timedelta(seconds=60))
  self.assertLessEqual(stamp(c['expires_at']),stamp(self.policy['expires_at']))
 def test_policy_cannot_inject_capabilities(self):
  self.policy['capabilities']={'fake':True};self.save()
  with self.assertRaises(Exception):self.provider.create()

if __name__=='__main__':unittest.main()
