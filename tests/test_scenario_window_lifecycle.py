import unittest
from copy import deepcopy
import test_scenario_context as fixture
from onec_mcp_toolkit_proxy.scenario_contract import capability_key,command_scope

class WindowTests(unittest.TestCase):
 def setUp(self):
  fixture.ContextTests.setUp(self)
  self.step=dict(step_id='absent',tool='test_expect',arguments=dict(window={'selector':{'form_name':'Form.List'}},params={'condition':{'property':'closed','operator':'equals','value':True}}),on_error='stop',timeout_ms=10000)
  self.policy['scope_digests']=[command_scope(self.step)];self.save();self.context=self.provider.create()
  self.windows=[];self.complete=True;original=self.provider._observe
  def observe(tool,args):
   if tool=='test_inspect':return {'data':{'complete':self.complete,'windows':self.windows}}
   return original(tool,args)
  self.provider._observe=observe
 def tearDown(self):fixture.ContextTests.tearDown(self)
 save=fixture.ContextTests.save
 def test_complete_absence_and_unique_presence_allow_observation(self):
  for windows in ([],[{'form_name':'Form.List'}],[{'form_name':'Other'}]):
   self.windows=windows
   self.assertTrue(self.provider.guard(self.step,self.context)['allowed'])
 def test_incomplete_and_ambiguous_never_prove_absence(self):
  self.complete=False;self.assertFalse(self.provider.guard(self.step,self.context)['allowed'])
  self.complete=True;self.windows=[{'form_name':'Form.List'}]*2
  self.assertFalse(self.provider.guard(self.step,self.context)['allowed'])
 def test_field_presence_not_enabled_by_window_capability(self):
  s=deepcopy(self.step);s['arguments']['params']['condition']['property']='exists'
  self.assertEqual(capability_key(s),'test_expect:exists:window:none')
  s['arguments']['element']={'selector':{'name':'field'}}
  self.assertEqual(capability_key(s),'test_expect:exists:scalar:none')
  self.assertNotIn(capability_key(s),self.context['capabilities'])
 def test_mutation_does_not_use_absence_exception(self):
  s=dict(step_id='close',tool='test_action',arguments=dict(action='close',window={'selector':{'form_name':'Form.List'}},params={}),on_error='stop',timeout_ms=10000)
  self.policy['scope_digests']=[command_scope(s)];self.save();context=self.provider.create()
  self.complete=False
  self.assertFalse(self.provider.guard(s,context)['allowed'])
