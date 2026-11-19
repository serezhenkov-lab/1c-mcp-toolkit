"""Real context expiry after one successful UI write, then only new observation."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/scenario_context_runtime.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('context=provider.create()')], 'refresh_setup', 'exec'))
import sqlite3
from contextlib import closing
text='REFRESH:'+uuid.uuid4().hex
first['arguments']['params']['text']=text;second['arguments']['params']['condition']['value']=text
template.update(scenario_id='product-context-renewal',steps=[first,second])
policy['scope_digests']=[command_scope(s) for s in template['steps']];policy_write(policy)
save('template',template);save('parameters',{})
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
completed=subprocess.run([sys.executable,'-B',str(root/'tests/test_client/scenario_refresh_child.py'),str(run),'--endpoint',f'http://127.0.0.1:{state["port"]}','--channel','queue1','--policy',str(path),'--template',str(run/'template.json'),'--parameters',str(run/'parameters.json'),'--store',str(run/'scenario.sqlite'),'--run'],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=180,creationflags=subprocess.CREATE_NO_WINDOW)
(run/'cli.stdout').write_text(completed.stdout,encoding='utf-8');(run/'cli.stderr').write_text(completed.stderr,encoding='utf-8')
assert completed.returncode==0,completed.stdout+completed.stderr
result=json.loads(completed.stdout);save('scenario-result',result)
check('two_steps_succeeded',result['status']=='succeeded' and len(result['steps'])==2 and all(s['status']=='succeeded' for s in result['steps']),result)
check('exactly_two_dispatches',result['dispatch_count']==2 and len({s['operation_id'] for s in result['steps']})==2)
events=result.get('context_refreshes',[])
check('renewal_before_readback',len(events)==1 and events[0]['before_step']=='readback' and events[0]['from_digest']!=events[0]['to_digest'])
before=json.loads((run/'context-before-delay.json').read_text(encoding='utf-8'))
with closing(sqlite3.connect((run/'scenario.sqlite').resolve().as_uri()+'?mode=ro',uri=True)) as db:saved=json.loads(db.execute('SELECT state FROM runs').fetchone()[0])
after=saved['context'];stable=lambda c:{k:v for k,v in c.items() if k not in ('observed_at','expires_at')}
check('same_authority_after_expiry',stable(before)==stable(after) and datetime.fromisoformat(after['observed_at'])>datetime.fromisoformat(before['expires_at']))
receipt=json.loads((run/'native-before-delay.json').read_text(encoding='utf-8'))
check('mutation_receipt_unchanged',result['steps'][0]['result']==receipt and result['steps'][0]['operation_id']==receipt['operation_id'])
check('readback_after_renewal',result['steps'][1]['result']['data']['matched'] and result['steps'][1]['result']['data']['actual']==text)
final=rows();save('after-data',final);check('documents_unchanged',final==baseline)
provider.close();save('refresh-summary',dict(checks=checks,route=run.name,platform='8.5.1.1529',real_expiry=True,test_only_reply_delay=True,mutations=1))
