"""Drop the HTTP reply after a real UI commit, then retry the identical request.

The relay buffers the async accepted reply, polls until terminal, and closes the
caller socket without sending headers/body. Toolkit code/journals are unmodified.
Each fixture click unconditionally creates a new document (no fixture dedup).
"""
import hashlib
import json
import socket
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[2]
route = sys.argv[1]
run = root / '.local/lost-response' / route
port = {'http': 17669, 'file': 17670, 'embedded': 17671}[route]
client = httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=30)
marker = f'LOSS:{route}:{uuid.uuid4().hex}'
events, checks = [], []

def save():
    (run / 'results.json').write_text(json.dumps({'route': route, 'marker': marker, 'checks': checks, 'events': events}, ensure_ascii=False, indent=2), encoding='utf-8')

def check(name, condition, evidence=None):
    checks.append({'name': name, 'ok': bool(condition), 'evidence': evidence})
    save()
    assert condition, (name, evidence)

def call(tool, args):
    r = client.post('/api/' + tool, params={'channel': 'queue1'}, json=args)
    value = r.json()
    events.append({'tool': tool, 'args': args, 'http': r.status_code, 'result': value})
    save()
    return value

def code(text, context='client'):
    r = call('execute_code', {'code': text, 'execution_context': context})
    while isinstance(r, dict) and 'success' in r:
        assert r['success'], r
        r = r.get('data', r.get('result'))
    if isinstance(r, str):
        try:
            r = json.loads(r)
        except json.JSONDecodeError:
            pass
    return r

def args(**kw):
    return {'request_id': str(uuid.uuid4()), 'params': {}, **kw}

def complete(tool, arguments):
    value = call(tool, arguments)
    for _ in range(240):
        if value.get('status') not in ('queued', 'running', 'awaiting_approval'):
            return value
        time.sleep(.25)
        value = call('test_session', args(action='status', params={'operation_id': value['operation_id']})).get('data', {}).get('operation', {})
    raise AssertionError(value)

def query(query_marker=None):
    query_marker = query_marker or marker
    return code('ЗапросТеста = Новый Запрос("ВЫБРАТЬ Ссылка, Номер, ОбязательноеПоле, ПометкаУдаления ИЗ Документ.T43_Required ГДЕ ОбязательноеПоле = &Маркер"); '
                f'ЗапросТеста.УстановитьПараметр("Маркер", "{query_marker}"); '
                'Результат = Новый Массив; ВыборкаТеста = ЗапросТеста.Выполнить().Выбрать(); Пока ВыборкаТеста.Следующий() Цикл '
                'Результат.Добавить(Новый Структура("reference,number,marker,deletion_mark", Строка(ВыборкаТеста.Ссылка.УникальныйИдентификатор()), ВыборкаТеста.Номер, ВыборкаТеста.ОбязательноеПоле, ВыборкаТеста.ПометкаУдаления)); КонецЦикла;', 'server')

def traces(query_marker=None):
    path = run.parent / 'ui-invocations.jsonl'
    if not path.exists():
        return []
    text = path.read_text(encoding='utf-8-sig')
    values = []
    decoder = json.JSONDecoder()
    while text.strip():
        value, end = decoder.raw_decode(text.lstrip())
        values.append(value)
        text = text.lstrip()[end:]
    return [v for v in values if v['marker'] == (query_marker or marker)]

for _ in range(60):
    try:
        if client.get('/health', timeout=1).status_code == 200:
            break
    except httpx.HTTPError:
        pass
    time.sleep(1)
else:
    raise AssertionError('Stand HTTP not ready')
time.sleep(2)
r = code('ФорматОтветаВстроенный = 0; ИспользоватьТочнуюАнонимизацию = Ложь; РежимПодтвержденияОпасныхОпераций = "session_allow"; '
         'ТестПрофильID = "lost_response"; ТестПрофильПользователь = "ApiProbe"; ТестПрофильПорт = 16549; ТестПрофильВключен = Истина; '
         'ТестПрофильТребуетПароль = Ложь; СохранитьПрофильТестирования(Неопределено); Результат = ТестПрофильСтатус;')
check('production_profile_configured', isinstance(r, str) and r.startswith('Профиль сохранён'), r)
for _ in range(40):
    state = complete('test_session', args(action='status'))
    if (state.get('error') or {}).get('code') != 'operation_store_unavailable':
        break
    time.sleep(.25)
attached = complete('test_session', args(action='attach', params={'profile_id': 'lost_response'}))
check('public_attach', attached.get('status') == 'succeeded', attached)
sid = attached['session_id']
windows = complete('test_inspect', args(action='windows', session_id=sid))
check('windows_available', windows.get('status') == 'succeeded', windows)
window = {'id': next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])}
tree = complete('test_inspect', args(action='tree', session_id=sid, window=window))
check('fixture_tree', tree.get('status') == 'succeeded', tree)
filled = complete('test_input', args(action='text', session_id=sid, window=window,
                  element={'selector': {'name': 'Текст'}}, params={'text': marker}))
check('marker_entered_through_ui', filled.get('status') == 'succeeded', filled)
check('no_document_before_click', query() == [])
check('no_invocation_before_click', traces() == [])
write_args = args(action='click', session_id=sid, window=window, element={'selector': {'name': 'Диалог'}})
fault = {}

class DropReply(BaseHTTPRequestHandler):
    def log_message(self, *unused):
        pass

    def do_POST(self):
        try:
            payload = self.rfile.read(int(self.headers['Content-Length']))
            parsed = json.loads(payload)
            assert self.path == '/api/test_action' and parsed == write_args
            accepted = call('test_action', parsed)
            terminal = accepted
            for _ in range(240):
                if terminal.get('status') not in ('queued', 'running', 'awaiting_approval'):
                    break
                time.sleep(.25)
                terminal = call('test_session', args(action='status', params={'operation_id': accepted['operation_id']})).get('data', {}).get('operation', {})
            fault.update({'accepted': accepted, 'terminal': terminal, 'trace_before_socket_close': traces(),
                          'reply_bytes_sent': 0, 'request_sha256': hashlib.sha256(payload).hexdigest()})
            assert terminal.get('status') == 'succeeded', terminal
            assert sum(t['stage'] == 'committed' for t in traces()) == 1
        except Exception as exc:
            fault['relay_error'] = repr(exc)
        finally:
            (run / 'dropped-response.json').write_text(json.dumps(fault, ensure_ascii=False, indent=2), encoding='utf-8')
            # Real EOF before any HTTP response headers/body reach the caller.
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()

relay = ThreadingHTTPServer(('127.0.0.1', 17672), DropReply)
thread = threading.Thread(target=relay.serve_forever, daemon=True)
thread.start()
received = None
try:
    try:
        httpx.post('http://127.0.0.1:17672/api/test_action', json=write_args, timeout=90)
    except httpx.RemoteProtocolError as exc:
        received = type(exc).__name__
finally:
    relay.shutdown()
    relay.server_close()
    thread.join(timeout=5)
check('caller_lost_response_on_wire', received == 'RemoteProtocolError' and not fault.get('relay_error'), fault)
original = fault['terminal']
first_rows = query()
check('one_committed_document_before_retry', len(first_rows) == 1 and first_rows[0]['marker'] == marker and not first_rows[0]['deletion_mark'], first_rows)
for index in range(3):
    replay = complete('test_action', write_args)
    check(f'retry_{index}_same_successful_operation', replay.get('operation_id') == original['operation_id'] and replay.get('status') == 'succeeded', replay)
check('same_document_after_retries', query() == first_rows, query())
trace = traces()
check('handler_and_commit_exactly_once', len(trace) == 2 and [v['stage'] for v in trace] == ['invoked', 'committed'] and trace[1]['reference'] == first_rows[0]['reference'], trace)
conflict = call('test_action', {**write_args, 'timeout_ms': 1})
check('changed_request_refused', conflict.get('error', {}).get('code') == 'request_conflict', conflict)
check('conflict_did_not_write', query() == first_rows and traces() == trace)
# Positive control: a NEW request really executes the same button again.
control_marker = marker + '-control'
filled = complete('test_input', args(action='text', session_id=sid, window=window,
                  element={'selector': {'name': 'Текст'}}, params={'text': control_marker}))
check('positive_control_marker_entered', filled.get('status') == 'succeeded', filled)
control = complete('test_action', {**write_args, 'request_id': str(uuid.uuid4())})
check('positive_control_executes', control.get('status') == 'succeeded' and control.get('operation_id') != original['operation_id'], control)
rows = query(control_marker)
check('positive_control_creates_separate_document', len(rows) == 1 and rows[0]['reference'] != first_rows[0]['reference'] and query() == first_rows, rows)
check('positive_control_second_invocation', len(traces(control_marker)) == 2 and traces() == trace, traces(control_marker))
print(json.dumps({'route': route, 'passed': len(checks), 'original_operation_id': original['operation_id']}))
