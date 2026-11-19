import unittest
from copy import deepcopy
import test_scenario_context as fixture
from onec_mcp_toolkit_proxy.scenario_contract import capability_key,command_scope,preflight_scenario

class ListMessagesTests(unittest.TestCase):
 def setUp(self):fixture.ContextTests.setUp(self)
 def tearDown(self):fixture.ContextTests.tearDown(self)
 save=fixture.ContextTests.save
 def test_list_and_messages_preflight_all_routes(self):
  steps=[dict(step_id='select',tool='test_input',arguments=dict(action='select',window={'selector':{'title':'Fixture'}},element={'selector':{'name':'Text','type':'field'}},params={'choice':{'list_value':'Choice'}}),on_error='stop',timeout_ms=10000),dict(step_id='messages',tool='test_inspect',arguments=dict(action='messages',window={'selector':{'title':'Fixture'}},params={}),on_error='stop',timeout_ms=10000),dict(step_id='message',tool='test_expect',arguments=dict(window={'selector':{'title':'Fixture'}},params={'condition':{'property':'message','operator':'equals','value':'Message'}}),on_error='stop',timeout_ms=10000)]
  self.policy['scope_digests']=[command_scope(s) for s in steps];self.save()
  template=dict(version=1,scenario_id='list',revision=1,state='reviewed',parameters={},data_scope=dict(policy_id='policy',purpose='unit',mutation='ui_write'),steps=steps)
  for route in ('http','file','embedded'):
   self.binding['transport']=route;c=self.provider.create()
   self.assertEqual(preflight_scenario(template,{},c)['status'],'ready')
  table=deepcopy(steps[0]);table['arguments']['params']['choice']={'selection_window':{'selector':{'title':'Choice'}},'table':{'selector':{'name':'Table'}},'row':{'where':[{'column':'Name','equals':'Choice'}]}}
  self.assertNotIn(capability_key(table),c['capabilities'])
 def test_no_scope_does_not_grant_new_mutation(self):
  self.policy['scope_digests']=[];self.save();c=self.provider.create()
  step=deepcopy(self.step);step.pop('finish_focus');step['arguments'].update(action='select',params={'choice':{'list_value':'Choice'}})
  template=dict(version=1,scenario_id='list',revision=1,state='reviewed',parameters={},data_scope=dict(policy_id='policy',purpose='unit',mutation='ui_write'),steps=[step])
  self.assertEqual(preflight_scenario(template,{},c)['status'],'blocked')
