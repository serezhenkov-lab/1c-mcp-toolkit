from copy import deepcopy
import unittest
from onec_mcp_toolkit_proxy.ui_snapshot_diff import diff_ui_snapshots


def node(identity, children=None):
    return dict(element_id=identity,type='group',children=children or [],unavailable=[],
        name='same',title='same',visible=True,enabled=True,read_only=False,editing=False)


def capture():
    return dict(binding=dict(owner='owner',channel_id='channel',base_id='base',session_id='session',
        generation='window',window_id='window',generation_proof='registry_window_id',scope='window',data_policy_id='raw'),
        result=dict(status='succeeded',session_id='session',operation_id='operation',
            data=dict(snapshot_id='snapshot',complete=True,truncated=False,
                coverage=[dict(scope='form_tree',status='complete')],tree=[node('root',[node('a'),node('b')])])) )


class DiffTests(unittest.TestCase):
    def setUp(self):
        self.a=capture();self.b=deepcopy(self.a)

    def diff(self):return diff_ui_snapshots(self.a,self.b)

    def test_equal_and_no_mutation(self):
        original=deepcopy(self.a)
        self.assertTrue(self.diff()['equal']);self.assertEqual(self.a,original)

    def test_known_property(self):
        self.b['result']['data']['tree'][0]['visible']=False
        result=self.diff()
        self.assertEqual(result['status'],'different')
        self.assertEqual(result['changed'][0]['changes'],[dict(property='visible',before=True,after=False)])

    def test_same_text_does_not_match_replacement(self):
        self.b['result']['data']['tree'][0]['children'][0]['element_id']='replacement'
        result=self.diff()
        self.assertEqual([n['element_id'] for n in result['removed']],['a'])
        self.assertEqual([n['element_id'] for n in result['added']],['replacement'])

    def test_partial_missing_is_not_deletion(self):
        self.b['result']['data']['tree'][0]['children']=[]
        self.b['result']['data']['truncated']=True
        result=self.diff()
        self.assertEqual(result['removed'],[]);self.assertEqual(result['status'],'partial')
        self.assertEqual(len(result['unobserved_ids']),2);self.assertIsNone(result['equal'])

    def test_unknown_coverage(self):
        self.b['result']['data']['coverage']=[]
        self.b['result']['data']['tree'][0]['children']=[]
        self.assertEqual(self.diff()['removed'],[])

    def test_unavailable_not_empty_or_equal(self):
        self.b['result']['data']['tree'][0]['unavailable']=['title']
        self.b['result']['data']['tree'][0]['title']=''
        result=self.diff()
        self.assertEqual(result['changed'],[]);self.assertIsNone(result['equal'])

    def test_binding_boundaries(self):
        for key in ('owner','channel_id','base_id','scope','data_policy_id','session_id','generation'):
            with self.subTest(key=key):
                self.b=deepcopy(self.a);self.b['binding'][key]='other'
                self.assertEqual(self.diff()['status'],'unavailable')

    def test_root_recreation(self):
        self.b['result']['data']['tree'][0]['element_id']='newroot'
        self.assertEqual(self.diff()['reason'],'root_identity_mismatch')

    def test_duplicate_id(self):
        self.b['result']['data']['tree'][0]['children'][1]['element_id']='a'
        self.assertEqual(self.diff()['status'],'unavailable')

    def test_type_change(self):
        self.b['result']['data']['tree'][0]['type']='button'
        self.assertEqual(self.diff()['reason'],'identity_type_mismatch')

    def test_presentation_budget_keeps_counts(self):
        self.b['result']['data']['tree'][0]['children'] += [node(str(i)) for i in range(150)]
        result=self.diff()
        self.assertEqual(result['counts']['added'],150)
        self.assertEqual(len(result['added']),100);self.assertTrue(result['diff_truncated'])
        self.assertFalse(result['equal'])

    def test_malformed_and_input_budget(self):
        for invalid in (None,{},dict(binding={},result={})):
            self.assertEqual(diff_ui_snapshots(self.a,invalid)['status'],'unavailable')
        self.b['result']['data']['padding']='x'*(2*1024*1024)
        self.assertEqual(self.diff()['reason'],'input_budget_exceeded')


if __name__=='__main__':unittest.main()
