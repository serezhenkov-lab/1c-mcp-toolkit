"""Queue2 acceptance: real 1C UI, native capture, bounded diagnostic fault hooks."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("'.local/queue1-finish'", "'.local/queue2-rest'")
# Explicit user approval covers the visible test client and the test manager.
prefix = prefix.replace('startupinfo.wShowWindow = 0', 'startupinfo.wShowWindow = 5')
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
    assert attached.get('status') == 'succeeded', attached
    sid = attached['session_id']
    windows = complete('test_inspect', args(action='windows', session_id=sid))
    window={'id':next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])}
    if '--artifacts-only' not in sys.argv:
        code('Результат=ФормаМенеджераТестирования.ПробаСписка("open");')
        for mode,expected in (('close',False),('open',True)):
            before=code('Результат=ФормаМенеджераТестирования.ПробаСписка("'+mode+'");')
            result=complete('test_inspect',args(action='tree',session_id=sid,window=window))
            after=code('Результат=ФормаМенеджераТестирования.ПробаСписка();')
            editor=result.get('data',{}).get('editor',{})
            check('list_'+mode+'_native_state', editor.get('choice_list')=={'available':True,'value':expected,'reason':None},editor)
            check('list_'+mode+'_unchanged',before==after and after['open']==expected,{'before':before,'after':after})
        code('Результат=ФормаМенеджераТестирования.ПробаСписка("close"); ФормаМенеджераТестирования.ПробаФлаг();')
        result=complete('test_inspect',args(action='tree',session_id=sid,window=window))
        unavailable=result.get('data',{}).get('editor',{}).get('choice_list',{})
        check('checkbox_list_unavailable',unavailable.get('available') is False and unavailable.get('value') is None and bool(unavailable.get('reason')),result['data']['editor'])
        denied=complete('test_action',args(action='click',session_id=sid,window=window,element={'selector':{'name':'MISSING_QUEUE2_REST'}}))
        errors=denied['data']['diagnostics']['errors']
        check('command_error_separate',denied['execution']=='not_started' and errors['command'] is not None and errors['observation'] is None and denied['data']['diagnostics']['last_confirmed_step'] is None,denied)
    counter=code('Результат=ФормаМенеджераТестирования.ПробаСчетчика();')
    action=args(action='click',session_id=sid,window=window,element={'selector':{'name':'Проверить'}})
    saved=complete('test_action',action)
    assert saved['status']=='succeeded',saved
    import ctypes
    from ctypes import wintypes
    u=ctypes.WinDLL('user32',use_last_error=True)
    u.GetWindow.argtypes=[wintypes.HWND,wintypes.UINT];u.GetWindow.restype=wintypes.HWND
    u.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
    CALLBACK=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    found=[]
    @CALLBACK
    def find(hwnd,extra):
        pid=wintypes.DWORD();u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==testclient.pid and u.IsWindowVisible(hwnd) and not u.GetWindow(hwnd,4):found.append(hwnd)
        return True
    u.EnumWindows(find,0);assert len(found)==1,found
    hwnd=found[0]
    for name,show in (('minimized',6),('hidden',0)):
        try:
            u.ShowWindow(hwnd,show);time.sleep(.2)
            assert (u.IsIconic(hwnd) if name=='minimized' else not u.IsWindowVisible(hwnd))
            refused=screenshot(name,target='test_client',session_id=sid)
            check(name+'_no_image',not refused.get('success') and refused.get('error')=='screenshot_target_unavailable' and 'image_sha256' not in refused,refused)
            status=call('test_session',args(action='status',params={'operation_id':saved['operation_id']}))['data']['operation']
            check(name+'_keeps_operation',status['operation_id']==saved['operation_id'] and status['status']=='succeeded' and status['data']['diagnostics']==saved['data']['diagnostics'],status)
        finally:
            u.ShowWindow(hwnd,9);u.ShowWindow(hwnd,5);u.SetForegroundWindow(hwnd);time.sleep(.5)
    replay=call('test_action',action)
    state=complete('test_session',args(action='status'))
    reattached=complete('test_session',args(action='attach',params={'profile_id':'queue2'}))
    assert reattached['status']=='succeeded',{'state':state,'reattach':reattached}
    sid=reattached['session_id']
    after=code('Результат=ФормаМенеджераТестирования.ПробаСчетчика();')
    check('artifact_failure_no_repeat',replay['operation_id']==saved['operation_id'] and int(after)==int(counter)+1,{'before':counter,'after':after,'operation_id':replay['operation_id']})
    stop(testclient)
    refused=screenshot('closed-process',target='test_client',session_id=sid)
    check('closed_process_no_image',not refused.get('success') and 'image_sha256' not in refused,refused)
    status=call('test_session',args(action='status',params={'operation_id':saved['operation_id']}))['data']['operation']
    check('closed_process_keeps_artifacts',status['status']=='succeeded' and status['data']['diagnostics']==saved['data']['diagnostics'],status)
    print(json.dumps({'route':route,'passed':len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
