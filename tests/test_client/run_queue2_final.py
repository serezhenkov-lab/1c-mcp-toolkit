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
    if '--remaining-only' not in sys.argv:
        selection=args(action='select',session_id=sid,window=window,element={'selector':{'name':'Выбор'}},params={'choice':{'list_value':'ABSENT_QUEUE2_FINAL'}})
        rejected=complete('test_input',selection)
        if '--before' in sys.argv:
            check('reproduced_selection_misclassified',rejected['execution']=='invoked' and rejected['error']['code']=='element_not_found' and rejected['data']['diagnostics']['errors']['observation'] is not None,rejected)
        else:
            check('selection_command_error_after_steps',rejected['execution']=='invoked' and rejected['error']['code']=='element_not_found' and rejected['error']['stage']=='resolve' and rejected['data']['diagnostics']['errors']['command'] is not None and rejected['data']['diagnostics']['errors']['observation'] is None,rejected)
            replay=complete('test_input',selection)
            check('selection_no_repeat',replay==rejected,replay)
            check('confirmed_steps_retained',rejected['data']['diagnostics']['last_confirmed_step']=='open_choice_list' and rejected['data']['diagnostics']['progress']['completed_count']==2,rejected['data']['diagnostics'])
    if '--before' not in sys.argv and '--production' not in sys.argv:
        before=code('Результат=ФормаМенеджераТестирования.ПробаАктивнойКнопки(Истина);')
        observed=complete('test_inspect',args(action='tree',session_id=sid,window=window))
        after=code('Результат=ФормаМенеджераТестирования.ПробаАктивнойКнопки();')
        editor=observed['data']['editor']
        check('button_editor_api_unavailable',all(editor[k]['available'] is False and editor[k]['value'] is None and editor[k]['reason']=='property_read_failed' for k in ('editing','text')) and editor['choice_list']=={'available':False,'value':None,'reason':'not_an_input_field'},editor)
        check('button_editor_read_unchanged',before==after and before['name']=='Проверить',{'before':before,'after':after})
        if '--window-probe' in sys.argv:
            opened=complete('test_action',args(action='click',session_id=sid,window=window,element={'selector':{'name':'ДругоеОкно'}}))
            import ctypes
            from ctypes import wintypes
            u=ctypes.WinDLL('user32',use_last_error=True)
            u.GetWindow.argtypes=[wintypes.HWND,wintypes.UINT];u.GetWindow.restype=wintypes.HWND
            CALLBACK=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
            found=[]
            @CALLBACK
            def find(hwnd,unused):
                pid=wintypes.DWORD();u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                if pid.value==testclient.pid and u.IsWindowVisible(hwnd):
                    title=ctypes.create_unicode_buffer(512);u.GetWindowTextW(hwnd,title,512)
                    found.append({'hwnd':hwnd,'owner':u.GetWindow(hwnd,4),'title':title.value})
                return True
            u.EnumWindows(find,0)
            (run/'native-windows.json').write_text(json.dumps(found,ensure_ascii=False,indent=2),encoding='utf8')
            candidates=[w for w in found if not w['owner']]
            refused=screenshot('second-window',target='test_client',session_id=sid)
            check('two_real_unowned_windows',len(candidates)>1,{'windows':found,'opened':opened})
            check('ambiguous_no_png','image_sha256' not in refused and 'ambiguous_window' in json.dumps(refused),refused)
    print(json.dumps({'route':route,'passed':len(checks)}))
finally:
    for p in reversed(owned):stop(p)
    (run/'cleanup.json').write_text(json.dumps({'owned':[p.pid for p in owned],'all_exited':all(p.poll() is not None for p in owned)}),encoding='utf8')
