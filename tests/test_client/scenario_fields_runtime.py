"""New field observations and scalar text/clear through the product CLI."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'fields_setup', 'exec'))

def expect(sid,name,prop,value):
 return dict(step_id=sid,tool='test_expect',arguments=dict(window=w,element={'selector':{'name':name,'type':'field'}},params={'condition':{'property':prop,'operator':'equals','value':value}}),on_error='stop',timeout_ms=10000)
def enter(sid,text,finish=False):
 step=dict(step_id=sid,tool='test_input',arguments=dict(action='text',window=w,element=el,params={'text':text}),on_error='stop',timeout_ms=10000)
 if finish:step['finish_focus']={'selector':{'name':'Флаг','type':'field'},'same_form':True}
 return step
text='Проверка поля: '+uuid.uuid4().hex
steps=[expect('present','Текст','exists',True),expect('absent','НетТакогоПоля_TASK021','exists',False),
 expect('disabled','Результат','enabled',False),expect('readonly','Результат','read_only',True),
 enter('scalar_input',text),expect('readback','Текст','value',text),
 enter('scalar_clear',''),expect('empty','Текст','value',''),
 enter('refill_for_clear',text,True),enter('focus_clear','',True),expect('empty_after_focus','Текст','value','')]
if '--fields-input-only' in sys.argv:steps=steps[4:]  # Explicit continuation after an accepted state prefix.
template.update(scenario_id='product-fields',steps=steps)
policy['scope_digests']=list(dict.fromkeys(command_scope(s) for s in steps));policy_write(policy)
save('template',template);save('parameters',{})
save('before-tree',call('test_inspect',action='tree',window=w,params={'depth':32,'max_nodes':5000}))
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
completed=subprocess.run([sys.executable,'-B','-m','onec_mcp_toolkit_proxy.scenario_context','--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(path),'--template',str(run/'template.json'),'--parameters',str(run/'parameters.json'),'--store',str(run/'scenario.sqlite'),'--run'],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
(run/'cli.stdout').write_text(completed.stdout,encoding='utf-8');(run/'cli.stderr').write_text(completed.stderr,encoding='utf-8')
assert completed.returncode==0,completed.stdout+completed.stderr
result=json.loads(completed.stdout);save('scenario-result',result)
check('all_steps_succeeded',result['status']=='succeeded' and len(result['steps'])==len(steps) and all(s['status']=='succeeded' for s in result['steps']),result)
check('one_dispatch_per_step',result['dispatch_count']==len(steps) and len({s['operation_id'] for s in result['steps']})==len(steps))
check('all_observations_matched',all(s['result']['data']['matched'] for s,t in zip(result['steps'],steps) if t['tool']=='test_expect'))
mutations=[s['result']['data'] for s,t in zip(result['steps'],steps) if t['tool']=='test_input']
check('text_and_clear_verified',[m['actual'] for m in mutations]==[text,'',text,''] and all(m['editing'] is False for m in mutations))
check('two_native_clears',all('clear' in mutations[i]['completed_steps'] for i in (1,3)) and mutations[3]['finish_focus']['after_confirmed'])
# Same live disabled field may be observed but may not be changed.
blocked=enter('disabled_input','forbidden');blocked['arguments']['element']={'selector':{'name':'Результат','type':'field'}}
policy['scope_digests'].append(command_scope(blocked));policy_write(policy);context=provider.create()
check('disabled_input_guard_rejected',provider.guard(blocked,context)['allowed'] is False)
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close();save('fields-summary',dict(checks=checks,route=run.name,platform='8.5.1.1529',new_capabilities=2,scenario_steps=len(steps)))
