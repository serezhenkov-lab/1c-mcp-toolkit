"""Queue2 acceptance: real 1C UI, native capture, bounded diagnostic fault hooks."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("'.local/queue1-finish'", "'.local/queue2'")
# Explicit user approval covers the visible test client and the test manager.
prefix = prefix.replace('startupinfo.wShowWindow = 0', 'startupinfo.wShowWindow = 5')
prefix = prefix.replace("run = stand / route", "run = stand / 'production'")
prefix = prefix.replace("str(stand / 'Toolkit.epf')", "str(stand / 'Toolkit-production.epf')")
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
    check('readonly_diagnostics', windows['data']['diagnostics']['complete'] and windows['data']['diagnostics']['progress']['completed_count'] == 0, windows['data']['diagnostics'])
    window = {'id': next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])}
    shot = screenshot('client', target='test_client', session_id=sid)
    check('verified_client_image', shot.get('success') and shot.get('capture_target', {}).get('process_id') == testclient.pid and shot.get('session_id') == sid and shot.get('png_signature') == '89504e470d0a1a0a', shot)
    import asyncio
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async def mcp_capture():
        async with streamablehttp_client(f'http://127.0.0.1:{port}/mcp?channel=queue1') as streams:
            async with ClientSession(streams[0],streams[1]) as session:
                await session.initialize()
                response = await session.call_tool('get_screenshot', {'target':'test_client','session_id':sid})
                metadata = [json.loads(p.text) for p in response.content if p.type == 'text']
                proof = next((p for p in metadata if 'capture_target' in p), {})
                check('native_mcp_capture_identity', any(p.type=='image' for p in response.content) and proof.get('capture_target',{}).get('process_id')==testclient.pid and proof.get('session_id')==sid, proof)
    asyncio.run(mcp_capture())
    detached = complete('test_session', args(action='detach', session_id=sid))
    denied = screenshot('detached', target='test_client', session_id=sid)
    check('detached_target_no_image', detached['status'] == 'succeeded' and not denied.get('success') and 'image_sha256' not in denied, denied)
    print(json.dumps({'route': route, 'passed': len(checks)}))
finally:
    for p in reversed(owned):
        stop(p)
    (run / 'cleanup.json').write_text(json.dumps({'owned': [p.pid for p in owned], 'all_exited': all(p.poll() is not None for p in owned)}), encoding='utf-8')
