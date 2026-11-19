"""New product scenario: absent -> navigate -> present -> close -> closed."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'window_setup', 'exec'))
target={'selector':{'form_name':'Документ.T43_Required.ФормаСписка'}}
def step(sid,tool,window,params,action=None):
    args=dict(window=window,params=params)
    if action:args['action']=action
    return dict(step_id=sid,tool=tool,arguments=args,on_error='stop',timeout_ms=10000)
def expect(sid,prop,value):return step(sid,'test_expect',target,{'condition':{'property':prop,'operator':'equals','value':value}})
template.update(scenario_id='product-window-lifecycle',steps=[
    expect('absent','exists',False),
    step('navigate','test_open',w,{'link':'e1cib/list/Документ.T43_Required'}),
    expect('present','exists',True),
    step('close','test_action',target,{},'close'),
    expect('closed','closed',True)])
policy['scope_digests']=[command_scope(s) for s in template['steps']];policy_write(policy)
save('template',template);save('parameters',{})
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
completed=subprocess.run([sys.executable,'-B','-m','onec_mcp_toolkit_proxy.scenario_context','--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(path),'--template',str(run/'template.json'),'--parameters',str(run/'parameters.json'),'--store',str(run/'scenario.sqlite'),'--run'],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
(run/'cli.stdout').write_text(completed.stdout,encoding='utf-8');(run/'cli.stderr').write_text(completed.stderr,encoding='utf-8')
assert completed.returncode==0,completed.stdout+completed.stderr
result=json.loads(completed.stdout);save('scenario-result',result)
check('all_steps_succeeded',result['status']=='succeeded' and len(result['steps'])==5 and all(s['status']=='succeeded' for s in result['steps']),result)
check('one_dispatch_per_step',result['dispatch_count']==5 and len({s['operation_id'] for s in result['steps']})==5)
check('absence_presence_closed_verified',all(result['steps'][i]['result']['data']['matched'] for i in (0,2,4)))
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close()
save('window-lifecycle-summary',dict(checks=checks,route=run.name,platform='8.5.1.1529',new_capabilities=4,scenario_steps=5))
