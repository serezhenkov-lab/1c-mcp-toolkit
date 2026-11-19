"""Native MCP probe of a disposable real 1C client; phases around proxy restart."""
import asyncio
import json
from pathlib import Path
import sys
import uuid
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

run = Path(__file__).resolve().parents[2] / '.local/lifecycle'
state_file = run / 'probe.json'

async def main():
    phase = sys.argv[1]
    state = json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {'checks': []}
    async with streamablehttp_client('http://127.0.0.1:17653/mcp?channel=lifecycle-test') as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            async def call(name, **args):
                response = await session.call_tool(name, args)
                text = '\n'.join(c.text for c in response.content if hasattr(c, 'text'))
                result = json.loads(text)
                print(name, json.dumps(result, ensure_ascii=False), flush=True)
                return result
            async def status(op):
                return await call('get_operation', operation_id=op)
            async def wait(op):
                for _ in range(60):
                    s = await status(op)
                    if s.get('status') in ('succeeded', 'failed', 'unknown'):
                        return s
                    await asyncio.sleep(.5)
                raise AssertionError('operation did not finish')
            async def write_case(label):
                number = uuid.uuid4().hex[:11]
                key = str(uuid.uuid4())
                code = ('Д = Документы.T43_Required.СоздатьДокумент(); '
                        f'Д.Номер = "{number}"; Д.Дата = ТекущаяДата(); '
                        f'Д.ОбязательноеПоле = "LIFECYCLE_{label}"; Д.Записать(); '
                        f'Результат = "LIFECYCLE_{label}";')
                args = dict(request_id=key, code=code, wait_timeout_ms=1)
                first = await call('execute_code_operation', **args)
                assert first['status'] in ('queued', 'running'), first
                repeated = await call('execute_code_operation', **args)
                assert first['operation_id'] == repeated['operation_id']
                conflict = await call('execute_code_operation', request_id=key, code=code+' Результат = 2;')
                assert conflict['error'] == 'request_conflict'
                state[label] = dict(args=args, number=number, operation_id=first['operation_id'])
                state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
                return first['operation_id']
            if phase == 'before':
                names = {t.name for t in (await session.list_tools()).tools}
                assert {'execute_code_operation', 'get_operation'} <= names
                op = await write_case('LATE')
                for _ in range(60):
                    if (run / 'delayed-result.json').exists():
                        break
                    await asyncio.sleep(.25)
                assert (await status(op))['status'] == 'running'
                state['late_result'] = await wait(op)
                assert state['late_result']['status'] == 'succeeded'
                state['checks'].append('native timeout, repeat, conflict and late success')
                op = await write_case('DROP')
                for _ in range(60):
                    if (run / 'dropped-result.json').exists():
                        break
                    await asyncio.sleep(.25)
                assert (run / 'dropped-result.json').exists()
                assert (await status(op))['status'] == 'running'
            elif phase == 'after':
                unknown = await status(state['DROP']['operation_id'])
                assert unknown['status'] == 'unknown' and unknown['error'] == 'executor_restarted'
                repeated = await call('execute_code_operation', **state['DROP']['args'])
                assert repeated['operation_id'] == unknown['operation_id'] and repeated['status'] == 'unknown'
                assert (await status(state['LATE']['operation_id']))['status'] == 'succeeded'
                state['unknown_result'] = unknown
                state['checks'].append('restart preserves success; lost response unknown; repeat never requeues')
                for label in ('LATE', 'DROP'):
                    number = state[label]['number']
                    code = ('З = Новый Запрос("ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК Количество ИЗ Документ.T43_Required КАК Д ГДЕ Д.Номер = &Номер"); '
                            f'З.УстановитьПараметр("Номер", "{number}"); В = З.Выполнить().Выбрать(); В.Следующий(); Результат = В.Количество;')
                    op = await call('execute_code_operation', request_id=str(uuid.uuid4()), code=code)
                    result = await wait(op['operation_id'])
                    state[label]['count_result'] = result
                    assert result['status'] == 'succeeded', result
                    assert str(result['result']['data']) == '1', result
                state['checks'].append('both documents exist exactly once in isolated database')
            else:
                raise ValueError(phase)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

asyncio.run(main())
