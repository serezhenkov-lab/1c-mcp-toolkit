"""Test-client adapter to the common durable owner; no UI state or second journal."""
import copy
import json

from .anonymizer import AnonymizerRegistry
from .command_queue import channel_command_queue
from .config import settings
from .consumer_registry import consumer_registry, current_consumer, ConsumerChanged
from .operation_api import operation_status
from .operation_journal import OperationError
from .test_client_contract import TEST_TOOLS, valid_request


def envelope(arguments, *, operation_id=None, status='failed', code=None, stage='lifecycle'):
    def identifier(key):
        value = arguments.get(key)
        return value if isinstance(value, str) and 1 <= len(value) <= 128 else None
    return dict(contract_version='1', request_id=identifier('request_id'),
                operation_id=operation_id, session_id=identifier('session_id'),
                status=status, execution='not_started', verification='not_requested',
                observed_at=None, observed_state=None,
                data={'observation_unavailable_reason': code or 'operation_not_observed'}, messages=[],
                error={'code': code, 'message': code, 'stage': stage, 'details': {}} if code else None)


def normalize(tool, arguments):
    def numbers(value):
        if isinstance(value, dict):
            return {key: numbers(child) for key, child in value.items()}
        if isinstance(value, list):
            return [numbers(child) for child in value]
        if type(value) is float and value.is_integer():
            return int(value)
        return value
    value = numbers(arguments)
    action = value.get('action')
    default = 120000 if tool == 'test_session' and action in ('start', 'attach') else 30000
    if tool == 'test_session' and action == 'status':
        default = 0
    value.setdefault('timeout_ms', default)
    params = value['params']
    if tool == 'test_inspect' and action in ('tree', 'command_interface', 'command_bars'):
        params.setdefault('depth', 8)
        params.setdefault('max_nodes', 1000)
    if tool == 'test_table' and action in ('read', 'find'):
        params.setdefault('allow_navigation', False)
    if tool == 'test_table' and action == 'read':
        params.setdefault('limit', 100)
    if tool == 'test_table' and action == 'add':
        params.setdefault('values', [])
    return value


async def saved_operation(channel, identifier):
    store = channel_command_queue.operation_store()
    row = store.get(channel, identifier)
    if row['tool'] not in TEST_TOOLS:
        raise OperationError('permission_denied')
    snapshot = await operation_status(channel, identifier)
    if not snapshot.get('success'):
        raise OperationError(snapshot.get('error', 'internal_error'))
    context = json.loads(row['context']) if row.get('context') else {}
    arguments = {'request_id': row['request_key'], **context}
    raw = snapshot.get('result')
    if isinstance(raw, dict) and isinstance(raw.get('data'), dict) and raw['data'].get('contract_version') == '1':
        result = copy.deepcopy(raw['data'])
        if result.get('session_id') == '':
            result['session_id'] = None
        if result.get('observed_at') is None and result.get('data') is None:
            result['data'] = {'observation_unavailable_reason': 'executor_returned_no_observation'}
        # A cached status snapshot must not bypass the current policy of its target tool.
        async def protect_nested(value, depth=0):
            nested = (value.get('data') or {}).get('operation')
            if not isinstance(nested, dict) or nested.get('contract_version') != '1':
                return
            if depth >= 8:
                raise OperationError('operation_result_unavailable')
            target = store.get(channel, nested['operation_id'])
            if target['tool'] not in TEST_TOOLS:
                raise OperationError('permission_denied')
            if settings.anonymization_enabled and target['tool'] in settings.anonymization_tools:
                anon = await AnonymizerRegistry.get_async(channel)
                if settings.anonymization_dictionary_enabled and anon._dict_matcher is None:
                    raise OperationError('operation_result_policy_not_ready')
                nested = anon.anonymize_response(copy.deepcopy(nested), target['tool'])
                value['data']['operation'] = nested
            await protect_nested(nested, depth + 1)
        await protect_nested(result)
        # Identity belongs to the owner, never to an arbitrary executor payload.
        result.update(request_id=row['request_key'], operation_id=identifier)
        return result
    state = row['state']
    code = row['error_code']
    if state == 'rejected':
        state, code = 'failed', 'permission_denied'
    elif state == 'result_expired':
        state, code = 'failed', 'result_expired'
    elif state == 'failed':
        code = code or 'internal_error'
    elif state == 'unknown':
        code = 'connection_lost'
    result = envelope(arguments, operation_id=identifier, status=state, code=code)
    if snapshot.get('progress') is not None:
        result['data']['progress'] = snapshot['progress']
        if snapshot['progress']['completed_count'] > 0:
            result['execution'] = 'invoked'
    if state == 'unknown':
        result.update(execution='unknown', verification='not_confirmed')
    return result


async def execute_test_operation(channel, tool, arguments):
    if not valid_request(tool, arguments):
        return envelope(arguments if isinstance(arguments, dict) else {}, code='invalid_params', stage='validation')
    args = normalize(tool, arguments)
    token = None
    try:
        store = channel_command_queue.operation_store()
        # A journal read never waits on the executor, permission dialog or dictionary query.
        if tool == 'test_session' and args['action'] == 'status' and 'operation_id' in args['params']:
            existing, _ = store.find(channel, args['request_id'], tool, args)
            if existing:
                return await saved_operation(channel, existing['id'])
            target = await saved_operation(channel, args['params']['operation_id'])
            # A pure journal read correlates to its target; it does not reserve a key.
            result = envelope(args, operation_id=args['params']['operation_id'], status='succeeded')
            result['data'] = {'operation': target, 'observation_unavailable_reason': 'journal_read_only'}
            return result
        owner = consumer_registry.consumers.get(channel)
        if owner and owner.retired:
            owner = None
        token = current_consumer.set(owner)
        do_anon = settings.anonymization_enabled and tool in settings.anonymization_tools
        if do_anon:
            anon = await AnonymizerRegistry.get_async(channel)
            args = anon.detokenize_params_for_tool(args, tool)
        existing, _ = store.find(channel, args['request_id'], tool, args)
        if existing:
            return await saved_operation(channel, existing['id'])
        if owner is None or owner.mode == 'server_host':
            return envelope(args, code='client_context_unavailable', stage='availability')
        if do_anon:
            await AnonymizerRegistry.ensure_dictionary_loaded(channel)
            if settings.anonymization_dictionary_enabled and anon._dict_matcher is None:
                return envelope(args, code='operation_result_policy_not_ready')
        identifier = await channel_command_queue.add_operation(channel, args['request_id'], tool, args,
                                                               context={'session_id': args.get('session_id')})
        return await saved_operation(channel, identifier)
    except OperationError as exc:
        code = 'permission_denied' if exc.code == 'operation_not_found' else exc.code
        return envelope(args, code=code)
    except ConsumerChanged:
        return envelope(args, code='connection_lost')
    finally:
        if token is not None:
            current_consumer.reset(token)
