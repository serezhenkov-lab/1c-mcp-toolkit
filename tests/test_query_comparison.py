"""Contract examples and failure boundaries, without 1C or transport I/O."""
from copy import deepcopy
from decimal import Decimal
import unittest

from onec_mcp_toolkit_proxy.query_comparison import compare_query_results, normalize_query_result


def cell(value, kind='string'):
    return dict(type=kind, value=value)


def fixture(expected=None, actual=None, mode='bag', types=('string',)):
    schema = [dict(name=f'c{i}', type=t, null_policy='reject') for i, t in enumerate(types)]
    contract = dict(id='baseline-1', base_id='base-1', query_fingerprint='a'*64,
                    data_policy_id='policy-1', schema=schema, mode=mode,
                    keys=['c0'] if mode == 'keyed' else [],
                    order_basis='ORDER BY unique id' if mode == 'ordered' else None,
                    ignore_columns=[])
    source = dict(kind='baseline', base_id='base-1', query_fingerprint='a'*64,
                  data_policy_id='policy-1', read_id='baseline-read', operation_id=None,
                  started_at='2026-11-16T10:00:00Z', finished_at='2026-11-16T10:00:01Z',
                  status='success', coverage='complete', effective_limit=None,
                  fidelity='exact', order_proven=True, normalization_error=None)
    e = dict(source=source, schema=deepcopy(schema), rows=expected if expected is not None else [[cell('a')]])
    a = dict(source=dict(source, kind='execute_query', read_id='query-read', effective_limit=1000),
             schema=deepcopy(schema), rows=actual if actual is not None else deepcopy(e['rows']))
    return deepcopy(dict(version=1, contract=contract, expected=e, actual=a))


def reference(typ='СправочникСсылка.Товары', presentation='Товар'):
    return cell(dict(object_type=typ, id='12345678-1234-1234-1234-123456789abc', presentation=presentation), 'reference')


def examples():
    a, b = [cell('a')], [cell('b')]
    yield 1, fixture([a,b], [b,a]), 'equal', None, dict(equal=2)
    yield 2, fixture([a,a], [a]), 'different', 'value_mismatch', dict(equal=1, missing=1)
    yield 3, fixture([a], [b]), 'different', 'value_mismatch', dict(missing=1, unexpected=1, changed=0)
    e = [[cell('1','number'),cell('a')]]
    yield 4, fixture(e, [[cell('1','number'),cell('b')]], 'keyed', ('number','string')), 'different', 'value_mismatch', dict(changed=1)
    yield 5, fixture(e, [[cell('2','number'),cell('a')]], 'keyed', ('number','string')), 'different', 'value_mismatch', dict(missing=1,unexpected=1)
    yield 6, fixture(e+e, e, 'keyed', ('number','string')), 'unavailable', 'duplicate_key', dict(changed=None)
    yield 7, fixture([a,b], [b,a], 'ordered'), 'different', 'value_mismatch', dict(changed=2)
    q=fixture([a,b], [b,a], 'ordered'); q['actual']['source']['order_proven']=False
    yield 8,q,'unavailable','order_unproven',{}
    yield 9,fixture([[cell('1.00','number')]],[[cell('1','number')]],types=('number',)),'equal',None,{}
    q=fixture([[cell('1','number')]],[[cell(True,'boolean')]],types=('number',)); q['actual']['schema'][0]['type']='boolean'
    yield 10,q,'different','schema_mismatch',dict(changed=None)
    yield 11,fixture([a],[[cell('a ')]]),'different','value_mismatch',dict(missing=1,unexpected=1)
    yield 12,fixture([[reference()]],[[reference(presentation='New')]],types=('reference',)),'equal',None,{}
    yield 13,fixture([[reference()]],[[reference('ДокументСсылка.Заказ')]],types=('reference',)),'different','value_mismatch',dict(missing=1,unexpected=1)
    q=fixture([],[]); q['actual'].update(schema=None,rows=None); q['actual']['source']['status']='failed'
    yield 14,q,'unavailable','source_failed',{}
    yield 15,fixture([],[]),'equal',None,dict(equal=0,missing=0,unexpected=0,changed=0)
    q=fixture(); q['actual']['source']['effective_limit']=1
    yield 16,q,'unavailable','incomplete_source',{}
    q=fixture(); q['actual']['source']['base_id']='base-2'
    yield 17,q,'unavailable','source_mismatch',{}
    q=fixture(); q['actual']['source'].update(kind='ui_snapshot',coverage='partial')
    yield 18,q,'unavailable','unsupported_source',{}
    q=fixture(e,[[cell('1','number'),cell('b')]],'keyed',('number','string')); q['contract']['ignore_columns']=[dict(name='c1',reason='volatile label')]
    yield 19,q,'equal',None,{}
    q=fixture(); q['actual'].update(rows=None,schema=None); q['actual']['source']['normalization_error']='ambiguous_null'
    yield 20,q,'unavailable','ambiguous_null',{}
    q=fixture([[cell(None,'wire_null')]])
    for obj in (q['contract'],q['expected'],q['actual']): obj['schema'][0]['null_policy']='wire_null'
    yield 21,q,'equal',None,{}
    q=fixture(); q['actual']['source']['normalization_error']='numeric_precision_unproven'; q['actual']['rows']=None
    yield 22,q,'unavailable','numeric_precision_unproven',{}
    q=fixture(); q['contract']['tolerance']=0.1
    yield 23,q,'invalid_contract','unsupported_rule',{}
    q=fixture([[cell(str(i),'number'),cell('a')] for i in range(101)],[[cell(str(i),'number'),cell('b')] for i in range(101)],'keyed',('number','string'))
    yield 24,q,'different','value_mismatch',dict(changed=101)


class ContractExamples(unittest.TestCase):
    def check_result(self, request, status, reason, counts):
        before=deepcopy(request)
        result=compare_query_results(request)
        self.assertEqual(request,before)
        self.assertEqual(result['status'],status)
        self.assertEqual(result['reason'],reason)
        self.assertIs(result['equal'], {'equal':True,'different':False}.get(status))
        self.assertIs(result['business_confirmed'],False)
        for key,value in counts.items(): self.assertEqual(result['counts'][key],value)
        if result['counts']['equal'] is not None:
            c=result['counts']
            self.assertEqual(c['expected'],c['equal']+c['changed']+c['missing'])
            self.assertEqual(c['actual'],c['equal']+c['changed']+c['unexpected'])
        return result

    def test_all_24_contract_examples(self):
        cases=list(examples()); self.assertEqual([x[0] for x in cases],list(range(1,25)))
        for number,q,status,reason,counts in cases:
            with self.subTest(example=number):
                r=self.check_result(q,status,reason,counts)
                if number in (19,21): self.assertEqual(r['scope'],'wire_projection')
                if number==24:
                    self.assertTrue(r['diff_truncated']); self.assertEqual(len(r['diff']['changed']),100)
                if number==2: self.assertEqual(r['diff']['missing'][0]['indices'],[1])
                if number==4: self.assertEqual(r['diff']['changed'][0]['cells'][0]['column'],'c1')

    def test_schema_column_order_and_keyed_row_order(self):
        q=fixture([[cell('1','number'),cell('a')],[cell('2','number'),cell('b')]],mode='keyed',types=('number','string'))
        q['actual']['schema'].reverse()
        q['actual']['rows']=[list(reversed(r)) for r in reversed(q['actual']['rows'])]
        self.check_result(q,'equal',None,dict(equal=2))

    def test_source_failures_and_precedence(self):
        for field,value,reason in [('status','unknown','source_unknown'),('coverage','partial','incomplete_source'),('fidelity','unknown','fidelity_unproven'),('data_policy_id','other','source_mismatch')]:
            with self.subTest(field=field):
                q=fixture(); q['actual']['source'][field]=value
                self.check_result(q,'unavailable',reason,{})
        q=fixture(); q['expected']['source']['coverage']='partial'; q['actual']['source']['status']='failed'
        self.check_result(q,'unavailable','source_failed',{})

    def test_invalid_contract_and_values(self):
        for mutate in [lambda q:q.update(version=True),lambda q:q['contract']['schema'].append(q['contract']['schema'][0]),
                       lambda q:q['contract'].update(keys=['c0']),lambda q:q['contract'].update(ignore_columns=[dict(name='c0',reason='all')]),
                       lambda q:q['expected']['rows'][0].append(cell('extra'))]:
            q=fixture(); mutate(q)
            self.assertEqual(compare_query_results(q)['status'],'invalid_contract')
        q=fixture(); q['actual']['rows'][0]=[]
        self.check_result(q,'unavailable','malformed_source',{})

    def test_input_and_diff_byte_budgets(self):
        q=fixture([[cell('a')]]*1001)
        self.check_result(q,'unavailable','input_budget_exceeded',{})
        q=fixture([[cell('x'*(1024*1024))]])
        self.check_result(q,'unavailable','input_budget_exceeded',{})
        q=fixture([[cell('x'*270000)]],[[cell('y')]])
        r=self.check_result(q,'different','value_mismatch',dict(missing=1,unexpected=1))
        self.assertTrue(r['diff_truncated']); self.assertFalse(any(r['diff'].values()))

    def test_no_decimal_context_rounding_and_negative_zero(self):
        for left,right,status in [('0','-0','equal'),('1.000000000000000000000000000001','1.000000000000000000000000000002','different')]:
            q=fixture([[cell(left,'number')]],[[cell(right,'number')]],types=('number',))
            self.check_result(q,status,None if status=='equal' else 'value_mismatch',{})

    def test_typed_cell_mismatch_does_not_coerce_bool(self):
        q=fixture([[cell('1','number')]],[[cell(True,'boolean')]],types=('number',))
        self.check_result(q,'different','value_mismatch',dict(missing=1,unexpected=1))

    def test_schema_missing_and_extra(self):
        q=fixture(); q['actual']['schema'][0]['name']='other'
        r=self.check_result(q,'different','schema_mismatch',dict(changed=None))
        self.assertEqual([x['column'] for x in r['diff']['schema']],['c0','other'])

    def test_unknown_schema_and_malformed_source_metadata(self):
        q=fixture(); q['actual']['schema'][0]['type']='unknown'
        self.check_result(q,'unavailable','schema_unavailable',{})
        q=fixture(); q['actual']['source']['normalization_error']=[]
        self.check_result(q,'unavailable','malformed_source',{})

    def test_duplicate_actual_keys_and_null_keys(self):
        q=fixture(mode='keyed'); q['actual']['rows']*=2
        self.check_result(q,'unavailable','duplicate_key',{})
        q=fixture(mode='keyed'); q['actual']['rows']=[[cell(None,'wire_null')]]
        self.check_result(q,'unavailable','ambiguous_null',{})

    def test_outputs_do_not_alias_request_and_are_deterministic(self):
        q=fixture([[cell('a')]],[[cell('b')]])
        r=compare_query_results(q)
        self.assertEqual(r,compare_query_results(q))
        r['diff']['missing'][0]['row'][0]['value']='changed'
        r['sources']['actual']['base_id']='changed'
        self.assertEqual(q['expected']['rows'][0][0]['value'],'a')
        self.assertEqual(q['actual']['source']['base_id'],'base-1')


class NormalizerTests(unittest.TestCase):
    def normalize(self,value,typ='Строка',kind='string',**overrides):
        q=fixture(types=(kind,)); ctx=dict(q['actual']['source'], response_complete=True)
        ctx.update(overrides)
        raw=dict(success=True,data=[dict(c0=value)],schema=dict(columns=[dict(name='c0',types=[typ])]))
        return normalize_query_result(raw,ctx,q['contract']),q,raw,ctx

    def test_real_wire_schema_and_complete_comparison(self):
        actual,q,_,_=self.normalize('a')
        q['actual']=actual
        self.assertEqual(compare_query_results(q)['status'],'equal')

    def test_exact_numbers_and_float_refusal(self):
        for value in (1,Decimal('1.00000000000000000000000001')):
            a,_,_,_=self.normalize(value,'Число','number')
            self.assertIsNone(a['source']['normalization_error'])
            self.assertEqual(a['rows'][0][0]['value'],str(value))
        a,q,_,_=self.normalize(1.0,'Число','number'); q['actual']=a
        self.assertEqual(compare_query_results(q)['reason'],'numeric_precision_unproven')

    def test_limit_truncation_and_incomplete_response(self):
        for options in (dict(effective_limit=1),dict(response_complete=False)):
            a,q,_,_=self.normalize('a',**options); q['actual']=a
            self.assertEqual(compare_query_results(q)['reason'],'incomplete_source')
        a,q,raw,ctx=self.normalize('a'); raw['truncated']=True
        q['actual']=normalize_query_result(raw,ctx,q['contract'])
        self.assertEqual(compare_query_results(q)['reason'],'incomplete_source')

    def test_error_not_empty_and_no_error_text_leak(self):
        _,q,_,ctx=self.normalize('a')
        q['actual']=normalize_query_result(dict(success=False,error='SECRET'),ctx,q['contract'])
        r=compare_query_results(q)
        self.assertEqual(r['reason'],'source_failed'); self.assertNotIn('SECRET',str(r))

    def test_null_and_union(self):
        a,q,raw,ctx=self.normalize(None)
        self.assertEqual(a['source']['normalization_error'],'ambiguous_null')
        q['contract']['schema'][0]['null_policy']='wire_null'
        a=normalize_query_result(raw,ctx,q['contract'])
        self.assertEqual(a['rows'][0][0],cell(None,'wire_null'))
        raw['schema']['columns'][0]['types']=['Строка','Дата']
        self.assertEqual(normalize_query_result(raw,ctx,q['contract'])['source']['normalization_error'],'ambiguous_type')

    def test_reference_type_uuid_and_unsupported_values(self):
        value=dict(_objectRef=True,ТипОбъекта='СправочникСсылка.Товары',УникальныйИдентификатор='12345678-1234-1234-1234-123456789abc',Представление='Товар')
        a,_,_,_=self.normalize(value,'СправочникСсылка.Товары','reference')
        self.assertEqual(a['rows'][0][0],reference())
        for value,typ,reason in [([], 'Массив','unsupported_value'),('x','ПеречислениеСсылка.Виды','unsupported_value'),('2026-02-30T12:00:00','Дата','malformed_source')]:
            a,_,_,_=self.normalize(value,typ)
            self.assertEqual(a['source']['normalization_error'],reason)


if __name__ == '__main__':
    unittest.main()
