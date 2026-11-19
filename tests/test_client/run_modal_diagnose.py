"""Modal screenshot regression on a production EPF; no Toolkit test hooks."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("'.local/queue1-finish'", "'.local/modal-fix'")
# Explicit user approval covers the visible test client and the test manager.
prefix = prefix.replace('startupinfo.wShowWindow = 0', 'startupinfo.wShowWindow = 5')
prefix = prefix.replace("run = stand / route", "run = stand / 'diagnose'")
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
    check('attach', attached.get('status') == 'succeeded', attached)
    sid = attached['session_id']
    windows = complete('test_inspect', args(action='windows', session_id=sid))
    window = {'id': next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])}
    # Native error creates the modal; this is a new isolated fixture with no previous clicks.
    application = complete('test_action', args(action='click', session_id=sid, window=window, element={'selector': {'name': 'ОшибкаПриложения'}}))
    check('application_error_after_fix', application['data']['diagnostics']['errors']['application']['present'] is True, application)
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]; user32.GetWindow.restype = wintypes.HWND
    user32.GetLastActivePopup.argtypes = [wintypes.HWND]; user32.GetLastActivePopup.restype = wintypes.HWND
    user32.SetWindowPos.argtypes = [wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    windows_by_pid = {}
    CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    @CALLBACK
    def collect(hwnd, extra):
        pid = wintypes.DWORD(); user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value in (testclient.pid,manager.pid) and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd,4):
            windows_by_pid.setdefault(pid.value,[]).append(hwnd)
        return True
    user32.EnumWindows(collect,0)
    check('unique_test_windows', all(len(windows_by_pid.get(pid,[]))==1 for pid in (testclient.pid,manager.pid)), windows_by_pid)
    manager_hwnd = windows_by_pid[manager.pid][0]; client_hwnd = windows_by_pid[testclient.pid][0]
    modal_hwnd = user32.GetLastActivePopup(client_hwnd)
    check('actual_modal_window', modal_hwnd != client_hwnd and user32.IsWindowVisible(modal_hwnd), {'main':client_hwnd,'modal':modal_hwnd})
    user32.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];user32.GetAncestor.restype=wintypes.HWND
    user32.GetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int];user32.GetWindowLongW.restype=ctypes.c_long
    def geometry(label):
        rows=[]
        @CALLBACK
        def collect_all(hwnd,extra):
            pid=wintypes.DWORD(); tid=user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if pid.value == testclient.pid and user32.IsWindowVisible(hwnd):
                rect=wintypes.RECT();user32.GetWindowRect(hwnd,ctypes.byref(rect))
                cls=ctypes.create_unicode_buffer(256);user32.GetClassNameW(hwnd,cls,256)
                rows.append(dict(hwnd=hwnd,owner=user32.GetWindow(hwnd,4),root_owner=user32.GetAncestor(hwnd,3),class_name=cls.value,rect=[rect.left,rect.top,rect.right,rect.bottom],enabled=bool(user32.IsWindowEnabled(hwnd)),exstyle=user32.GetWindowLongW(hwnd,-20), previous=user32.GetWindow(hwnd,3), following=user32.GetWindow(hwnd,2)))
            return True
        user32.EnumWindows(collect_all,0)
        (run/(label+'.json')).write_text(json.dumps(rows),encoding='utf8')
    geometry('before')
    shot=screenshot('natural',target='test_client',session_id=sid)
    detail=code('Доказательство=ФормаМенеджераТестирования.ДоказательствоСнимкаКлиента("'+sid+'"); Результат=Лев(КомпонентаScreenCapture.CaptureProcessWindow(Доказательство.pid,Доказательство.created,100,Ложь,-1,-1,-1,-1,""),100);')
    (run/'native-natural.json').write_text(json.dumps(detail),encoding='utf8')
    geometry('after')
    user32.SetForegroundWindow.argtypes=[wintypes.HWND]
    user32.SetWindowPos(client_hwnd,wintypes.HWND(-1),0,0,0,0,0x253)
    user32.SetForegroundWindow(modal_hwnd)
    user32.SetWindowPos(modal_hwnd,wintypes.HWND(-1),0,0,0,0,0x253) # NOACTIVATE and NOOWNERZORDER
    time.sleep(.3)
    geometry('raised')
    shot=screenshot('raised',target='test_client',session_id=sid)
    detail=code('Доказательство=ФормаМенеджераТестирования.ДоказательствоСнимкаКлиента("'+sid+'"); Результат=Лев(КомпонентаScreenCapture.CaptureProcessWindow(Доказательство.pid,Доказательство.created,100,Ложь,-1,-1,-1,-1,""),100);')
    (run/'native-raised.json').write_text(json.dumps(detail),encoding='utf8')
    geometry('raised-after')
    user32.SetWindowPos(modal_hwnd,wintypes.HWND(-2),0,0,0,0,0x253)
    user32.SetWindowPos(client_hwnd,wintypes.HWND(-2),0,0,0,0,0x253)
    print(json.dumps({'route':'queue2-followup','passed':len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
