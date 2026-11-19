"""Latency during explicit compaction rounds; payloads are not archived."""
import json
from pathlib import Path
import sys
import time
import httpx
import asyncio

run=Path(__file__).resolve().parents[2]/'.local/lifecycle-limits'
if len(sys.argv)>2:run=Path(sys.argv[2])
name=sys.argv[1]
report=run/(name+'.json')
seed=next(x for x in json.loads((run/'seeds.json').read_text()) if x['name']==name)
samples=[]
c=httpx.Client(base_url='http://127.0.0.1:17661',timeout=2)

def read_report():
    deadline=time.monotonic()+5
    while True:
        try:return json.loads(report.read_text(encoding='utf-8-sig'))
        except (PermissionError,json.JSONDecodeError):
            if time.monotonic()>=deadline:raise
            time.sleep(.02)

def probe(phase):
    for endpoint in (('health','status') if phase in ('baseline','final') or '--all-reads' in sys.argv else ('health',)):
        started=time.perf_counter()
        item=dict(phase=phase,endpoint=endpoint,started_unix_ms=time.time()*1000)
        try:
            if endpoint=='health':r=c.get('/health')
            else:r=c.post('/api/test_session?channel=test',json=dict(request_id='latency-'+name,action='status',params={'operation_id':seed['keep_id']}))
            item.update(http=r.status_code,bytes=len(r.content))
            if endpoint=='status':
                body=r.json()
                error=body.get('error')
                item.update(status=body.get('status'),code=error.get('code') if isinstance(error,dict) else error)
        except Exception as e:item['error']=type(e).__name__
        item['elapsed_ms']=(time.perf_counter()-started)*1000
        samples.append(item)
        (run/(name+'-http.json')).write_text(json.dumps(samples,indent=2),encoding='utf-8')

try:
    probe('baseline')
    round_count=1 if seed.get('count',0)>=10000 or seed['bytes']>=8*1024*1024 else 3
    for number in range(1,round_count+1):
        (run/(name+'.go')).write_text(str(number),encoding='utf-8')
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            probe(f'round-{number}')
            value=read_report()
            if len(value['rounds'])>=number and value['rounds'][number-1]['ms']>0:break
            time.sleep(.1)
        else:raise TimeoutError('compaction timeout')
        probe(f'after-{number}')
    probe('final')
    async def native_status():
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client('http://127.0.0.1:17661/mcp?channel=test') as streams:
            async with ClientSession(streams[0],streams[1]) as session:
                await session.initialize()
                result=await session.call_tool('test_session',dict(request_id='native-'+name,action='status',params={'operation_id':seed['keep_id']}))
                data=json.loads(next(block.text for block in result.content if block.type=='text'))
                nested=(data.get('data') or {}).get('operation') or {}
                (run/(name+'-native.json')).write_text(json.dumps(dict(status=data.get('status'),error=data.get('error'),
                    operation_id=data.get('operation_id'),target_id=nested.get('operation_id'),target_status=nested.get('status'))),encoding='utf-8')
    asyncio.run(asyncio.wait_for(native_status(),timeout=15))
    print(name,'compaction_ms',[x['ms'] for x in value['rounds']],
          'HTTP timeouts',sum(x.get('error','').endswith('Timeout') for x in samples),
          'HTTP 503',sum(x.get('http')==503 for x in samples))
finally:
    (run/(name+'.stop')).write_text('stop owned fixture',encoding='utf-8')
