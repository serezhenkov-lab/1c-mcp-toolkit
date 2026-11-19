"""Focused native-number/modal regression; stand launcher must already run."""
import json,time,uuid,httpx
from pathlib import Path
import sys
run=Path(sys.argv[1])
for _ in range(60):
    if (run/"state.json").exists():break
    time.sleep(1)
state=json.loads((run/'state.json').read_text(encoding='utf-8'))
sid=state['sid'];client=httpx.Client(base_url=f'http://127.0.0.1:{state["port"]}',timeout=30,trust_env=False)
def call(tool,**kw):
    a={'request_id':str(uuid.uuid4()),'params':{},**kw}
    if tool.startswith('test_'):a['session_id']=sid
    r=client.post('/api/'+tool,params={'channel':'queue1'},json=a).json()
    with (run/'actions.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(tool=tool,args=a,result=r),ensure_ascii=False)+'\n')
    for _ in range(240):
        if r.get('status') not in ('queued','running'):break
        time.sleep(.25)
        r=client.post('/api/test_session',params={'channel':'queue1'},json=dict(request_id=str(uuid.uuid4()),action='status',params={'operation_id':r['operation_id']})).json().get('data',{}).get('operation',{})
    with (run/'terminal.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(tool=tool,args=a,result=r),ensure_ascii=False)+'\n')
    return r
def nodes(tree):
    for n in tree:
        yield n
        yield from nodes(n.get('children',[]))


w={'selector':{'form_name':'Документ.T43_Required.ФормаСписка'}}
r=call('test_action',action='click',window=w,element={'selector':{'name':'ФормаСоздать'}});assert r['status']=='succeeded',r
w={'selector':{'form_name':'Документ.T43_Required.ФормаОбъекта'}}
text='M'+uuid.uuid4().hex[:10]
r=call('test_input',action='text',window=w,element={'selector':{'name':'Номер'}},params={'text':text})
(run/'input.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
windows=call('test_inspect',action='windows')
modal=[x for x in windows['data']['windows'] if x['form_name']=='MessageBox'];assert len(modal)==1,windows
m={'id':modal[0]['window_id']}
tree=call('test_inspect',action='tree',window=m)
(run/'modal.json').write_text(json.dumps(tree,ensure_ascii=False,indent=2),encoding='utf-8')
no=[n for n in nodes(tree['data']['tree']) if n.get('name')=='Button1' and n.get('title')=='Нет'];assert len(no)==1,no
answer=call('test_action',action='click',window=m,element={'id':no[0]['element_id']})
after=call('test_inspect',action='windows')
values=call('test_inspect',action='values',window=w,params={'targets':[{'selector':{'name':'Номер'}}]})
(run/'proof.json').write_text(json.dumps(dict(text=text,input=r,modal=modal,answer=answer,after=after,values=values),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(input=r['status'],input_error=r.get('error'),answer=answer['status'],answer_error=answer.get('error')),ensure_ascii=True))
checks={}
if '--fixed' in sys.argv:
    checks['modal_blocks_finish_before_attempt']=r['status']=='failed' and r['execution']=='invoked' and r['error']['code']=='action_not_confirmed' and r['data'].get('input_completion')=='blocked_by_other_window'
    checks['input_called_once_finish_not_called']=r['data']['completed_steps']==['activate','input_text']
    checks['blocking_window_matches']=r['data'].get('blocking_window_id')==modal[0]['window_id']
    checks['explicit_answer_succeeds']=answer['status']=='succeeded'
    checks['modal_disappeared']=not any(x['form_name']=='MessageBox' for x in after['data']['windows'])
    stale=call('test_action',action='click',window=m,element={'id':no[0]['element_id']})
    checks['closed_modal_stale_before_invocation']=stale['execution']=='not_started' and stale['error']['code']=='stale_target'
    normal=call('test_input',action='text',window=w,element={'selector':{'name':'ОбязательноеПоле'}},params={'text':'MODAL_CHECK_ONLY'})
    checks['ordinary_input_after_answer']=normal['status']=='succeeded' and normal['data'].get('actual')=='MODAL_CHECK_ONLY' and 'finish_edit' in normal['data'].get('completed_steps',[])
    (run/'fixed-checks.json').write_text(json.dumps(dict(checks=checks,stale=stale,normal=normal),ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(checks.values()),checks
print(json.dumps(checks))
(run/'finish').touch()
