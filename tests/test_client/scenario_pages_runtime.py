"""New product chain: select inactive page, verify both visible/hidden branches."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'pages_setup', 'exec'))
def select(sid,name):
    return dict(step_id=sid,tool='test_action',arguments=dict(action='select_page',window=w,element={'selector':{'name':name,'type':'group','path':['Страницы']}},params={}),on_error='stop',timeout_ms=10000)
def visible(sid,name,value):
    return dict(step_id=sid,tool='test_expect',arguments=dict(window=w,element={'selector':{'name':name,'type':'decoration'}},params={'condition':{'property':'visible','operator':'equals','value':value}}),on_error='stop',timeout_ms=10000)
template.update(scenario_id='product-pages',steps=[select('second','Вторая'),visible('second_visible','Метка2',True),visible('first_hidden','Метка1',False),select('first','Первая'),visible('first_visible','Метка1',True),visible('second_hidden','Метка2',False)])
policy['scope_digests']=[command_scope(s) for s in template['steps']];policy_write(policy)
save('template',template);save('parameters',{})
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
completed=subprocess.run([sys.executable,'-B','-m','onec_mcp_toolkit_proxy.scenario_context','--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(path),'--template',str(run/'template.json'),'--parameters',str(run/'parameters.json'),'--store',str(run/'scenario.sqlite'),'--run'],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
(run/'cli.stdout').write_text(completed.stdout,encoding='utf-8');(run/'cli.stderr').write_text(completed.stderr,encoding='utf-8')
assert completed.returncode==0,completed.stdout+completed.stderr
result=json.loads(completed.stdout);save('scenario-result',result)
check('all_steps_succeeded',result['status']=='succeeded' and len(result['steps'])==6 and all(s['status']=='succeeded' for s in result['steps']),result)
check('one_dispatch_per_step',result['dispatch_count']==6 and len({s['operation_id'] for s in result['steps']})==6)
check('native_pages_verified',result['steps'][0]['result']['data']['current_page']=='Вторая' and result['steps'][3]['result']['data']['current_page']=='Первая')
check('both_visibility_branches_verified',all(result['steps'][i]['result']['data']['matched'] for i in (1,2,4,5)))
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close()
save('pages-summary',dict(checks=checks,route=run.name,platform='8.5.1.1529',new_capabilities=1,scenario_steps=6))
