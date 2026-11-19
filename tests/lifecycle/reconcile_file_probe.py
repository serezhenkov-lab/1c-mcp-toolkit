"""Read-only data reconciliation for the preserved failed disposable file run."""
import asyncio
import json
from pathlib import Path
import uuid
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

run = Path(__file__).resolve().parents[2] / '.local/lifecycle-approval'
async def main():
    request_path = max((run / 'bridge').rglob('*.running'), key=lambda p: p.stat().st_mtime)
    request = json.loads(request_path.read_text(encoding='utf-8'))
    import re
    number = re.search(r'Д.Номер = "([a-f0-9]+)"', request['params']['code'])[1]
    code = ('З = Новый Запрос("ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК Количество ИЗ Документ.T43_Required КАК Д ГДЕ Д.Номер = &Номер"); '
            f'З.УстановитьПараметр("Номер", "{number}"); В = З.Выполнить().Выбрать(); В.Следующий(); Результат = В.Количество;')
    async with streamablehttp_client('http://127.0.0.1:17654/mcp?channel=lifecycle-approval') as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            async def call(name, args):
                r = await session.call_tool(name, args)
                return json.loads('\n'.join(x.text for x in r.content if hasattr(x, 'text')))
            args = dict(request_id=str(uuid.uuid4()), code=code)
            for _ in range(30):
                op = await call('execute_code_operation', args)
                if op.get('error') != 'consumer_unavailable':
                    break
                await asyncio.sleep(1)
            assert 'operation_id' in op, op
            for _ in range(60):
                result = await call('get_operation', dict(operation_id=op['operation_id']))
                if result['status'] in ('succeeded','failed','unknown'):
                    break
                await asyncio.sleep(.5)
            assert result['status'] == 'succeeded' and result['result']['data'] == 0, result
            (run / 'file-reconciliation.json').write_text(json.dumps(dict(original_operation=request['id'], number=number, result=result), ensure_ascii=False, indent=2), encoding='utf-8')
            print('Confirmed zero documents for original unresolved file command; no replay')
asyncio.run(main())
