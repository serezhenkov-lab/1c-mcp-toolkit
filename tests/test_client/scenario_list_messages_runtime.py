"""New product chain: list choices -> button message -> inspect and expect."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'list_message_setup', 'exec'))
choice={'selector':{'name':'Выбор','type':'field'}}
button={'selector':{'name':'Проверить','type':'button'}}
def step(sid,tool,params,action=None,element=None):
    args=dict(window=w,params=params)
    if action:args['action']=action
    if element:args['element']=element
    return dict(step_id=sid,tool=tool,arguments=args,on_error='stop',timeout_ms=10000)
template.update(scenario_id='product-list-messages',steps=[
    step('alpha','test_input',{'choice':{'list_value':'CHOICE_ALPHA'}},'select',choice),
    step('beta','test_input',{'choice':{'list_value':'CHOICE_BETA'}},'select',choice),
    step('emit','test_action',{},'click',button),
    step('messages','test_inspect',{},'messages'),
    step('message','test_expect',{'condition':{'property':'message','operator':'equals','value':'ACTION_CLICK'}})])
policy['scope_digests']=[command_scope(s) for s in template['steps']];policy_write(policy)
ctx=provider.create();save('expanded-context',ctx)
from onec_mcp_toolkit_proxy.scenario_contract import capability_key
check('new_capabilities_available',all(capability_key(s) in ctx['capabilities'] for s in template['steps']))
save('template',template);save('parameters',{})
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
completed=subprocess.run([sys.executable,'-B','-m','onec_mcp_toolkit_proxy.scenario_context','--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(path),'--template',str(run/'template.json'),'--parameters',str(run/'parameters.json'),'--store',str(run/'scenario.sqlite'),'--run'],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
(run/'cli.stdout').write_text(completed.stdout,encoding='utf-8');(run/'cli.stderr').write_text(completed.stderr,encoding='utf-8')
assert completed.returncode==0,completed.stdout+completed.stderr
result=json.loads(completed.stdout);save('scenario-result',result)
check('all_steps_succeeded',result['status']=='succeeded' and len(result['steps'])==5 and all(s['status']=='succeeded' for s in result['steps']),result)
check('one_dispatch_per_step',result['dispatch_count']==5 and len({s['operation_id'] for s in result['steps']})==5)
check('two_choices_verified',all(s['result']['verification']=='confirmed' for s in result['steps'][:2]))
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close()
save('list-messages-summary',dict(checks=checks,route=run.name,platform='8.5.1.1529',new_capabilities=3,scenario_steps=5))
