import unittest
from copy import deepcopy
import test_scenario_fields as fields
from onec_mcp_toolkit_proxy.scenario_contract import capability_key,preflight_scenario
import test_scenario_context as context_fixture

class EditingTests(unittest.TestCase):
 def setUp(self):
  fields.FieldTests.setUp(self)
  self.node.update(type='table',enabled=True,read_only=False,editing=False)
  self.expect('editing',False);self.step['arguments']['element']['selector']['type']='table';self.authorize()
 def tearDown(self):fields.FieldTests.tearDown(self)
 save=fields.FieldTests.save
 expect=fields.FieldTests.expect
 authorize=fields.FieldTests.authorize
 allowed=fields.FieldTests.allowed
 def test_table_mode_ready_without_row_identity(self):
  self.assertEqual(capability_key(self.step),'test_expect:editing:table_state:none')
  self.assertEqual(preflight_scenario(context_fixture.ContextTests.template(self),{},self.context)['status'],'ready')
  for value in (False,True):self.node['editing']=value;self.assertTrue(self.allowed())
 def test_unmatched_field_and_untyped_target_are_blocked(self):
  for value in ('field',None):
   selector=self.step['arguments']['element']['selector']
   if value:selector['type']=value
   else:selector.pop('type',None)
   self.authorize();self.assertFalse(self.allowed());self.assertEqual(preflight_scenario(context_fixture.ContextTests.template(self),{},self.context)['status'],'ready' if value=='field' else 'blocked')
 def test_unknown_mode_cannot_satisfy_false(self):
  self.node['editing']=None;self.assertFalse(self.allowed())
 def test_incomplete_or_ambiguous_tree_blocks(self):
  self.complete=False;self.assertFalse(self.allowed());self.complete=True;self.nodes.append(deepcopy(self.node));self.assertFalse(self.allowed())
 def test_table_row_mutation_stays_unsupported(self):
  self.step.update(tool='test_table');self.step['arguments'].update(action='add',params={});self.authorize()
  self.assertEqual(preflight_scenario(context_fixture.ContextTests.template(self),{},self.context)['status'],'blocked')
