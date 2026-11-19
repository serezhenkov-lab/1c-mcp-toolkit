import unittest
from copy import deepcopy
import test_scenario_context as fixture
from onec_mcp_toolkit_proxy.scenario_contract import command_scope,preflight_scenario

class FieldTests(unittest.TestCase):
 def setUp(self):
  fixture.ContextTests.setUp(self)
  self.node=dict(name='Text',type='field',visible=True,enabled=False,read_only=True,editing=False)
  self.nodes=[self.node];self.complete=True
  original=self.provider._observe
  def observe(tool,args):
   if tool=='test_inspect':return {'data':dict(complete=self.complete,tree=self.nodes)}
   return original(tool,args)
  self.provider._observe=observe
 def tearDown(self):fixture.ContextTests.tearDown(self)
 save=fixture.ContextTests.save
 def authorize(self):
  self.policy['scope_digests']=[command_scope(self.step)];self.save();self.context=self.provider.create()
 def expect(self,prop,value):
  self.step=dict(step_id='observe',tool='test_expect',arguments=dict(window={'selector':{'title':'Fixture'}},element={'selector':{'name':'Text','type':'field'}},params={'condition':{'property':prop,'operator':'equals','value':value}}),on_error='stop',timeout_ms=1000);self.authorize()
 def allowed(self):return self.provider.guard(self.step,self.context)['allowed']
 def test_absence_requires_complete_unambiguous_tree(self):
  self.expect('exists',False);self.nodes=[];self.assertTrue(self.allowed())
  self.complete=False;self.assertFalse(self.allowed());self.complete=True
  self.nodes=[self.node,deepcopy(self.node)];self.assertFalse(self.allowed())
 def test_presence_requires_explicit_field_scope(self):
  self.expect('exists',False);self.step['arguments']['element']['selector'].pop('type');self.authorize();self.assertFalse(self.allowed())
 def test_exists_ignores_interactivity(self):
  self.expect('exists',True);self.node['visible']=False;self.assertTrue(self.allowed())
 def test_disabled_readonly_editing_observations(self):
  for prop,value in [('enabled',False),('read_only',True)]:
   self.expect(prop,value);self.assertTrue(self.allowed())
 def test_editing_without_native_evidence_is_blocked(self):
  self.node['editing']=None;self.expect('editing',False);self.assertFalse(self.allowed())
 def test_unknown_state_is_not_false(self):
  for prop in ('visible','enabled','read_only','editing'):
   self.expect(prop,False);old=self.node[prop];self.node[prop]=None;self.assertFalse(self.allowed());self.node[prop]=old
 def test_absent_state_cannot_be_observed(self):
  self.expect('enabled',False);self.nodes=[];self.assertFalse(self.allowed())
 def test_input_still_blocks_disabled_hidden_readonly(self):
  self.node.update(enabled=True,read_only=False)
  self.authorize();self.assertTrue(self.allowed())
  for prop,value in [('enabled',False),('visible',False),('read_only',True)]:
   old=self.node[prop];self.node[prop]=value;self.assertFalse(self.allowed());self.node[prop]=old
 def test_scalar_text_and_clear_preflight(self):
  self.step.pop('finish_focus');self.authorize()
  for text in ('Новый текст',''):
   self.step['arguments']['params']['text']=text;self.authorize()
   self.assertEqual(preflight_scenario(fixture.ContextTests.template(self),{},self.context)['status'],'ready')
