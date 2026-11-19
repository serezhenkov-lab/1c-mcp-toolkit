import unittest
from copy import deepcopy
import test_scenario_context as fixture
from onec_mcp_toolkit_proxy.scenario_contract import command_scope

class PageTests(unittest.TestCase):
 def setUp(self):
  fixture.ContextTests.setUp(self)
  self.step=dict(step_id='page',tool='test_action',arguments=dict(action='select_page',window={'selector':{'title':'Fixture'}},element={'selector':{'name':'Page','type':'group'}},params={}),on_error='stop',timeout_ms=10000)
  self.node=dict(name='Page',type='group',visible=False,enabled=True)
  self.parent=dict(name='Pages',type='group',visible=True,enabled=True,children=[self.node]);self.complete=True
  self.authorize()
  original=self.provider._observe
  def observe(tool,args):
   if tool=='test_inspect':return {'data':{'complete':self.complete,'tree':[self.parent]}}
   return original(tool,args)
  self.provider._observe=observe
 def tearDown(self):fixture.ContextTests.tearDown(self)
 save=fixture.ContextTests.save
 def authorize(self):
  self.policy['scope_digests']=[command_scope(self.step)];self.save();self.context=self.provider.create()
 def allowed(self):return self.provider.guard(self.step,self.context)['allowed']
 def test_inactive_page_candidate_allowed(self):self.assertTrue(self.allowed())
 def test_hidden_disabled_or_unknown_blocks(self):
  for node,key,value in ((self.parent,'visible',False),(self.parent,'enabled',False),(self.node,'enabled',False),(self.node,'visible',None)):
   old=node[key];node[key]=value;self.assertFalse(self.allowed());node[key]=old
 def test_incomplete_and_ambiguous_block(self):
  self.complete=False;self.assertFalse(self.allowed());self.complete=True
  self.parent['children'].append(deepcopy(self.node));self.assertFalse(self.allowed())
 def test_visibility_can_observe_hidden_but_click_cannot(self):
  self.node['type']='button';self.step['arguments']['element']['selector']['type']='button'
  self.step.update(tool='test_expect');self.step['arguments'].pop('action');self.step['arguments']['params']={'condition':{'property':'visible','operator':'equals','value':False}};self.authorize()
  self.assertTrue(self.allowed())
  self.step.update(tool='test_action');self.step['arguments'].update(action='click',params={});self.authorize()
  self.assertFalse(self.allowed())
 def test_button_not_accepted_as_page(self):
  self.node['type']='button';self.step['arguments']['element']['selector']['type']='button';self.authorize()
  self.assertFalse(self.allowed())
