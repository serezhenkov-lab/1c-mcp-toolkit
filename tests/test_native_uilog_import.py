import json
from copy import deepcopy
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from onec_mcp_toolkit_proxy.scenario_import import import_uilog
from onec_mcp_toolkit_proxy.scenario_contract import preflight_scenario

BASE=Path('openspec/changes/upravlenie-test-klientom')
RAW=(BASE/'evidence/uilog-native/fresh-uilog.xml').read_bytes()
SCHEMA=json.loads((BASE/'contracts/scenario-v1.schema.json').read_text(encoding='utf-8'))

def run(xml):return import_uilog(xml,scenario_id='fresh-native',policy_id='review-only')

class NativeImportTests(unittest.TestCase):
    def test_saved_recording_preserves_three_events_in_review_draft(self):
        r=run(RAW);self.assertEqual(r['status'],'draft')
        Draft202012Validator(SCHEMA).validate(r['draft'])
        self.assertEqual(len(r['draft']['steps']),1)
        c=r['draft']['recording_review']['compositions'][0]
        self.assertEqual([e['event'] for e in c['events']],['activate','inputText','activate'])
        self.assertEqual(c['events'][-1]['element']['selector']['name'],'Номер')
        self.assertIn('confirm_exact_finish_target',c['obligations'])
        self.assertEqual(r['dispatch_count'],0);self.assertFalse(r['execution_ready'])
        self.assertNotIn(next(iter(r['parameter_values'].values())),json.dumps(r['draft'],ensure_ascii=False))

    def test_caption_alias_conflict(self):
        r=run('<uilog><ClientApplicationWindow caption="A" title="B"><activate/></ClientApplicationWindow></uilog>')
        self.assertEqual(r['status'],'blocked')
        self.assertIn('conflicting_window_title',[i['code'] for i in r['issues']])

    def test_repeated_windows_are_ordered_events(self):
        block='<ClientApplicationWindow caption="A"><activate/></ClientApplicationWindow>'
        r=run('<uilog>'+block*2+'</uilog>')
        self.assertEqual(r['status'],'draft');self.assertEqual(len(r['draft']['steps']),2)

    def test_unmatched_activation_never_disappears(self):
        for body in ['<activate/>','<inputText text="x"/><activate/>','<activate/><activate/><inputText text="x"/>']:
            r=run('<uilog><Form title="A"><FormField name="F">'+body+'</FormField></Form></uilog>')
            self.assertEqual(r['status'],'blocked');self.assertIsNone(r['draft'])

    def test_unknown_between_events_blocks_all(self):
        r=run(RAW.replace(b'<inputText',b'<unknown/><inputText'))
        self.assertEqual(r['status'],'blocked');self.assertIsNone(r['draft'])

    def test_unrelated_window_activation_not_composed(self):
        r=run(RAW.replace('T43_required (создание) *'.encode(),'Другой документ'.encode()))
        self.assertEqual(r['status'],'blocked')

    def test_reviewed_flag_cannot_bypass_recording_review(self):
        r=run(RAW);d=r['draft']
        report=preflight_scenario(d,r['parameter_values'],None)
        self.assertNotEqual(report['status'],'ready')
        self.assertIn('recording_requires_review',[i['code'] for i in report['issues']])
        changed=deepcopy(d);changed['state']='reviewed'
        self.assertFalse(Draft202012Validator(SCHEMA).is_valid(changed))
        report=preflight_scenario(changed,r['parameter_values'],None)
        self.assertNotEqual(report['status'],'ready');self.assertEqual(report['dispatch_count'],0)

    def test_schema_copies_match(self):
        self.assertEqual(SCHEMA,json.loads(Path('onec_mcp_toolkit_proxy/scenario-v1.schema.json').read_text(encoding='utf-8')))

if __name__=='__main__':unittest.main()
