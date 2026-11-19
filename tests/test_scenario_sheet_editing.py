import unittest
import test_scenario_fields as fields
import test_scenario_context as context_fixture
from onec_mcp_toolkit_proxy.scenario_contract import capability_key,preflight_scenario

class SheetEditingTests(unittest.TestCase):
 def setUp(self):
  fields.FieldTests.setUp(self);self.node.update(enabled=True,read_only=False,editing=False);self.expect('editing',False)
 def tearDown(self):fields.FieldTests.tearDown(self)
 save=fields.FieldTests.save
 expect=fields.FieldTests.expect
 authorize=fields.FieldTests.authorize
 allowed=fields.FieldTests.allowed
 def test_field_state_is_distinct_from_table_state(self):
  self.assertEqual(capability_key(self.step),'test_expect:editing:field_state:none')
  self.assertEqual(preflight_scenario(context_fixture.ContextTests.template(self),{},self.context)['status'],'ready')
 def test_known_native_boolean_allows_both_states(self):
  for value in (False,True):self.node['editing']=value;self.assertTrue(self.allowed())
 def test_ordinary_field_unavailable_is_still_blocked(self):
  self.node.update(editing=None,unavailable=['editing']);self.assertFalse(self.allowed())
 def test_name_alone_has_no_editing_capability(self):
  self.step['arguments']['element']['selector'].pop('type');self.authorize();self.assertFalse(self.allowed())
 def test_complete_unique_target_required(self):
  self.complete=False;self.assertFalse(self.allowed());self.complete=True;self.nodes=[];self.assertFalse(self.allowed())
