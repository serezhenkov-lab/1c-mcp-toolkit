"""Real post-input refusal must stop the runner, including durable resume."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'refusal_setup', 'exec'))

marker='RUNNER_REJECT:'+uuid.uuid4().hex
prefix=deepcopy(second);prefix['step_id']='prefix'
prefix['arguments']['params']['condition']['value']='Начальное'
first['arguments']['params']['text']=marker
tail=deepcopy(first);tail['step_id']='tail';tail['arguments']['params']['text']='TAIL_MUST_NOT_RUN'
template.update(scenario_id='mutation-refusal-recovery',steps=[prefix,first,tail,second])
policy['scope_digests']=list(dict.fromkeys(command_scope(s) for s in template['steps']));policy_write(policy)
save('template',template);save('parameters',{})
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
base=[sys.executable,'-B','-m','onec_mcp_toolkit_proxy.scenario_context','--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(path),'--store',str(run/'scenario.sqlite')]
def cli(tag,args):
 p=subprocess.run(base+args,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
 (run/(tag+'.stdout')).write_text(p.stdout,encoding='utf-8');(run/(tag+'.stderr')).write_text(p.stderr,encoding='utf-8')
 assert p.returncode==0,p.stdout+p.stderr
 result=json.loads(p.stdout);save(tag,result);return result
result=cli('run-result',['--template',str(run/'template.json'),'--parameters',str(run/'parameters.json'),'--run'])
check('stopped_after_invoked_failure',result['status']=='partial' and result['dispatch_count']==2 and len(result['steps'])==2,result)
failed=result['steps'][1]['result']
check('native_mismatch_is_failed',failed['status']=='failed' and failed['error']['code']=='action_not_confirmed' and failed['execution']=='invoked' and failed['data']['actual']==marker.replace('RUNNER_REJECT:','RUNNER_CORRECTED:') and failed['data']['completed_steps'][-1]=='finish_edit',failed)
check('successful_prefix_retained',result['steps'][0]['status']=='succeeded')
identities=lambda r:[tuple(e.get(k) for k in ('step_id','step_execution_id','request_id','operation_id','status')) for e in r['steps']]
for tag,extra in (('recover',[]),('resume',['--resume'])):
 recovered=cli(tag,['--recover',result['run_id']]+extra)
 check(tag+'_no_replay',recovered['status']=='partial' and recovered['dispatch_count']==2 and identities(recovered)==identities(result),recovered)
tree=call('test_inspect',action='tree',window=w,params={'depth':32,'max_nodes':5000});save('final-tree',tree)
check('complete_final_tree',tree['status']=='succeeded' and tree['data']['complete'])
for name,value in (('Текст',marker.replace('RUNNER_REJECT:','RUNNER_CORRECTED:')),('Результат','1'),('Флаг','Нет')):
 observed=call('test_inspect',action='values',window=w,params={'targets':[{'selector':{'name':name,'type':'field'}}]});save('final-value-'+name,observed)
 check('final_'+name,observed['status']=='succeeded' and observed['data']['values'][0]['value']==value,observed)
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close();save('mutation-failure-summary',dict(checks=checks,route=run.name,platform='8.5.1.1529'))
