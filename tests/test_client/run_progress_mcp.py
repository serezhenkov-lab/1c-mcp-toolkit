"""Intermediate lifecycle progress through native MCP on the isolated 8.5 stand."""
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
prefix=prefix.replace("run = stand / route", "run = stand / ('mcp-' + route)")
if '--legacy-owner' in sys.argv:
    prefix=prefix.replace("run = stand / ('mcp-' + route)", "run = stand / 'legacy-file'")
    # Only the test proxy omits the new capability, as an older owner would.
    launcher = "from onec_mcp_toolkit_proxy.command_queue import Command; original=Command.to_dict; Command.to_dict=lambda self: {k:v for k,v in original(self).items() if k!='lifecycle_progress_version'}; import uvicorn; uvicorn.run('onec_mcp_toolkit_proxy.server:app',host='127.0.0.1',port=17670,log_level='warning')"
    prefix=prefix.replace("[sys.executable, '-B', '-m', 'uvicorn', 'onec_mcp_toolkit_proxy.server:app',\n                   '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning']", "[sys.executable, '-B', '-c', " + repr(launcher) + "]")
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
    import asyncio
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async def native_test():
        async with streamablehttp_client(f'http://127.0.0.1:{port}/mcp?channel=queue1') as streams:
            async with ClientSession(streams[0],streams[1]) as session:
                await session.initialize()
                response=await session.call_tool('test_expect',args(session_id=sid,window=window,element={'selector':{'name':'Текст'}},timeout_ms=4000,params={'condition':{'property':'value','operator':'equals','value':'NEVER_MCP_PROGRESS'}}))
                result=json.loads(response.content[0].text);operation=result['operation_id'];samples=[]
                for _ in range(60):
                    response=await session.call_tool('test_session',args(action='status',params={'operation_id':operation}))
                    result=json.loads(response.content[0].text)['data']['operation']
                    p=(result.get('data') or {}).get('progress')
                    if p:samples.append(p)
                    if result['status'] not in ('queued','running','awaiting_approval'):break
                    await asyncio.sleep(.2)
                if '--legacy-owner' in sys.argv:
                    check('legacy_owner_no_progress',not samples,samples)
                else:
                    check('native_mcp_intermediate',bool(samples) and all(p['operation_id']==operation and p['scope']=='intermediate_snapshot' and p['last_confirmed_step'] is None for p in samples),samples)
                check('native_mcp_terminal',result['status']=='failed' and result['error']['code']=='expectation_timeout' and 'progress' not in result['data'],result)
    asyncio.run(native_test())
    print(json.dumps({'route':'mcp-'+route,'passed':len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
