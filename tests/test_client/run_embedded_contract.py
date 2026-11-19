"""Public MCP schemas/calls and differential REST request validation on the stand."""
import os
import asyncio
import copy
import json
from pathlib import Path
import sys
import uuid
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from onec_mcp_toolkit_proxy.test_client_contract import INPUT_SCHEMAS, valid_request
run = root / '.local/embedded-lifecycle'
run = Path(os.environ.get('TOOLKIT_STAND_DIR', str(run)))
endpoint = os.environ.get('TOOLKIT_STAND_URL','http://127.0.0.1:17657')
events = []

async def main():
    window = {'active': True}
    common = dict(session_id='nonexistent-session', window=window, params={})
    cases = {
        'test_session': dict(action='status', params={}),
        'test_open': dict(**{**common,'params':{'link':'e1cib/list/Документ.T43_Required'}}),
        'test_inspect': dict(session_id='nonexistent-session',action='windows',params={}),
        'test_input': dict(**{**common,'params':{'checked':True}}, action='check',element={'selector':{'name':'x'}}),
        'test_action': dict(**common,action='activate_window'),
        'test_table': dict(**common,action='read',element={'selector':{'name':'x'}}),
        'test_expect': dict(**{**common,'params':{'condition':{'property':'exists','operator':'equals','value':False}}}),
    }
    async with streamablehttp_client(endpoint+'/mcp?channel=queue1') as streams:
        async with ClientSession(streams[0],streams[1]) as mcp:
            await mcp.initialize()
            schemas = {x.name:x.inputSchema for x in (await mcp.list_tools()).tools}
            for tool,expected in INPUT_SCHEMAS.items():
                assert {**schemas[tool], 'type':'object'} == {**expected,'type':'object'}, tool
            for tool,params in cases.items():
                args = dict(request_id=str(uuid.uuid4()),**params)
                r = await mcp.call_tool(tool,args)
                value = json.loads(r.content[0].text)
                assert value['contract_version']=='1' and value['operation_id'], value
                events.append(dict(transport='mcp',tool=tool,args=args,result=value))
    async with httpx.AsyncClient(timeout=10) as c:
        count=0
        for tool,params in cases.items():
            base=dict(request_id=str(uuid.uuid4()),**params)
            variants=[base,{**base,'unexpected':1},{**base,'timeout_ms':True},{**base,'timeout_ms':-1},
                      {**base,'timeout_ms':300001},{**base,'timeout_ms':1.5},{**base,'request_id':''},
                      {**base,'request_id':'x'*129}, {**base,'timeout_ms':0.0}]
            if 'action' in base:variants.append({**base,'action':base['action'].upper()})
            if 'element' in base:variants.append({**base,'element':{'selector':{}}})
            for args in variants:
                args=copy.deepcopy(args)
                if args['request_id']==base['request_id']: args['request_id']=str(uuid.uuid4())
                r=(await c.post(endpoint+'/api/'+tool+'?channel=queue1',json=args)).json()
                admitted=r.get('operation_id') is not None
                assert admitted==valid_request(tool,args),(tool,args,r)
                events.append(dict(transport='rest',tool=tool,args=args,result=r))
                count+=1
    (run/'contract-probe.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'7 native MCP schemas/calls; {count} differential REST cases passed')

asyncio.run(main())
