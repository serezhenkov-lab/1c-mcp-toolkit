"""Native TI-05 sequence and exact-reference cleanup in a disposable stand.

Run only via run_native_document.py http --batch --source-db ... --epf ... .
No mutation is retried after an exception, timeout or unknown.
"""
import json
from pathlib import Path
import sys
import time
import uuid
import httpx

run = Path(sys.argv[1]).resolve()
root = Path(__file__).resolve().parents[2]
assert run.is_relative_to(root / '.local') and run.name in ('http', 'file', 'embedded')
state = json.loads((run / 'state.json').read_text(encoding='utf-8'))
client = httpx.Client(base_url=f'http://127.0.0.1:{state["port"]}', timeout=30, trust_env=False)
sid = state['sid']
marker = 'NATIVE_CLEANUP:' + uuid.uuid4().hex
checks = []

def save(name, value):
    (run / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def check(name, condition, evidence=None):
    checks.append(dict(name=name, ok=bool(condition), evidence=evidence))
    save('scenario-proof', dict(marker=marker, checks=checks))
    assert condition, (name, evidence)

def call(tool, **kw):
    arguments = {'request_id': str(uuid.uuid4()), 'params': {}, **kw}
    if tool.startswith('test_'):
        arguments['session_id'] = sid
    result = client.post('/api/' + tool, params={'channel': 'queue1'}, json=arguments).json()
    with (run / 'scenario-actions.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(dict(tool=tool, args=arguments, result=result), ensure_ascii=False) + '\n')
    for _ in range(240):
        if result.get('status') not in ('queued', 'running', 'awaiting_approval'):
            break
        time.sleep(.25)
        result = client.post('/api/test_session', params={'channel': 'queue1'}, json={
            'request_id': str(uuid.uuid4()), 'action': 'status',
            'params': {'operation_id': result['operation_id']}}).json()['data']['operation']
    with (run / 'scenario-terminal.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(dict(tool=tool, args=arguments, result=result), ensure_ascii=False) + '\n')
    return result

def code(text):
    result = call('execute_code', code=text, execution_context='server')
    while isinstance(result, dict) and 'success' in result:
        assert result['success'], result
        result = result.get('data', result.get('result'))
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            pass
    return result

def rows():
    result = call('execute_query', query='ВЫБРАТЬ Ссылка, Номер, Дата, ОбязательноеПоле, ПометкаУдаления ИЗ Документ.T43_Required', limit=1000)
    assert result.get('success') is True and isinstance(result.get('data'), list), result
    assert len(result['data']) < 1000, 'Cannot prove complete baseline'
    return {r['Ссылка']['УникальныйИдентификатор']: r for r in result['data']}

def click(window, name):
    return call('test_action', action='click', window=window, element={'selector': {'name': name}})

connection = code('Результат=СтрокаСоединенияИнформационнойБазы();')
check('query_base_matches_isolated_manager_and_client', str(run / 'db').casefold().replace('\\', '/') in str(connection).casefold().replace('\\', '/'), connection)
before = rows()
save('baseline', before)
check('fresh_marker', not any(r['ОбязательноеПоле'] == marker for r in before.values()))
created = click({'selector': {'form_name': 'Документ.T43_Required.ФормаСписка'}}, 'ФормаСоздать')
check('native_form_created', created.get('status') == 'succeeded', created)
w = {'selector': {'form_name': 'Документ.T43_Required.ФормаОбъекта'}}
tree = call('test_inspect', action='tree', window=w)
save('native-tree', tree)
check('native_tree_available', tree.get('status') == 'succeeded')
date = call('test_input', action='text', window=w, element={'selector': {'name': 'Дата'}}, params={'text': '17.11.2026 12:00:00'})
check('date_entered', date.get('status') == 'succeeded', date)
# Number remains the native automatic number; the modal-number regression is separate.
rejected = click(w, 'ФормаЗаписать')
messages = call('test_inspect', action='messages', window=w)
after_reject = rows()
save('required-rejection', dict(action=rejected, messages=messages, rows=after_reject))
check('required_refusal_has_message_and_no_write', rejected.get('status') == 'succeeded' and after_reject == before and
      any('не заполнено' in m.get('text', '') for m in messages.get('data', {}).get('messages', [])))
filled = call('test_input', action='text', window=w, element={'selector': {'name': 'ОбязательноеПоле'}}, params={'text': marker})
check('required_value_corrected', filled.get('status') == 'succeeded' and filled.get('data', {}).get('actual') == marker, filled)
written = click(w, 'ФормаЗаписать')
after = rows()  # reconciliation is a read even if the write reply is ambiguous
save('written', dict(action=written, rows=after))
added = set(after) - set(before)
check('exactly_one_new_reference', len(added) == 1 and len(after) == len(before) + 1, list(added))
reference = added.pop()
row = after[reference]
check('new_document_values', row['ОбязательноеПоле'] == marker and row['Дата'] == '2026-11-17T12:00:00Z' and bool(row['Номер']) and not row['ПометкаУдаления'], row)
check('baseline_unchanged_after_write', all(after[k] == v for k, v in before.items()))
check('native_write_confirmed', written.get('status') == 'succeeded', written)
closed = call('test_action', action='close', window=w)
check('saved_form_closed', closed.get('status') == 'succeeded', closed)
save('cleanup-target', dict(reference=reference, marker=marker, row=row))
# Authorized cleanup only of this run's observed new reference; never by broad filter.
# Test role lacks Delete. Privileged mode is confined to this server call and restored.
path = str(run / 'db').replace('"', '""')
cleanup = code(f'''
Если СтрНайти(НРег(СтрокаСоединенияИнформационнойБазы()), НРег("{path}")) = 0 Тогда ВызватьИсключение "Cleanup base mismatch"; КонецЕсли;
СтарыйРежим = ПривилегированныйРежим();
Попытка
    УстановитьПривилегированныйРежим(Истина);
    НачатьТранзакцию();
    СсылкаТеста = Документы.T43_Required.ПолучитьСсылку(Новый УникальныйИдентификатор("{reference}"));
    ОбъектТеста = СсылкаТеста.ПолучитьОбъект();
    Если ОбъектТеста = Неопределено Тогда ВызватьИсключение "Cleanup target absent"; КонецЕсли;
    Если ОбъектТеста.ОбязательноеПоле <> "{marker}" Тогда ВызватьИсключение "Cleanup marker mismatch"; КонецЕсли;
    ОбъектТеста.Удалить();
    ЗафиксироватьТранзакцию();
    УстановитьПривилегированныйРежим(СтарыйРежим);
    Результат = Истина;
Исключение
    Если ТранзакцияАктивна() Тогда ОтменитьТранзакцию(); КонецЕсли;
    УстановитьПривилегированныйРежим(СтарыйРежим);
    ВызватьИсключение;
КонецПопытки;''')
check('exact_reference_cleanup_completed', cleanup is True, cleanup)
final = rows()
save('after-cleanup', final)
check('baseline_restored_exactly', final == before, dict(before_count=len(before), after_count=len(final), deleted=reference))
check('deleted_reference_and_marker_absent', reference not in final and not any(r['ОбязательноеПоле'] == marker for r in final.values()))
context = code('Результат=Новый Структура("privileged,transaction", ПривилегированныйРежим(), ТранзакцияАктивна());')
check('cleanup_context_restored', context == dict(privileged=False, transaction=False), context)
print(json.dumps(dict(passed=len(checks), reference=reference, cleanup=True)))
