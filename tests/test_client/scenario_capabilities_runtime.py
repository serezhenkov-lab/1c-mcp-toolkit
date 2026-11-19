"""New product registry combinations; no replay of the established input suite."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'capability_setup', 'exec'))
from onec_mcp_toolkit_proxy.scenario_contract import capability_key
button={'selector':{'name':'Проверить','type':'button'}}
flag={'selector':{'name':'Флаг','type':'field'}}
counter={'selector':{'name':'Результат','type':'field'}}
def step(sid,tool,params,action=None,element=None):
    args=dict(window=w,params=params)
    if action:args['action']=action
    if element:args['element']=element
    return dict(step_id=sid,tool=tool,arguments=args,on_error='stop',timeout_ms=10000)
def expect(sid,prop,value,element=None):
    return step(sid,'test_expect',{'condition':{'property':prop,'operator':'equals','value':value}},element=element)
scenarios={
 'window-observations':[
    step('activate','test_action',{},'activate_window'),
    expect('title','title','Action Fixture'),
    expect('visible','visible',True,button),
    expect('enabled','enabled',True,button),
    expect('readonly','read_only',True,counter)],
 'checkbox-button':[
    step('check','test_input',{'checked':True},'check',flag),
    step('click','test_action',{},'click',button),
    expect('counter','value','1',counter),
    step('uncheck','test_input',{'checked':False},'check',flag)]}
policy['scope_digests']=list({command_scope(s) for steps in scenarios.values() for s in steps});policy_write(policy)
ctx=provider.create();save('expanded-context',ctx)
expected={capability_key(s) for steps in scenarios.values() for s in steps}
check('new_capabilities_available',expected<=set(ctx['capabilities']),sorted(expected))
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
save('parameters',{})
for name,steps in scenarios.items():
    candidate=deepcopy(template);candidate.update(scenario_id=name,steps=steps)
    save(name+'-template',candidate)
    completed=subprocess.run([sys.executable,'-B','-m','onec_mcp_toolkit_proxy.scenario_context','--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(path),'--template',str(run/(name+'-template.json')),'--parameters',str(run/'parameters.json'),'--store',str(run/(name+'.sqlite')),'--run'],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
    (run/(name+'.stdout')).write_text(completed.stdout,encoding='utf-8');(run/(name+'.stderr')).write_text(completed.stderr,encoding='utf-8')
    assert completed.returncode==0,completed.stdout+completed.stderr
    result=json.loads(completed.stdout);save(name+'-result',result)
    check(name+'_all_steps_succeeded',result['status']=='succeeded' and len(result['steps'])==len(steps) and all(s['status']=='succeeded' for s in result['steps']),result)
    check(name+'_one_dispatch_per_step',result['dispatch_count']==len(steps))
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close()
save('capabilities-summary',dict(checks=checks,new_keys=7,registry_keys=12,scenario_steps=9,route=run.name,platform='8.5.1.1529'))
