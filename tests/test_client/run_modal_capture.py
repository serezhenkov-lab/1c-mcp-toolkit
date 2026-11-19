"""Modal screenshot regression on a production EPF; no Toolkit test hooks."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("'.local/queue1-finish'", "'.local/modal-fix'")
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
    user32.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]; user32.GetAncestor.restype=wintypes.HWND
    check('modal_owner_proven', user32.GetWindow(modal_hwnd,4)==client_hwnd and user32.GetAncestor(modal_hwnd,3)==client_hwnd and not user32.IsWindowEnabled(client_hwnd), {'main':client_hwnd,'modal':modal_hwnd})
    # Never activate/reorder every shadow window: that changed the owner order in the old harness.
    # SWP_NOACTIVATE | SWP_NOOWNERZORDER | SWP_NOMOVE | SWP_NOSIZE.
    flags=0x213
    def place(hwnd, insert):
        if not user32.SetWindowPos(hwnd,wintypes.HWND(insert),0,0,0,0,flags):
            raise ctypes.WinError(ctypes.get_last_error())
    def above(upper, lower):
        current=user32.GetWindow(lower,3)
        for _ in range(4096):
            if not current: return False
            if current==upper: return True
            current=user32.GetWindow(current,3)
        raise AssertionError('Z-order did not terminate')
    def verified(label):
        shot=screenshot(label,target='test_client',session_id=sid)
        layers=shot.get('overlays',[])
        check(label,shot.get('success') and shot.get('capture_complete') and shot.get('capture_target',{}).get('process_id')==testclient.pid and shot.get('session_id')==sid and any(l.get('hwnd')==modal_hwnd and not l.get('clipped') for l in layers),shot)
        check(label+'_preserves_modal',user32.GetLastActivePopup(client_hwnd)==modal_hwnd and user32.IsWindowVisible(modal_hwnd) and not user32.IsWindowEnabled(client_hwnd),{'hwnd':modal_hwnd})
        return shot
    try:
        place(client_hwnd,-1); place(modal_hwnd,-1)
        time.sleep(.3)
        check('modal_above_main',above(modal_hwnd,client_hwnd),{'main':client_hwnd,'modal':modal_hwnd})
        positive=verified('modal-visible')
        import asyncio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        async def mcp_capture():
            async with streamablehttp_client(f'http://127.0.0.1:{port}/mcp?channel=queue1') as streams:
                async with ClientSession(streams[0],streams[1]) as session:
                    await session.initialize()
                    response=await session.call_tool('get_screenshot',{'target':'test_client','session_id':sid})
                    metadata=[json.loads(p.text) for p in response.content if p.type=='text']
                    proof=next((p for p in metadata if 'capture_target' in p),{})
                    images=[p for p in response.content if p.type=='image']
                    check('modal_mcp', bool(images) and proof.get('capture_complete') and proof.get('session_id')==sid and proof.get('capture_target',{}).get('process_id')==testclient.pid and any(l.get('hwnd')==modal_hwnd for l in proof.get('overlays',[])),proof)
                    (run/'modal-mcp.png').write_bytes(base64.b64decode(images[0].data))
        asyncio.run(mcp_capture())
        # Force a different PID (our manager only) over the modal, without changing its owner.
        rect=wintypes.RECT();user32.GetWindowRect(modal_hwnd,ctypes.byref(rect))
        user32.SetWindowPos(manager_hwnd,wintypes.HWND(-1),rect.left-20,rect.top-20,600,300,0x210)
        time.sleep(.3)
        check('foreign_window_above_modal',above(manager_hwnd,modal_hwnd),{'manager':manager_hwnd,'modal':modal_hwnd})
        denied=screenshot('foreign-occlusion',target='test_client',session_id=sid)
        check('foreign_occlusion_no_image',not denied.get('success') and denied.get('error')=='screenshot_target_unavailable' and 'image_sha256' not in denied,denied)
        place(manager_hwnd,-2)
        place(client_hwnd,-1);place(modal_hwnd,-1)
        time.sleep(.3)
        restored=verified('modal-restored')
        check('same_modal_pixels_after_restore',positive['image_sha256']==restored['image_sha256'],{'before':positive['image_sha256'],'after':restored['image_sha256']})
    finally:
        place(manager_hwnd,-2);place(modal_hwnd,-2);place(client_hwnd,-2)
    print(json.dumps({'route':route,'passed':len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
