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
    proxy = start_proxy()
    command = f'"{exe}" ENTERPRISE /IBConnectionString "File=""{run / "db"}"";" /TESTCLIENT -TPort16549 /N ApiProbe /Execute "{stand / "Fixture.epf"}" /DisableStartupDialogs /DisableStartupMessages /Out "{run / "client.log"}"'
    testclient = launch(command, 'client')
    for _ in range(120):
        try:
            with socket.create_connection(('127.0.0.1', 16549), timeout=.3):
                break
        except OSError:
            time.sleep(.5)
    manager = start_manager()
    ready()
    code('ТестПрофильID="queue2"; ТестПрофильПользователь="ApiProbe"; ТестПрофильПорт=16549; ТестПрофильВключен=Истина; ТестПрофильТребуетПароль=Ложь; СохранитьПрофильТестирования(Неопределено); Результат=ТестПрофильСтатус;')
    for _ in range(40):
        state = complete('test_session', args(action='status'))
        if (state.get('error') or {}).get('code') != 'operation_store_unavailable':
            break
        time.sleep(.25)
    attached = complete('test_session', args(action='attach', params={'profile_id': 'queue2'}))
    assert attached.get('status') == 'succeeded',attached
    sid = attached['session_id']
    windows = complete('test_inspect', args(action='windows', session_id=sid))
    window={'id':next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])}
    if '--mutation-only' not in sys.argv:
        request=args(session_id=sid,window=window,element={'selector':{'name':'Текст'}},timeout_ms=6000,params={'condition':{'property':'value','operator':'equals','value':'NEVER_PROGRESS'}})
        started=call('test_expect',request)
        operation=started['operation_id']
        samples=[]; latencies=[]
        deadline=time.monotonic()+20
        result=started
        while time.monotonic()<deadline:
            begin=time.monotonic()
            response=call('test_session',args(action='status',params={'operation_id':operation}))
            latencies.append(time.monotonic()-begin)
            result=response['data']['operation']
            value=(result.get('data') or {}).get('progress')
            if value is not None:
                samples.append(value)
                assert result['status']=='running',result
            if result['status'] not in ('queued','running','awaiting_approval'):break
            time.sleep(.25)
        check('progress_before_terminal',bool(samples) and result['status']=='failed' and result['error']['code']=='expectation_timeout',{'samples':samples,'terminal':result})
        check('progress_correlated_bounded',all(p['operation_id']==operation and p['scope']=='intermediate_snapshot' and p['completed_count']==0 and p['last_confirmed_step'] is None and len(json.dumps(p))<1024 for p in samples),samples)
        check('monotonic_heartbeat',len({p['sequence'] for p in samples})>=2 and all(a['sequence']<=b['sequence'] and a['elapsed_ms']<=b['elapsed_ms'] for a,b in zip(samples,samples[1:])),samples)
        check('waiting_phase',any(p['phase']=='waiting' for p in samples),samples)
        check('status_not_queued',max(latencies)<2,{'max_seconds':max(latencies)})
        check('terminal_uses_final_diagnostics','progress' not in result['data'] and result['data']['diagnostics']['progress']['scope']=='terminal_snapshot',result)
        replay=call('test_expect',request)
        check('replay_keeps_final',replay['operation_id']==operation and replay==result,replay)
        foreign=client.post('/api/test_session',params={'channel':'other_progress'},json=args(action='status',params={'operation_id':operation})).json()
        check('foreign_no_progress','intermediate_snapshot' not in json.dumps(foreign) and 'NEVER_PROGRESS' not in json.dumps(foreign),foreign)
    # Successful mutation must still have one final confirmed result after intermediate events.
    action=args(action='click',session_id=sid,window=window,element={'selector':{'name':'Проверить'}})
    clicked=complete('test_action',action)
    check('action_after_progress',clicked['status']=='succeeded' and clicked['data']['diagnostics']['last_confirmed_step']=='action',clicked)
    replay=call('test_action',action)
    check('action_not_repeated',replay==clicked,replay)
    checked=complete('test_expect',args(session_id=sid,window=window,element={'selector':{'name':'Результат'}},timeout_ms=0,params={'condition':{'property':'value','operator':'equals','value':'1'}}))
    check('one_ui_mutation',checked['status']=='succeeded',checked)
    if '--fault' in sys.argv:
        check('delivery_failure_does_not_fail_action',clicked['data']['diagnostics'].get('progress_delivery_failed') is True,clicked)
    print(json.dumps({'route':route,'passed':len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
