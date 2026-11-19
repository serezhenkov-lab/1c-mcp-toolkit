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
prefix=prefix.replace("run = stand / route","run = stand / 'desktop'")
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

import ctypes
from ctypes import wintypes
u=ctypes.WinDLL('user32',use_last_error=True)
u.CreateDesktopW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
u.CreateDesktopW.restype=wintypes.HANDLE
u.CloseDesktop.argtypes=[wintypes.HANDLE]
u.OpenInputDesktop.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];u.OpenInputDesktop.restype=wintypes.HANDLE
u.GetUserObjectInformationW.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
def desktop_name(handle):
    buffer=ctypes.create_unicode_buffer(256);size=wintypes.DWORD()
    assert u.GetUserObjectInformationW(handle,2,buffer,ctypes.sizeof(buffer),ctypes.byref(size))
    return buffer.value
def input_desktop():
    handle=u.OpenInputDesktop(0,False,1);assert handle
    try:return desktop_name(handle)
    finally:u.CloseDesktop(handle)
original_input=input_desktop()
private_name='ToolkitQueue2_'+uuid.uuid4().hex
private=u.CreateDesktopW(private_name,None,None,0,0x1ff,None);assert private,ctypes.get_last_error()
class STARTUPINFOW(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('lpReserved',wintypes.LPWSTR),('lpDesktop',wintypes.LPWSTR),('lpTitle',wintypes.LPWSTR)]+[(n,wintypes.DWORD) for n in ('dwX','dwY','dwXSize','dwYSize','dwXCountChars','dwYCountChars','dwFillAttribute','dwFlags')]+[('wShowWindow',wintypes.WORD),('cbReserved2',wintypes.WORD),('lpReserved2',ctypes.c_void_p)]+[(n,wintypes.HANDLE) for n in ('hStdInput','hStdOutput','hStdError')]
class PROCESS_INFORMATION(ctypes.Structure):
    _fields_=[('hProcess',wintypes.HANDLE),('hThread',wintypes.HANDLE),('dwProcessId',wintypes.DWORD),('dwThreadId',wintypes.DWORD)]
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.CreateProcessW.argtypes=[wintypes.LPCWSTR,wintypes.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,wintypes.BOOL,wintypes.DWORD,ctypes.c_void_p,wintypes.LPCWSTR,ctypes.POINTER(STARTUPINFOW),ctypes.POINTER(PROCESS_INFORMATION)]
k.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
k.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
k.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
k.CloseHandle.argtypes=[wintypes.HANDLE]
u.GetThreadDesktop.argtypes=[wintypes.DWORD];u.GetThreadDesktop.restype=wintypes.HANDLE
class OwnedProcess:
    def __init__(self,info):self.pid=info.dwProcessId;self.handle=info.hProcess;self.exitcode=None
    def poll(self):
        if self.exitcode is not None:return self.exitcode
        value=wintypes.DWORD();assert k.GetExitCodeProcess(self.handle,ctypes.byref(value))
        if value.value!=259:
            self.exitcode=value.value;k.CloseHandle(self.handle)
        return self.exitcode
    def terminate(self):
        if self.poll() is None:assert k.TerminateProcess(self.handle,1)
    def wait(self,timeout):
        if self.poll() is None:assert k.WaitForSingleObject(self.handle,int(timeout*1000))==0
        return self.poll()
def launch(command,name,env=None):
    assert env is None, 'This desktop probe uses embedded only'
    si=STARTUPINFOW();si.cb=ctypes.sizeof(si);si.lpDesktop='winsta0\\'+private_name;si.dwFlags=1;si.wShowWindow=5
    pi=PROCESS_INFORMATION();line=command if isinstance(command,str) else subprocess.list2cmdline(command)
    assert k.CreateProcessW(None,ctypes.create_unicode_buffer(line),None,None,False,0x08000000,None,str(root),ctypes.byref(si),ctypes.byref(pi)),ctypes.get_last_error()
    k.CloseHandle(pi.hThread);process=OwnedProcess(pi);owned.append(process)
    return process

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
    CALLBACK=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    native=[]
    @CALLBACK
    def inspect_desktop(hwnd,unused):
        pid=wintypes.DWORD();tid=u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value in (testclient.pid,manager.pid) and u.IsWindowVisible(hwnd):native.append({'pid':pid.value,'hwnd':hwnd,'enumerated_desktop':private_name})
        return True
    u.EnumDesktopWindows.argtypes=[wintypes.HANDLE,CALLBACK,wintypes.LPARAM]
    assert u.EnumDesktopWindows(private,inspect_desktop,0)
    check('actual_process_desktops',{w['pid'] for w in native}=={testclient.pid,manager.pid} and all(w['enumerated_desktop']==private_name for w in native),native)
    refused=screenshot('private-desktop' ,target='test_client',session_id=sid)
    check('private_desktop_not_input',desktop_name(private)==private_name and input_desktop()==original_input and private_name!=original_input,{'private':private_name,'input_before':original_input,'input_after':input_desktop(),'client_pid':testclient.pid,'manager_pid':manager.pid})
    check('desktop_refusal_no_png','image_sha256' not in refused and refused.get('success') is False and refused.get('error')=='screenshot_target_unavailable',refused)
    print(json.dumps({'route':'private-desktop','passed':len(checks)}))
finally:
    for p in reversed(owned):stop(p)
    (run/'cleanup.json').write_text(json.dumps({'owned':[p.pid for p in owned],'all_exited':all(p.poll() is not None for p in owned),'desktop_closed':bool(u.CloseDesktop(private)),'input_unchanged':input_desktop()==original_input}),encoding='utf8')
