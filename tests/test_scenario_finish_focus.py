from copy import deepcopy
import unittest
from test_native_uilog_import import run, RAW
from test_scenario_runner import context_for, Transport, guard
from onec_mcp_toolkit_proxy.scenario_contract import preflight_scenario
from onec_mcp_toolkit_proxy.scenario_runner import ScenarioRunner

class FinishFocusTests(unittest.TestCase):
    def setUp(self):
        result=run(RAW);self.d=result['draft'];self.p=result['parameter_values']
    def codes(self,d=None,c=None):
        return {i['code'] for i in preflight_scenario(d or self.d,self.p,c)['issues']}
    def test_import_carries_exact_condition(self):
        self.assertEqual(self.d['steps'][0]['finish_focus'],{'same_form':True,'selector':{'name':'Номер','title':'Номер','type':'field'}})
        self.assertIn('context_unavailable',self.codes())
    def test_changed_or_missing_condition_blocks_review(self):
        for missing in (True,False):
            d=deepcopy(self.d)
            if missing:del d['steps'][0]['finish_focus']
            else:d['steps'][0]['finish_focus']['selector']['name']='Дата'
            self.assertIn('finish_focus_review_mismatch',self.codes(d))
    def test_reviewed_and_fake_support_do_not_allow_dispatch(self):
        d=deepcopy(self.d);d.pop('recording_review');d['state']='reviewed'
        c=context_for(d,self.p);c['policy_id']=d['data_scope']['policy_id'];c['finish_focus_supported']=True;c['capabilities']={}
        t=Transport();r=ScenarioRunner(t,guard).run(d,self.p,c)
        self.assertEqual(r['status'],'blocked');self.assertEqual(r['dispatch_count'],0);self.assertEqual(t.requests,[])
        self.assertIn('capability_unknown',self.codes(d,c))
    def test_supported_guard_is_materialized_for_dispatch(self):
        d=deepcopy(self.d);d.pop('recording_review');d['state']='reviewed'
        c=context_for(d,self.p);c['policy_id']=d['data_scope']['policy_id']
        t=Transport();r=ScenarioRunner(t,guard).run(d,self.p,c)
        self.assertEqual(r['status'],'succeeded');self.assertEqual(r['dispatch_count'],1)
        self.assertEqual(t.requests[0][1]['params']['finish_focus'],d['steps'][0]['finish_focus'])
    def test_conflicting_public_guard_is_rejected(self):
        self.d['steps'][0]['arguments']['params']['finish_focus']={'selector':{'name':'Дата','type':'field'},'same_form':True}
        self.assertIn('invalid_finish_focus',self.codes())
    def test_public_shape_and_embedded_schema(self):
        import json,re
        from pathlib import Path
        from onec_mcp_toolkit_proxy.test_client_contract import INPUT_SCHEMAS, valid_request
        bsl=Path('1c/MCPToolkit/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl').read_text(encoding='utf-8-sig')
        body=bsl.split('Функция СхемыТестированияLifecycle()',1)[1].split('КонецФункции',1)[0]
        decoded=''.join(x.replace('""','"') for x in re.findall(r'^\s*"(.*)"(?: \+|\);)$',body,re.M))
        self.assertEqual(json.loads(decoded),INPUT_SCHEMAS)
        req=dict(request_id='r',session_id='s',window={'selector':{'title':'w'}},element={'selector':{'name':'f'}},action='text',params={'text':'x','finish_focus':self.d['steps'][0]['finish_focus']})
        self.assertTrue(valid_request('test_input',req))
        req['params']['finish_focus']['same_form']=False
        self.assertFalse(valid_request('test_input',req))
    def test_runtime_identifier_rejected(self):
        self.d['steps'][0]['finish_focus']['selector']['id']='old-element'
        self.assertIn('invalid_shape',self.codes())
    def test_not_allowed_for_other_commands(self):
        d=deepcopy(self.d);d.pop('recording_review');d['steps'][0]['tool']='test_action';d['steps'][0]['arguments']['action']='click';d['steps'][0]['arguments']['params']={}
        self.assertIn('invalid_finish_focus',self.codes(d))
    def test_no_guard_on_ordinary_existing_input(self):
        d=deepcopy(self.d);d.pop('recording_review');d['state']='reviewed';d['steps'][0].pop('finish_focus')
        c=context_for(d,self.p);c['policy_id']=d['data_scope']['policy_id']
        self.assertEqual(preflight_scenario(d,self.p,c)['status'],'ready')

if __name__=='__main__':unittest.main()
