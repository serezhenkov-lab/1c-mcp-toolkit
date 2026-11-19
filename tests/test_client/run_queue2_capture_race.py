"""Queue2 acceptance: real 1C UI, native capture, bounded diagnostic fault hooks."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[2]
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("'.local/queue1-finish'", "'.local/queue2-final'")
# Explicit user approval covers the visible test client and the test manager.
prefix = prefix.replace('startupinfo.wShowWindow = 0', 'startupinfo.wShowWindow = 5')
if '--before' in sys.argv:
    prefix=prefix.replace("run = stand / route","run = stand / 'before'")
if '--fault' in sys.argv:
    prefix=prefix.replace("run = stand / route", "run = stand / 'fault'").replace("str(stand / 'Toolkit.epf')", "str(stand / 'Toolkit-fault.epf')")
if '--production' in sys.argv:
    prefix=prefix.replace("str(stand / 'Toolkit.epf')","str(stand / 'Toolkit-production.epf')")
prefix=prefix.replace("run = stand / route","run = stand / 'race'").replace("str(stand / 'Toolkit.epf')","str(stand / 'Toolkit-race.epf')")
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
    import ctypes
    from ctypes import wintypes
    from concurrent.futures import ThreadPoolExecutor
    u=ctypes.WinDLL('user32',use_last_error=True)
    u.GetWindow.argtypes=[wintypes.HWND,wintypes.UINT];u.GetWindow.restype=wintypes.HWND
    u.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    CALLBACK=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    roots=[]
    @CALLBACK
    def find(hwnd,unused):
        pid=wintypes.DWORD();u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==testclient.pid and u.IsWindowVisible(hwnd) and not u.GetWindow(hwnd,4):roots.append(hwnd)
        return True
    u.EnumWindows(find,0);assert len(roots)==1,roots
    assert u.SetWindowPos(roots[0],wintypes.HWND(-1),0,0,0,0,0x13|0x200)
    time.sleep(.3)
    assert not (run/'ready').exists() and not (run/'release').exists()
    with ThreadPoolExecutor(max_workers=1) as pool:
        capture=pool.submit(screenshot,'race',target='test_client',session_id=sid)
        for _ in range(100):
            if (run/'ready').exists() or capture.done():break
            time.sleep(.05)
        reached=(run/'ready').exists()
        if not reached:
            result=capture.result();check('capture_barrier_reached',False,result)
        check('capture_barrier_reached',reached and testclient.poll() is None and not capture.done(),{'pid':testclient.pid,'hwnd':roots[0]})
        stop(testclient)
        (run/'release').write_text('release',encoding='ascii')
        result=capture.result(timeout=20)
    check('final_identity_guard_ran',(run/'guard').exists() and testclient.poll() is not None,result)
    check('capture_race_no_png',result.get('success') is False and result.get('error')=='screenshot_target_unavailable' and 'image_sha256' not in result,result)
    print(json.dumps({'route':'identity-race','passed':len(checks)}))
finally:
    (run/'release').write_text('release',encoding='ascii')
    for p in reversed(owned):stop(p)
    (run/'cleanup.json').write_text(json.dumps({'owned':[p.pid for p in owned],'all_exited':all(p.poll() is not None for p in owned)}),encoding='utf8')
