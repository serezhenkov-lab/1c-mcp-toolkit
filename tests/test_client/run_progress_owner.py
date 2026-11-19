"""Queue2 acceptance: real 1C UI, native capture, bounded diagnostic fault hooks."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[2]
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("'.local/queue1-finish'", "'.local/progress'")
# Explicit user approval covers the visible test client and the test manager.
prefix = prefix.replace('startupinfo.wShowWindow = 0', 'startupinfo.wShowWindow = 5')
if '--fault' in sys.argv:
    prefix=prefix.replace("run = stand / route", "run = stand / 'fault'").replace("str(stand / 'Toolkit.epf')", "str(stand / 'Toolkit-fault.epf')")
prefix=prefix.replace("run = stand / route", "run = stand / 'owner'")
exec(compile(prefix, 'queue2_helpers', 'exec'))
import base64
import hashlib
import socket

def screenshot(name, **kwargs):
    response = client.post('/api/get_screenshot', params={'channel': 'queue1'}, json=kwargs).json()
    image = response.pop('image_base64', None)
    if image:
        raw = base64.b64decode(image)
        (run / (name + '.png')).write_bytes(raw)
        response['image_sha256'] = hashlib.sha256(raw).hexdigest()
        response['png_signature'] = raw[:8].hex()
    events.append({'tool': 'get_screenshot', 'args': kwargs, 'result': response})
    save()
    return response

try:
    manager=start_manager();ready()
    for _ in range(40):
        state=complete('test_session',args(action='status'))
        if (state.get('error') or {}).get('code')!='operation_store_unavailable':break
        time.sleep(.25)
    identifier=code('Новая=Ложь; Результат=LifecycleПринять("queue1","progress-owner-copy", "test_expect",Новый Структура("test","synthetic"),Новый Структура("session_id","owner-test"),Новая);')
    prefix_bsl='Ид="'+identifier+'"; '
    result=code(prefix_bsl+'П=Новый Структура("phase,completed_count,elapsed_ms,last_confirmed_step","waiting",0,100,Неопределено); LifecycleСобытие("queue1",Ид,"progress",3,П); Результат=LifecycleПолучить("queue1",Ид);')
    check('embedded_progress_stored',result['state']=='running' and result['event_seq']==3 and result['progress']['elapsed_ms']==100,result)
    after=code(prefix_bsl+'П=Новый Структура("phase,completed_count,elapsed_ms,last_confirmed_step","waiting",0,200,Неопределено); LifecycleСобытие("queue1",Ид,"progress",3,П); П.phase="SECRET"; LifecycleСобытие("queue1",Ид,"progress",4,П); Результат=LifecycleПолучить("queue1",Ид);')
    check('embedded_duplicate_invalid_no_write',after==result,after)
    after=code(prefix_bsl+'П=Новый Структура("phase,completed_count,elapsed_ms,last_confirmed_step","observing",1,300,"action"); LifecycleСобытие("queue1",Ид,"progress",5,П); LifecycleСобытие("queue1",Ид,"running",2); П.elapsed_ms=299; LifecycleСобытие("queue1",Ид,"progress",6,П); Результат=LifecycleПолучить("queue1",Ид);')
    check('embedded_monotonic',after['event_seq']==5 and after['progress']['completed_count']==1 and after['progress']['elapsed_ms']==300,after)
    denied=code(prefix_bsl+'Попытка LifecycleСобытие("foreign",Ид,"progress",7,Новый Структура); Результат=Ложь; Исключение Результат=Истина; КонецПопытки;')
    check('embedded_foreign_denied',denied)
    # Owned manager crash/restart; no TESTCLIENT and no UI mutation in this owner-only check.
    stop(manager);manager=start_manager();ready()
    for _ in range(40):
        state=call('test_session',args(action='status',params={'operation_id':identifier}))
        if (state.get('error') or {}).get('code')!='operation_store_unavailable':break
        time.sleep(.25)
    recovered=state['data']['operation']
    check('embedded_recovery_unknown_progress',recovered['status']=='unknown' and recovered['data']['progress']['sequence']==5 and recovered['data']['progress']['completed_count']==1,recovered)
    after=code(prefix_bsl+'П=Новый Структура("phase,completed_count,elapsed_ms,last_confirmed_step","observing",1,400,"action"); LifecycleСобытие("queue1",Ид,"progress",9,П); Результат=LifecycleПолучить("queue1",Ид);')
    check('unknown_not_revived',after['state']=='unknown' and after['event_seq']==5,after)
    final_id=code('Новая=Ложь; Ид=LifecycleПринять("queue1","progress-final-copy", "test_expect",Новый Структура("test","synthetic"),Новый Структура("session_id","owner-test"),Новая); П=Новый Структура("phase,completed_count,elapsed_ms,last_confirmed_step","waiting",0,100,Неопределено); LifecycleСобытие("queue1",Ид,"progress",3,П); LifecycleЗавершить("queue1",Ид,Новый Структура("success,data",Истина,Новый Структура("value",42))); LifecycleСобытие("queue1",Ид,"progress",4,П); Результат=LifecycleПолучить("queue1",Ид);')
    check('embedded_final_immutable',final_id['state']=='succeeded' and final_id['result']['data']['value']==42 and 'progress' not in final_id,final_id)
    print(json.dumps({'route':'embedded-owner','passed':len(checks)}))
finally:
    for p in reversed(owned):stop(p)
    (run/'cleanup.json').write_text(json.dumps({'owned':[p.pid for p in owned],'all_exited':all(p.poll() is not None for p in owned)}),encoding='utf8')
