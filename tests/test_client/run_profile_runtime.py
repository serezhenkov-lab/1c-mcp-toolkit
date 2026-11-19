"""Exercise production profile commands and public HTTP; no injected EPF startup code.

execute_code drives the ordinary form command, not Настроить/ПолучитьМенеджер.
UI entry/click acceptance is recorded separately from these integration checks.
"""
import json
import sys
import time
import uuid
from pathlib import Path
import httpx

RUN = Path(__file__).resolve().parents[2] / '.local/profile-runtime'
client = httpx.Client(base_url='http://127.0.0.1:17668', timeout=90)
stage = sys.argv[1]
events = []
checks = []

def save():
    (RUN / (stage + '.json')).write_text(json.dumps({'checks': checks, 'events': events}, ensure_ascii=False, indent=2), encoding='utf-8')

def call(tool, args):
    r = client.post('/api/' + tool, params={'channel': 'queue1'}, json=args)
    data = r.json()
    events.append({'tool': tool, 'args': args, 'http': r.status_code, 'result': data})
    save()
    return data

def check(name, condition, value=None):
    checks.append({'name': name, 'ok': bool(condition), 'value': value})
    save()
    assert condition, (name, value)

def code(text, context='client'):
    r = call('execute_code', {'code': text, 'execution_context': context})
    assert r.get('success'), r
    return r.get('data')

def operation(tool='test_session', **args):
    args['request_id'] = str(uuid.uuid4())
    r = call(tool, args)
    for _ in range(240):
        if r.get('status') not in ('queued', 'running', 'awaiting_approval'):
            return r
        time.sleep(.25)
        r = call('test_session', {'request_id': str(uuid.uuid4()), 'action': 'status', 'params': {'operation_id': r['operation_id']}}).get('data', {}).get('operation', {})
    raise AssertionError(r)

def ready_status():
    for _ in range(40):
        r = operation(action='status', params={})
        if r.get('error', {}).get('code') != 'operation_store_unavailable':
            return r
        time.sleep(.25)
    return r

if stage == 'configure':
    code('ФорматОтветаВстроенный = 0; ИспользоватьТочнуюАнонимизацию = Ложь; Результат = Истина;')
    r = code('ТестПрофильID = "queue1"; ТестПрофильПользователь = "ApiProbe"; ТестПрофильПорт = 16548; ТестПрофильВключен = Истина; СохранитьПрофильТестирования(Неопределено); Результат = ТестПрофильСтатус;')
    check('production_form_save', r.startswith('Профиль сохранён'), r)
    stored = code('Результат = ХранилищеОбщихНастроек.Загрузить("MCPToolkit", "TestClientProfileV1");', 'server')
    check('stored_whitelist', set(stored) == {'version', 'id', 'user', 'port', 'enabled', 'password_required'}, stored)
    state = ready_status()
    check('configured_without_launch', state.get('data', {}).get('state') == 'absent', state)
    r = code('ТестПрофильID = "invalid/id"; СохранитьПрофильТестирования(Неопределено); Результат = ТестПрофильСтатус;')
    check('invalid_profile_refused', r.startswith('Не удалось'), r)
    same = code('Результат = ХранилищеОбщихНастроек.Загрузить("MCPToolkit", "TestClientProfileV1");', 'server')
    check('invalid_save_preserves_record', same == stored, same)
    code('ТестПрофильID = "queue1"; РежимПодтвержденияОпасныхОпераций = "session_allow"; Результат = Истина;')
    started = operation(action='start', params={'profile_id': 'queue1'})
    check('public_start', started.get('status') == 'succeeded', started)
    (RUN / 'session.json').write_text(json.dumps(started), encoding='utf-8')
    r = code('ТестПрофильПорт = 16549; СохранитьПрофильТестирования(Неопределено); Результат = ТестПрофильСтатус;')
    check('live_profile_change_refused', r.startswith('Профиль занят'), r)
    same = code('Результат = ХранилищеОбщихНастроек.Загрузить("MCPToolkit", "TestClientProfileV1");', 'server')
    check('busy_save_preserves_record', same == stored, same)
    code('ТестПрофильПорт = 16548; Результат = Истина;')
elif stage == 'restart':
    r = call('restart_1c_session', {})
    check('restart_accepted', r.get('success'), r)
elif stage == 'restored':
    # Anonymization is deferred; only test response format/policy, never profile setup.
    code('ФорматОтветаВстроенный = 0; ИспользоватьТочнуюАнонимизацию = Ложь; Результат = Истина;')
    state = ready_status()
    check('restored_without_setup', state.get('data', {}).get('state') == 'disconnected' and state['data'].get('manager_mode'), state)
    denied = operation(action='start', params={'profile_id': 'queue1'})
    check('permission_not_restored', denied.get('error', {}).get('code') == 'permission_denied', denied)
    # Explicit test permission, after observing normal startup denial.
    code('РежимПодтвержденияОпасныхОпераций = "session_allow"; ФорматОтветаВстроенный = 0; Результат = Истина;')
    second = operation(action='start', params={'profile_id': 'queue1'})
    check('no_second_client', second.get('error', {}).get('code') == 'client_already_exists', second)
    attached = operation(action='attach', params={'profile_id': 'queue1'})
    check('explicit_attach_unowned', attached.get('status') == 'succeeded' and attached['data'].get('owned') is False, attached)
    old = json.loads((RUN / 'session.json').read_text(encoding='utf-8'))
    check('fresh_session_id', attached['session_id'] != old['session_id'])
    r = operation(tool='test_inspect', action='windows', session_id=attached['session_id'], params={})
    check('public_inspect', r.get('status') == 'succeeded', r)
    r = operation(action='stop', session_id=attached['session_id'], params={})
    check('unowned_stop_denied', r.get('error', {}).get('code') == 'client_not_owned', r)
elif stage == 'password-setup':
    r = code('ТестПрофильПароль = "profile-test-not-a-real-password"; ТестПрофильТребуетПароль = Истина; СохранитьПрофильТестирования(Неопределено); Результат = Новый Структура("status,password_cleared", ТестПрофильСтатус, ПустаяСтрока(ТестПрофильПароль));')
    check('password_kept_only_in_driver_memory', r['status'].startswith('Профиль сохранён') and r['password_cleared'], r)
    stored = code('Результат = ХранилищеОбщихНастроек.Загрузить("MCPToolkit", "TestClientProfileV1");', 'server')
    check('secret_not_in_storage', stored.get('password_required') is True and set(stored) == {'version', 'id', 'user', 'port', 'enabled', 'password_required'}, stored)
    r = call('restart_1c_session', {})
    check('restart_accepted', r.get('success'), r)
elif stage == 'password-restored':
    r = code('ФорматОтветаВстроенный = 0; ИспользоватьТочнуюАнонимизацию = Ложь; Результат = Новый Структура("required,empty,id", ТестПрофильТребуетПароль, ПустаяСтрока(ТестПрофильПароль), ИдентификаторПрофиляТестирования);')
    check('password_not_restored', r == {'required': True, 'empty': True, 'id': 'queue1'}, r)
    code('РежимПодтвержденияОпасныхОпераций = "session_allow"; Результат = Истина;')
    ready_status()
    r = operation(action='start', params={'profile_id': 'queue1'})
    check('missing_password_blocks_launch', r.get('error', {}).get('code') == 'profile_credentials_required', r)
    r = code('ТестПрофильТребуетПароль = Ложь; СохранитьПрофильТестирования(Неопределено); Результат = ТестПрофильСтатус;')
    check('password_requirement_can_be_cleared', r.startswith('Профиль сохранён'), r)
    r = operation(action='start', params={'profile_id': 'queue1'})
    check('new_explicit_start', r.get('status') == 'succeeded', r)
    r = operation(action='stop', session_id=r['session_id'], params={})
    check('owned_stop', r.get('status') == 'succeeded', r)
    r = code('ТестПрофильВключен = Ложь; СохранитьПрофильТестирования(Неопределено); Результат = ТестПрофильСтатус;')
    check('profile_disabled', r == 'Профиль отключён', r)
    r = operation(action='start', params={'profile_id': 'queue1'})
    check('disabled_profile_blocks_start', r.get('error', {}).get('code') == 'session_not_ready', r)
    r = call('restart_1c_session', {})
    check('disabled_restart_accepted', r.get('success'), r)
elif stage == 'disabled-restored':
    r = code('ФорматОтветаВстроенный = 0; ИспользоватьТочнуюАнонимизацию = Ложь; Результат = Новый Структура("enabled,driver_absent,id,status", ТестПрофильВключен, ФормаМенеджераТестирования = Неопределено, ТестПрофильID, ТестПрофильСтатус);')
    check('disabled_profile_restored_without_driver', r == {'enabled': False, 'driver_absent': True, 'id': 'queue1', 'status': 'Профиль отключён'}, r)
else:
    raise ValueError(stage)
print(json.dumps({'stage': stage, 'passed': len(checks)}, ensure_ascii=False))
