"""Native API mismatch proof and typed table editing through the product provider."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'editing_setup', 'exec'))

def probe(mode):
 result=client_code('Результат=ФормаМенеджераТестирования.ПробаEditing("'+mode+'");')
 if isinstance(result,str):result=json.loads(result)
 save('native-'+mode,result);return result

def find(nodes,name):
 for n in nodes:
  if n.get('name')==name:return n
  found=find(n.get('children',[]),name)
  if found:return found

def snapshot(tag,expected):
 tree=call('test_inspect',action='tree',window=w,params={'depth':32,'max_nodes':5000});save(tag+'-tree',tree)
 assert tree['status']=='succeeded' and tree['data']['complete']
 table=find(tree['data']['tree'],'Строки');field=find(tree['data']['tree'],'Текст')
 check(tag+'_typed_inspect',table['editing'] is expected and 'editing' not in table['unavailable'] and field['editing'] is None and field['unavailable_reasons']['editing']=='property_not_supported_for_type')
 return tree

steps=[dict(step_id='editing_'+str(value).lower(),tool='test_expect',arguments=dict(window=w,element={'selector':{'name':'Строки','type':'table'}},params={'condition':{'property':'editing','operator':'equals','value':value}}),on_error='stop',timeout_ms=10000) for value in (False,True)]
policy['scope_digests']=[command_scope(s) for s in steps];policy_write(policy)
first=probe('field');check('field_control_kind_rejected',bool(first['field_error']) and 'ТекущийРежимРедактирование' in first['field_error'] and first['table_editing'] is False,first)
started=False;results=[]
try:
 for tag,value in (('idle',False),('editing',True),('finished',False)):
  if tag=='editing':started=True;native=probe('begin');check('native_table_editing_true',native['table_editing'] is True)
  if tag=='finished':native=probe('end');started=False;check('native_table_editing_false',native['table_editing'] is False)
  snapshot(tag,value)
  template.update(scenario_id='product-table-'+tag,steps=[deepcopy(steps[int(value)])]);save(tag+'-template',template)
  result=provider.run(template,{},store_path=run/'scenario.sqlite');save(tag+'-result',result);results.append(result)
  check(tag+'_product_expect',result['status']=='succeeded' and result['dispatch_count']==1 and result['steps'][0]['result']['data']['actual'] is value and result['steps'][0]['result']['data']['matched'])
finally:
 if started:probe('end')
unsupported=call('test_expect',window=w,element=el,params={'condition':{'property':'editing','operator':'equals','value':False}});save('field-expect',unsupported)
check('field_false_not_fabricated',unsupported['status']=='failed' and unsupported['error']['code']=='value_unavailable')
check('three_distinct_observations',len({r['steps'][0]['operation_id'] for r in results})==3)
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close();save('editing-summary',dict(checks=checks,route=run.name,platform='8.5.1.1529',product_mutations=0,fixture_edit_cycle=True))
