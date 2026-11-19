"""Queue2 acceptance: real 1C UI, native capture, bounded diagnostic fault hooks."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[2]
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("'.local/queue1-finish'", "'.local/hwnd'")
# Explicit user approval covers the visible test client and the test manager.
prefix = prefix.replace('startupinfo.wShowWindow = 0', 'startupinfo.wShowWindow = 5')
if '--before' in sys.argv:
    prefix=prefix.replace("run = stand / route","run = stand / 'before'")
if '--fault' in sys.argv:
    prefix=prefix.replace("run = stand / route", "run = stand / 'fault'").replace("str(stand / 'Toolkit.epf')", "str(stand / 'Toolkit-fault.epf')")
if '--production' in sys.argv:
    prefix=prefix.replace("str(stand / 'Toolkit.epf')","str(stand / 'Toolkit-production.epf')")
prefix=prefix.replace("run = stand / route","run = stand / ('version85' if '--85' in sys.argv else 'refresh')")
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
    import ctypes,threading
    from ctypes import wintypes
    u=ctypes.WinDLL('user32',use_last_error=True)
    u.GetWindow.argtypes=[wintypes.HWND,wintypes.UINT];u.GetWindow.restype=wintypes.HWND
    u.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)];u.GetWindowThreadProcessId.restype=wintypes.DWORD
    ENUM=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def native_windows():
        found=[]
        @ENUM
        def cb(hwnd,extra):
            pid=wintypes.DWORD();tid=u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value==testclient.pid:
                cls=ctypes.create_unicode_buffer(256);u.GetClassNameW(hwnd,cls,256)
                found.append({'hwnd':hwnd,'pid':pid.value,'thread':tid,'owner':u.GetWindow(hwnd,4),'visible':bool(u.IsWindowVisible(hwnd)),'class':cls.value})
            return True
        u.EnumWindows(cb,0);return found
    eventlog=[];event_errors=[];stop_hook=threading.Event();hook_ready=threading.Event()
    EVENT=ctypes.WINFUNCTYPE(None,wintypes.HANDLE,wintypes.DWORD,wintypes.HWND,ctypes.c_long,ctypes.c_long,wintypes.DWORD,wintypes.DWORD)
    @EVENT
    def on_event(hook,event,hwnd,obj,child,tid,ms):
        if obj==0 and child==0 and len(eventlog)<10000:eventlog.append({'event':event,'hwnd':hwnd,'thread':tid,'time':ms})
    u.SetWinEventHook.argtypes=[wintypes.DWORD,wintypes.DWORD,wintypes.HMODULE,EVENT,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD];u.SetWinEventHook.restype=wintypes.HANDLE
    u.UnhookWinEvent.argtypes=[wintypes.HANDLE]
    def hook_loop():
        hook=u.SetWinEventHook(0x8000,0x8003,None,on_event,testclient.pid,0,0)
        if not hook:event_errors.append(ctypes.get_last_error())
        hook_ready.set()
        try:
            msg=wintypes.MSG()
            while not stop_hook.is_set():
                while u.PeekMessageW(ctypes.byref(msg),None,0,0,1):u.TranslateMessage(ctypes.byref(msg));u.DispatchMessageW(ctypes.byref(msg))
                time.sleep(.01)
        finally:
            if hook:u.UnhookWinEvent(hook)
    watcher=threading.Thread(target=hook_loop);watcher.start();hook_ready.wait(5);assert not event_errors,event_errors
    history=[]
    try:
        for action in ('Сведения','Обновить','Сведения'):
            before=native_windows();offset=len(eventlog)
            windows=complete('test_inspect',args(action='windows',session_id=sid))
            window={'id':next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])}
            result=complete('test_action',args(action='click',session_id=sid,window=window,element={'selector':{'name':'HWND'+action}}))
            time.sleep(.3)
            after=native_windows()
            fresh=complete('test_inspect',args(action='windows',session_id=sid))
            fresh_window={'id':next(w['window_id'] for w in fresh['data']['windows'] if 'Action Fixture' in w['title'])}
            value=complete('test_inspect',args(action='values',session_id=sid,window=fresh_window,params={'targets':[{'selector':{'name':'Результат'}}]}))
            raw=value['data']['values'][0]['value']
            try:details=json.loads(raw)
            except (ValueError,TypeError):details={'raw':raw}
            item={'action':action,'before':before,'after':after,'events':eventlog[offset:],'details':details,'public_windows':fresh['data']['windows'],'action_status':result['status']};history.append(item)
            (run/'window-history.json').write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding='utf8')
            check('mode_'+str(len(history)),result['status']=='succeeded' and details.get('error')=='',item)
        check('same_client_alive',testclient.poll() is None,{'pid':testclient.pid})
        print(json.dumps({'route':route,'passed':len(checks)}))
    finally:
        stop_hook.set();watcher.join(timeout=5)
        (run/'win-events.json').write_text(json.dumps(eventlog,ensure_ascii=False,indent=2),encoding='utf8')
finally:
    for p in reversed(owned):stop(p)
    (run/'cleanup.json').write_text(json.dumps({'owned':[p.pid for p in owned],'all_exited':all(p.poll() is not None for p in owned)}),encoding='utf8')
