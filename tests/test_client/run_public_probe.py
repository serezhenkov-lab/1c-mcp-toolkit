"""Real native MCP and REST calls against the isolated 8.5 manager."""
import os
import asyncio
import json
from pathlib import Path
import uuid
import sys
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

file_mode = '--file' in sys.argv
embedded = '--embedded' in sys.argv
run = Path(__file__).resolve().parents[2] / ('.local/embedded-lifecycle' if embedded else '.local/queue1-file' if file_mode else '.local/queue1')
base = 'http://127.0.0.1:' + ('17657' if embedded else '17656' if file_mode else '17655')
if embedded:
    run = Path(os.environ.get('TOOLKIT_STAND_DIR', str(run)))
    base = os.environ.get('TOOLKIT_STAND_URL', base)
events = []


async def main():
    async with httpx.AsyncClient(timeout=10) as http:
        async def call(tool, args):
            result = (await http.post(base + '/api/' + tool + '?channel=queue1', json=args)).json()
            events.append({'tool': tool, 'args': args, 'result': result})
            (run / 'public-probe.json').write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')
            return result

        async def complete(tool, args):
            result = await call(tool, args)
            identifier = result.get('operation_id')
            for _ in range(130):
                if result['status'] not in ('queued', 'running', 'awaiting_approval'):
                    return result
                await asyncio.sleep(.5)
                status = await call('test_session', {'request_id': str(uuid.uuid4()), 'action': 'status',
                                                     'params': {'operation_id': identifier}})
                result = status.get('data', {}).get('operation', status)
            raise AssertionError(result)

        async with streamablehttp_client(base + '/mcp?channel=queue1') as streams:
            async with ClientSession(streams[0], streams[1]) as mcp:
                await mcp.initialize()
                names = {tool.name for tool in (await mcp.list_tools()).tools}
                assert {'test_session', 'test_open', 'test_inspect', 'test_input', 'test_action', 'test_table', 'test_expect'} <= names
                native = await mcp.call_tool('test_session', {'request_id': 'native-status', 'action': 'status', 'params': {}})
                events.append({'native_status': native.model_dump(mode='json')})
        start_args = {'request_id': 'public-start', 'action': 'start', 'params': {'profile_id': 'queue1'}}
        start = await complete('test_session', start_args)
        assert start['status'] == 'succeeded', start
        sid = start['session_id']
        (run / 'session.json').write_text(json.dumps(start, ensure_ascii=False, indent=2), encoding='utf-8')
        repeat = await call('test_session', {**start_args, 'timeout_ms': 120000})
        assert repeat['operation_id'] == start['operation_id'] and repeat['status'] == 'succeeded', repeat
        conflict = await call('test_session', {**start_args, 'timeout_ms': 1})
        assert conflict['error']['code'] == 'request_conflict', conflict
        windows = await complete('test_inspect', dict(request_id='public-windows', session_id=sid, action='windows', params={}))
        assert windows['status'] == 'succeeded', windows
        window = {'id': windows['data']['windows'][0]['window_id']}
        activated = await complete('test_action', dict(request_id='public-activate', session_id=sid,
                                                     action='activate_window', window=window, params={}))
        assert activated['status'] == 'succeeded', activated
        args = dict(request_id='public-expect', session_id=sid, window=window, timeout_ms=5000,
                    params={'condition': {'property': 'title', 'operator': 'equals', 'value': 'never-this-title'}})
        waiting = await call('test_expect', args)
        await asyncio.sleep(1)
        pending = await call('test_session', dict(request_id='during-expect', action='status',
                                                params={'operation_id': waiting['operation_id']}))
        assert pending['data']['operation']['status'] == 'running', pending
        repeat_wait = await call('test_expect', args)
        assert repeat_wait['operation_id'] == waiting['operation_id']
        expired = await complete('test_expect', args)
        assert expired['error']['code'] == 'expectation_timeout', expired
        for tool, action, params in [('test_input', 'text', {'text': 'not-written'}), ('test_table', 'read', {})]:
            missing = await complete(tool, dict(request_id='public-' + tool, session_id=sid, window=window,
                                               action=action, element={'selector': {'name': 'DefinitelyMissing'}}, params=params))
            assert missing['status'] == 'failed', missing
        opened = await complete('test_open', dict(request_id='public-open', session_id=sid, window=window,
                                                 params={'link': 'e1cib/list/Документ.T43_Required'}))
        assert opened['status'] in ('succeeded', 'failed'), opened
        print(json.dumps({'start': start, 'windows': windows}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
