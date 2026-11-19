"""New 10.3 integration checks; does not rerun the 10.2 examples."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'test_client'))
from query_verification import verify_document_response
from test_query_comparison import fixture, reference
from onec_mcp_toolkit_proxy.query_comparison import normalize_query_result


class IntegrationTests(unittest.TestCase):
    def setup_read(self):
        q=fixture([[reference('ДокументСсылка.T43_Required')]],types=('reference',))
        context=dict(q['actual']['source'],response_complete=True)
        value=q['expected']['rows'][0][0]['value']
        raw=dict(success=True,data=[dict(c0=dict(_objectRef=True,ТипОбъекта=value['object_type'],
            УникальныйИдентификатор=value['id'],Представление=value['presentation']))],
            schema=dict(columns=[dict(name='c0',types=['Null',value['object_type']])]))
        return q,context,raw

    def test_nullable_schema_nonnull_reference_confirms_one_document(self):
        q,c,r=self.setup_read()
        out=verify_document_response(json.dumps(r),contract=q['contract'],baseline=q['expected'],context=c)
        self.assertTrue(out['business_confirmed'])
        self.assertFalse(out['comparison']['business_confirmed'])

    def test_catalog_reference_is_not_a_document_confirmation(self):
        q,c,r=self.setup_read()
        typ='СправочникСсылка.Товары'
        q['expected']['rows'][0][0]['value']['object_type']=typ
        r['data'][0]['c0']['ТипОбъекта']=typ
        r['schema']['columns'][0]['types']=['Null',typ]
        out=verify_document_response(json.dumps(r),contract=q['contract'],baseline=q['expected'],context=c)
        self.assertEqual(out['comparison']['status'],'equal')
        self.assertFalse(out['business_confirmed'])

    def test_nullable_schema_does_not_allow_ambiguous_null(self):
        q,c,r=self.setup_read(); r['data'][0]['c0']=None
        self.assertEqual(normalize_query_result(r,c,q['contract'])['source']['normalization_error'],'ambiguous_null')

    def test_nullable_schema_does_not_resolve_multiple_concrete_types(self):
        q,c,r=self.setup_read(); r['schema']['columns'][0]['types'].append('Строка')
        self.assertEqual(normalize_query_result(r,c,q['contract'])['source']['normalization_error'],'ambiguous_type')

    def test_text_data_duplicate_json_keys_and_failure_cannot_confirm(self):
        q,c,r=self.setup_read(); r['data']=json.dumps(r['data'])
        for raw in [json.dumps(r),'{"success":true,"success":false}',json.dumps(dict(success=False,error='private'))]:
            self.assertFalse(verify_document_response(raw,contract=q['contract'],baseline=q['expected'],context=c)['business_confirmed'])

    def test_empty_equal_or_multiple_equal_rows_do_not_confirm_one_document(self):
        for count in (0,2):
            q,c,r=self.setup_read(); q['expected']['rows']*=count; r['data']*=count
            out=verify_document_response(json.dumps(r),contract=q['contract'],baseline=q['expected'],context=c)
            self.assertEqual(out['comparison']['status'],'equal')
            self.assertFalse(out['business_confirmed'])


if __name__=='__main__': unittest.main()
