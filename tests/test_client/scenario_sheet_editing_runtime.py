"""Spreadsheet field native false/true/false and product observation acceptance."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'sheet_setup', 'exec'))

def probe(mode):
 result=client_code('Результат=ФормаМенеджераТестирования.ПробаEditingТабДок("'+mode+'");')
 if isinstance(result,str):result=json.loads(result)
 save('native-'+mode,result);return result

def find(nodes,name):
 for node in nodes:
  if node.get('name')==name:return node
  found=find(node.get('children',[]),name)
  if found:return found

def expectation(value,name='ТабДок'):
 return dict(step_id='editing_'+str(value).lower(),tool='test_expect',arguments=dict(window=w,element={'selector':{'name':name,'type':'field'}},params={'condition':{'property':'editing','operator':'equals','value':value}}),on_error='stop',timeout_ms=10000)
steps=[expectation(False),expectation(True)];ordinary=expectation(False,'Текст')
policy['scope_digests']=[command_scope(s) for s in steps+[ordinary]];policy_write(policy)
initial=probe('read');check('native_idle_despite_edit_allowed',initial['editing'] is False and initial['text']=='SHEET_EDITING_UNCHANGED',initial)
started=False;results=[]
try:
 for tag,value in (('idle',False),('editing',True),('finished',False)):
  if tag=='editing':started=True;native=probe('begin');check('native_begin_true',native['editing'] is True,native)
  if tag=='finished':native=probe('end');started=False;check('native_cancel_false_content_retained',native['editing'] is False and native['text']==initial['text'],native)
  tree=call('test_inspect',action='tree',window=w,params={'depth':32,'max_nodes':5000});save(tag+'-tree',tree)
  check(tag+'_inspect',tree['status']=='succeeded' and tree['data']['complete'] and find(tree['data']['tree'],'ТабДок')['editing'] is value)
  template.update(scenario_id='product-sheet-'+tag,steps=[deepcopy(steps[int(value)])]);save(tag+'-template',template)
  result=provider.run(template,{},store_path=run/'scenario.sqlite');save(tag+'-result',result);results.append(result)
  check(tag+'_product_expect',result['status']=='succeeded' and result['dispatch_count']==1 and result['steps'][0]['result']['data']['actual'] is value and result['steps'][0]['result']['data']['matched'])
finally:
 if started:probe('end')
template.update(scenario_id='ordinary-field-still-unavailable',steps=[ordinary])
blocked=provider.run(template,{},store_path=run/'scenario.sqlite');save('ordinary-blocked',blocked)
check('ordinary_field_guard_blocks_before_dispatch',blocked['status']=='blocked' and blocked['dispatch_count']==0 and blocked['steps'][0]['result']['error']['code']=='runtime_precondition_failed')
check('three_distinct_read_operations',len({r['steps'][0]['operation_id'] for r in results})==3)
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close();save('sheet-editing-summary',dict(checks=checks,route=run.name,platform='8.5.1.1529',product_mutations=0,fixture_edit_cycle=True))
