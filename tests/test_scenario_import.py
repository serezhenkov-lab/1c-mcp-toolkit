from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from onec_mcp_toolkit_proxy.scenario_import import import_uilog


def form(body, attrs='title="Заказ"'):
    return f'<uilog><ClientApplicationWindow title="1С" isMain="true"><Form {attrs}>{body}</Form></ClientApplicationWindow></uilog>'


def run(source):
    return import_uilog(source,scenario_id='recording-1',policy_id='fixture-only')


class ImportTests(unittest.TestCase):
    def test_supported_events_produce_schema_valid_draft_in_order(self):
        xml=form('<activate/><FormField name="Комментарий"><inputText text="Пример"/></FormField>'
                 '<FormField name="Флаг"><setCheck/></FormField>'
                 '<FormButton name="Записать"><click/></FormButton><close/>')
        result=run(xml)
        self.assertEqual(result['status'],'draft')
        draft=result['draft']
        schema=json.loads(Path('openspec/changes/upravlenie-test-klientom/contracts/scenario-v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(draft)
        self.assertEqual([s['arguments']['action'] for s in draft['steps']],['activate_window','text','check','click','close'])
        self.assertEqual(result['parameter_values'],{'value_002':'Пример'})
        self.assertNotIn('Пример',json.dumps(draft,ensure_ascii=False))
        self.assertEqual(draft['state'],'draft')
        self.assertTrue(all(s['on_error']=='stop' for s in draft['steps']))
        self.assertEqual(result['dispatch_count'],0)
        self.assertFalse(result['execution_ready'])
        self.assertEqual(len(result['targets_requiring_review']),5)

    def test_unknown_last_event_never_returns_successful_prefix(self):
        result=run(form('<FormButton name="OK"><click/></FormButton><futureAction/>'))
        self.assertEqual(result['status'],'blocked'); self.assertIsNone(result['draft'])
        self.assertEqual(len(result['candidate_steps']),1)
        issue=next(i for i in result['issues'] if i['code']=='unknown_event')
        self.assertEqual(issue['node_type'],'futureAction')
        self.assertEqual(len(issue['node_sha256']),64)
        self.assertTrue(issue['path'].startswith('/uilog/'))

    def test_duplicate_sibling_targets_are_not_chosen(self):
        result=run(form('<FormButton title="OK"><click/></FormButton>'*2))
        self.assertIsNone(result['draft'])
        self.assertIn('ambiguous_recorded_target',[i['code'] for i in result['issues']])

    def test_missing_target_and_active_window_not_invented(self):
        for xml in ['<uilog><click/></uilog>',form('<FormButton><click/></FormButton>'),form('<activate/>',attrs='')]:
            with self.subTest(xml=xml):
                self.assertIsNone(run(xml)['draft'])

    def test_recorded_context_is_discarded_and_not_parameterized(self):
        xml=form('<FormField name="Поле" id="native"><inputText text="value"/></FormField>',
                 attrs='title="Заказ" session_id="old-session" port="1234" password="secret"')
        result=run(xml)
        self.assertEqual(result['status'],'draft')
        for private in ('old-session','1234','secret','native'):
            self.assertNotIn(private,json.dumps(result,ensure_ascii=False))
        self.assertEqual(result['parameter_values'],{'value_001':'value'})
        self.assertIn('recorded_context_discarded',[i['code'] for i in result['issues']])

    def test_code_events_block_but_input_text_is_inert_data(self):
        for tag in ('script','execute_code','BSL'):
            result=run(form(f'<{tag}>Выполнить("код")</{tag}>'))
            self.assertIsNone(result['draft'])
            self.assertIn('forbidden_event',[i['code'] for i in result['issues']])
            self.assertNotIn('Выполнить',json.dumps(result,ensure_ascii=False))
        result=run(form('<FormField name="Поле"><inputText text="Выполнить(&quot;код&quot;); ${env.PASSWORD}"/></FormField>'))
        self.assertEqual(result['status'],'draft')
        self.assertEqual(result['parameter_values']['value_001'],'Выполнить("код"); ${env.PASSWORD}')

    def test_unknown_attributes_and_children_are_not_ignored(self):
        for body in ['<FormButton name="OK"><click code="x"/></FormButton>',
                     '<FormButton name="OK"><click><script/></click></FormButton>',
                     '<FormField name="Поле" passwordMode="true"><inputText text="private"/></FormField>']:
            self.assertIsNone(run(form(body))['draft'])

    def test_unsupported_table_group_click_and_open_are_explicit(self):
        for body in ['<FormTable name="Строки"><click/></FormTable>',
                     '<FormGroup name="Карточка"><click/></FormGroup>',
                     '<FormField name="Поле"><open/></FormField>']:
            result=run(form(body)); self.assertEqual(result['status'],'blocked')
            self.assertIsNone(result['draft']); self.assertTrue(result['issues'])

    def test_no_external_entities_dtd_or_processing_instructions(self):
        for xml in ['<!DOCTYPE uilog [<!ENTITY x SYSTEM "file:///C:/private">]><uilog>&x;</uilog>',
                    '<uilog><?run code?></uilog>']:
            self.assertIsNone(run(xml)['draft'])
        self.assertEqual(run('<uilog>')['status'],'rejected')
        self.assertEqual(run('<other/>')['status'],'rejected')

    def test_input_depth_node_and_step_budgets(self):
        self.assertEqual(run('x'*(1024*1024+1))['status'],'rejected')
        self.assertEqual(run('<uilog>'+'<Form>'*33+'</Form>'*33+'</uilog>')['status'],'rejected')
        self.assertEqual(run('<uilog>'+'<x/>'*10001+'</uilog>')['status'],'rejected')
        result=run(form('<FormButton name="OK">'+'<click/>'*101+'</FormButton>'))
        self.assertIsNone(result['draft']); self.assertEqual(len(result['candidate_steps']),100)
        result=run(form('<FormField name="Поле">'+'<inputText text="x"/>'*101+'</FormField>'))
        self.assertEqual(len(result['parameter_values']),100)
        self.assertIsNone(result['draft'])

    def test_nested_root_does_not_inherit_target_context(self):
        result=run(form('<uilog><activate/></uilog>'))
        self.assertIsNone(result['draft'])
        self.assertIn('unsupported_hierarchy',[i['code'] for i in result['issues']])

    def test_unknown_events_are_bounded_without_silent_success(self):
        result=run(form('<unknown/>'*105))
        self.assertEqual(len(result['issues']),100)
        self.assertTrue(result['issues_truncated']); self.assertEqual(result['status'],'blocked')

    def test_utf8_bom_empty_text_and_repeated_actions_are_preserved(self):
        xml=form('<FormField name="Поле"><inputText text=""/><inputText text=""/></FormField>')
        result=run(b'\xef\xbb\xbf'+xml.encode('utf-8'))
        self.assertEqual(len(result['draft']['steps']),2)
        self.assertEqual(result['parameter_values'],{'value_001':'','value_002':''})
        self.assertEqual(run(xml),run(xml))

    def test_wrong_hierarchy_and_encoding_fail_closed(self):
        for xml in ['<uilog><FormButton name="OK"><click/></FormButton></uilog>',
                    '<?xml version="1.0" encoding="UTF-16"?><uilog/>']:
            self.assertIsNone(run(xml)['draft'])
        self.assertEqual(run(b'\xff\xfe')['status'],'rejected')

    def test_options_cannot_inject_runtime_binding_or_code(self):
        result=import_uilog('<uilog/>',scenario_id='../run',policy_id='fixture')
        self.assertEqual(result['status'],'rejected')
        self.assertIsNone(result['draft'])


if __name__=='__main__': unittest.main()
