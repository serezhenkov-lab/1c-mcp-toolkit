import unittest
import test_scenario_context as fixture
from onec_mcp_toolkit_proxy.scenario_context import REGISTRY

class CapabilityTests(unittest.TestCase):
 def setUp(self):fixture.ContextTests.setUp(self)
 def tearDown(self):fixture.ContextTests.tearDown(self)
 save=fixture.ContextTests.save
 def test_new_capabilities_are_route_specific(self):
  new={k for k,v in REGISTRY['capabilities'].items() if isinstance(v,dict)}
  self.assertEqual(len(new),19)
  for route in ('http','file','embedded','unverified'):
   self.binding['transport']=route;c=self.provider.create()
   self.assertEqual(new & set(c['capabilities']),new if route!='unverified' else set())
   if route!='unverified':self.assertIn('test_input:text:finish_focus:none',c['capabilities'])
   else:self.assertEqual(c['capabilities'],{})
 def test_unproven_keys_still_absent(self):
  self.binding['transport']='http';c=self.provider.create()
  for key in ('test_action:click:group:none','test_table:add:table:none','test_input:select:selection_table:none'):
   self.assertNotIn(key,c['capabilities'])
 def test_registry_revision_covers_route_changes(self):
  from onec_mcp_toolkit_proxy.scenario_contract import digest
  from copy import deepcopy
  altered=deepcopy(REGISTRY);altered['capabilities']['test_input:check:scalar:none']['modes'].append('unverified')
  self.assertNotEqual(digest(altered),digest(REGISTRY))
 def test_activation_limitation_is_exposed(self):
  self.binding['transport']='http'
  cap=self.provider.create()['capabilities']['test_action:activate_window:scalar:none']
  self.assertIn('visible',cap['limitations'][0])
