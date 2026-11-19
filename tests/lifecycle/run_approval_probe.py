"""Read actual native lifecycle while real 1C confirmation stays open for 3 seconds."""
import asyncio
import json
from pathlib import Path
import uuid
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

run = Path(__file__).resolve().parents[2] / '.local/lifecycle-approval'

async def main():
    results = []
    async with streamablehttp_client('http://127.0.0.1:17654/mcp?channel=lifecycle-approval') as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            async def call(name, **args):
                response = await session.call_tool(name, args)
                return json.loads('\n'.join(c.text for c in response.content if hasattr(c, 'text')))
            async def wait(op, args=None):
                states = []
                repeat_checked = False
                for _ in range(200):
                    status = await call('get_operation', operation_id=op)
                    assert status['success'], status
                    if not states or states[-1] != status['status']:
                        states.append(status['status'])
                        print(op, states, flush=True)
                    if status['status'] == 'awaiting_approval' and args and not repeat_checked:
                        repeated = await call('execute_code_operation', **args)
                        assert repeated['operation_id'] == op and repeated['status'] == 'awaiting_approval'
                        repeat_checked = True
                    if status['status'] in ('succeeded', 'failed', 'rejected', 'unknown'):
                        return status, states
                    await asyncio.sleep(.2)
                raise AssertionError(f'operation {op} did not finish: {states}')
            for label, reason in [('DENY', 'mode_deny'), ('REJECT', 'user_declined'), ('CLOSE', 'user_declined'),
                                  ('STALE', 'approval_stale'), ('ALLOW', None), ('SESSION', None)]:
                number = uuid.uuid4().hex[:11]
                code = (f'// CASE_{label}\nД = Документы.T43_Required.СоздатьДокумент(); '
                        f'Д.Номер = "{number}"; Д.Дата = ТекущаяДата(); '
                        f'Д.ОбязательноеПоле = "CASE_{label}"; Д.Записать(); Результат = "CASE_{label}";')
                args = dict(request_id=str(uuid.uuid4()), code=code, wait_timeout_ms=1)
                first = await call('execute_code_operation', **args)
                final, states = await wait(first['operation_id'], args)
                assert final['status'] == ('rejected' if reason else 'succeeded'), final
                if reason:
                    assert final['result']['rejection_reason'] == reason, final
                if label != 'DENY':
                    assert 'awaiting_approval' in states, states
                else:
                    assert 'awaiting_approval' not in states
                repeated = await call('execute_code_operation', **args)
                assert repeated['operation_id'] == final['operation_id'] and repeated['status'] == final['status']
                query = ('З = Новый Запрос("ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК Количество ИЗ Документ.T43_Required КАК Д ГДЕ Д.Номер = &Номер"); '
                         f'З.УстановитьПараметр("Номер", "{number}"); В = З.Выполнить().Выбрать(); В.Следующий(); Результат = В.Количество;')
                check = await call('execute_code_operation', request_id=str(uuid.uuid4()), code=query)
                count, _ = await wait(check['operation_id'])
                assert count['status'] == 'succeeded' and count['result']['data'] == (0 if reason else 1), count
                results.append(dict(case=label, states=states, final=final, count=count['result']['data'], number=number))
                (run / 'probe.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
                print('PASS', label, flush=True)

asyncio.run(main())
