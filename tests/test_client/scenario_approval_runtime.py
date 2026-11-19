"""Durable runner wait/deny/allow through a real 1C confirmation callback."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'approval_setup', 'exec'))
import time
client_code('РежимПодтвержденияОпасныхОпераций="ask"; Результат=Истина;')
binding=provider.binding();save('ask-binding',binding)
check('real_ask_mode',binding['approval_mode']=='ask')
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
base=[sys.executable,'-B','-m','onec_mcp_toolkit_proxy.scenario_context','--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(path),'--store',str(run/'scenario.sqlite')]
def cli(tag,args):
 p=subprocess.run(base+args,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
 (run/(tag+'.stdout')).write_text(p.stdout,encoding='utf-8');(run/(tag+'.stderr')).write_text(p.stderr,encoding='utf-8')
 r=json.loads(p.stdout);save(tag,r)
 assert p.returncode==0 or (p.returncode==1 and r['status']=='blocked'),p.stdout+p.stderr
 return r
def values(tag):
 r=call('test_inspect',action='values',window=w,params={'targets':[el,{'selector':{'name':'Результат','type':'field'}}]});save(tag,r)
 assert r['status']=='succeeded',r
 return [v['value'] for v in r['data']['values']]
for decision in ('deny','allow'):
 marker='APPROVAL:'+decision+':'+uuid.uuid4().hex
 first['arguments']['params']['text']=marker;first['timeout_ms']=120000
 second['arguments']['params']['condition']['value']=marker
 template.update(scenario_id='runner-approval-'+decision,steps=[first,second])
 policy['scope_digests']=[command_scope(s) for s in template['steps']];policy_write(policy)
 check(decision+'_initial_values',values(decision+'-before')==['Начальное','0'])
 save(decision+'-template',template);save('parameters',{})
 pending=cli(decision+'-pending',['--template',str(run/(decision+'-template.json')),'--parameters',str(run/'parameters.json'),'--run'])
 check(decision+'_waiting',pending['status']=='awaiting_approval' and pending['dispatch_count']==1 and len(pending['steps'])==1,pending)
 entry=pending['steps'][0];rid=pending['run_id'];op=entry['operation_id']
 if decision=='deny' and run.name!='file':
  waiting=cli(decision+'-waiting-resume',['--recover',rid,'--resume'])
  check(decision+'_resume_while_waiting_no_dispatch',
        (waiting['status']=='awaiting_approval' and waiting['dispatch_count']==1 and waiting['steps'][0]['operation_id']==op)
        or (waiting['status']=='blocked' and waiting['dispatch_count']==0 and waiting['reason']=='context_observation_timeout'),waiting)
 status=call('test_session',action='status',params={'operation_id':op})['data']['operation'];save(decision+'-waiting-operation',status)
 check(decision+'_not_invoked_before_decision',status['status']=='awaiting_approval' and status['execution']=='not_started',status)
 signal=entry['request_id']+'\n'+decision+'\n'
 (run/(decision+'-decision.txt')).write_text(signal,encoding='utf-8')
 target=root/'.local/runner-approval-20261117/decision.txt';tmp=target.with_suffix('.tmp');tmp.write_text(signal,encoding='utf-8');tmp.replace(target)
 deadline=time.monotonic()+40
 while True:
  observed=call('test_session',action='status',params={'operation_id':op})['data']['operation']
  if observed['status'] not in ('awaiting_approval','running','queued'):break
  assert time.monotonic()<deadline,observed
  time.sleep(.25)
 save(decision+'-operation',observed)
 recovered=cli(decision+'-recovered',['--recover',rid])
 resumed=cli(decision+'-resumed',['--recover',rid,'--resume'])
 if decision=='deny':
  check('denied_without_invocation',observed['status']=='failed' and observed['execution']=='not_started' and observed['error']['code']=='permission_denied',observed)
  check('denied_resume_stops',recovered['status']==resumed['status']=='failed' and resumed['dispatch_count']==1 and len(resumed['steps'])==1)
  check('denied_no_input',values('deny-after')==['Начальное','0'])
 else:
  check('allowed_existing_operation',observed['status']=='succeeded' and observed['operation_id']==op and recovered['status']=='recovered' and recovered['dispatch_count']==1)
  check('explicit_resume_only_tail',resumed['status']=='succeeded' and resumed['dispatch_count']==2 and resumed['steps'][0]['operation_id']==op)
  check('allowed_exactly_one_input',values('allow-after')==[marker,'1'])
 check(decision+'_same_request',resumed['steps'][0]['request_id']==entry['request_id'])
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close();save('approval-summary',dict(checks=checks,route=run.name,platform='8.5.1.1529',decision_source='isolated fixture, real dialog callback; not human acceptance'))
