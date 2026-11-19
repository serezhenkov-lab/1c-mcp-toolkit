"""New acceptance: recover continue_observation after actual process death."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'observation_setup', 'exec'))
import time,sqlite3
from contextlib import closing
folder=run/'observation';folder.mkdir()
fail=deepcopy(second);fail.update(step_id='failed_read',on_error='continue_observation',timeout_ms=1000)
fail['arguments']['params']['condition']['value']='MUST_NOT_EXIST:'+uuid.uuid4().hex
skip=deepcopy(first);skip['arguments']['params']['text']='MUST_NOT_WRITE:'+uuid.uuid4().hex
last=deepcopy(second);last['arguments']['params']['condition']['value']=''
template['steps']=[fail,skip,last]
policy['scope_digests']=[command_scope(s) for s in template['steps']]
(folder/'policy.json').write_text(json.dumps(policy,ensure_ascii=False),encoding='utf-8')
(folder/'child.json').write_text(json.dumps(dict(endpoint=f'http://127.0.0.1:{state["port"]}',template=template),ensure_ascii=False),encoding='utf-8')
initial=call('test_expect',window=w,element=el,params={'condition':{'property':'value','operator':'equals','value':''}})
check('initial_empty_field',initial['status']=='succeeded')
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
with open(folder/'child.stdout','w',encoding='utf-8') as out,open(folder/'child.stderr','w',encoding='utf-8') as err:
    process=subprocess.Popen([sys.executable,'-B',str(root/'tests/test_client/scenario_recovery_child.py'),str(folder),'observation'],cwd=root,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline=time.monotonic()+90
        while not (folder/'kill-ready').exists():
            assert process.poll() is None,(folder/'child.stderr').read_text(encoding='utf-8')
            assert time.monotonic()<deadline,'crash_boundary_timeout'
            time.sleep(.1)
        process.kill();process.wait(timeout=10)
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=10)
with closing(sqlite3.connect(folder/'runs.sqlite')) as db:
    rid,payload=db.execute('SELECT id,state FROM runs').fetchone()
before=json.loads(payload);save('observation-checkpoint',before)
check('process_killed_after_failed_read',process.returncode!=0 and before['output']['dispatch_count']==1 and before['output']['steps'][0]['operation_id'] is not None)
base=[sys.executable,'-B','-m','onec_mcp_toolkit_proxy.scenario_context','--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(folder/'policy.json'),'--store',str(folder/'runs.sqlite'),'--recover',rid]
outputs=[]
for i,extra in enumerate(([],['--resume'],['--resume'])):
    result=subprocess.run(base+extra,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
    (folder/f'recover-{i}.stdout').write_text(result.stdout,encoding='utf-8')
    (folder/f'recover-{i}.stderr').write_text(result.stderr,encoding='utf-8')
    assert result.returncode==0,result.stderr+result.stdout
    outputs.append(json.loads(result.stdout))
check('recover_preserves_failed_read',outputs[0]['status']=='recovered' and outputs[0]['steps'][0]['status']=='failed' and outputs[0]['dispatch_count']==1)
r=outputs[1]
check('resume_only_observations',r['status']=='partial' and r['observation_only'] and [e['status'] for e in r['steps']]==['failed','skipped','succeeded'] and r['dispatch_count']==2)
check('skipped_mutation_has_no_operation',r['steps'][1]['operation_id'] is None)
identities=lambda x:[(e['step_execution_id'],e['request_id'],e['operation_id'],e['status']) for e in x['steps']]
check('repeated_resume_no_dispatch',outputs[2]['status']=='partial' and outputs[2]['dispatch_count']==2 and identities(outputs[2])==identities(r))
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close()
save('observation-summary',dict(checks=checks,actual_process_kill=True,platform='8.5.1.1529',route=run.name))
