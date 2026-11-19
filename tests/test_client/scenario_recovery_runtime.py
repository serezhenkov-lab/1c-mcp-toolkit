"""Kill a real runner process; recover through the product CLI, never replay UI."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'recovery_setup', 'exec'))
import sqlite3,time
from contextlib import closing
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'

for mode in os.environ.get('SCENARIO_RECOVERY_CASES','saved-receipt,lost-reply').split(','):
    folder=run/mode;folder.mkdir()
    child_template=deepcopy(template)
    marker='RECOVERY:'+mode+':'+uuid.uuid4().hex
    child_template['steps'][0]['arguments']['params']['text']=marker
    child_template['steps'][1]['arguments']['params']['condition']['value']=marker
    grant=deepcopy(policy);grant['scope_digests']=[command_scope(s) for s in child_template['steps']]
    (folder/'policy.json').write_text(json.dumps(grant,ensure_ascii=False),encoding='utf-8')
    (folder/'child.json').write_text(json.dumps(dict(endpoint=f'http://127.0.0.1:{state["port"]}',template=child_template),ensure_ascii=False),encoding='utf-8')
    with open(folder/'child.stdout','w',encoding='utf-8') as out,open(folder/'child.stderr','w',encoding='utf-8') as err:
        process=subprocess.Popen([sys.executable,'-B',str(root/'tests/test_client/scenario_recovery_child.py'),str(folder),mode],cwd=root,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
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
    before=json.loads(payload);save(mode+'-checkpoint',before)
    check(mode+'_process_killed',process.returncode!=0 and before['output']['dispatch_count']==1)
    base=[sys.executable,'-B','-m','onec_mcp_toolkit_proxy.scenario_context','--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(folder/'policy.json'),'--store',str(folder/'runs.sqlite'),'--recover',rid]
    outputs=[]
    for index,extra in enumerate(([],['--resume'],['--resume'])):
        result=subprocess.run(base+extra,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
        (folder/f'recover-{index}.stdout').write_text(result.stdout,encoding='utf-8')
        (folder/f'recover-{index}.stderr').write_text(result.stderr,encoding='utf-8')
        assert result.returncode==0,result.stderr+result.stdout
        outputs.append(json.loads(result.stdout))
    if mode=='saved-receipt':
        check('recovery_observes_without_dispatch',outputs[0]['status']=='recovered' and outputs[0]['dispatch_count']==1)
        check('explicit_resume_only_new_readback',outputs[1]['status']=='succeeded' and outputs[1]['dispatch_count']==2 and outputs[1]['steps'][0]['operation_id']==before['output']['steps'][0]['operation_id'])
        identities=lambda result:[tuple(e[k] for k in ('step_id','step_execution_id','request_id','operation_id','status')) for e in result['steps']]
        check('second_resume_no_dispatch',outputs[2]['status']=='succeeded' and outputs[2]['dispatch_count']==2 and identities(outputs[2])==identities(outputs[1]))
    else:
        check('lost_receipt_unknown_no_replay',all(x['status']=='unknown' and x['dispatch_count']==1 and len(x['steps'])==1 for x in outputs))
    # Independent public value observation after kill, not another input.
    observed=call('test_expect',window=w,element=el,params={'condition':{'property':'value','operator':'equals','value':marker}})
    save(mode+'-readback',observed)
    check(mode+'_ui_value_retained',observed['status']=='succeeded',observed)
final=rows();save('after-data',final);check('no_document_written',final==baseline)
provider.close()
save('recovery-summary',dict(checks=checks,actual_process_kill=True,new_recording=False,platform='8.5.1.1529',route=run.name))
