"""Native operation API; permission decisions remain in the 1C executor."""
import asyncio
import copy

from .anonymizer import AnonymizerRegistry
from .command_queue import channel_command_queue
from .config import settings
from .consumer_registry import consumer_registry, current_consumer, ConsumerChanged
from .operation_journal import OperationError
from .tools import validate_execute_code_params


def failure(code):
    return {'success': False, 'error': code}


async def operation_status(channel, operation_id):
    """Read without waiting for a consumer and without enqueueing database code."""
    try:
        store = channel_command_queue.operation_store()
        row = store.get(channel, operation_id)
        result = store.snapshot(channel, operation_id)
        # Raw stored data never bypasses the configured outbound policy.
        owner = consumer_registry.consumers.get(channel)
        if result['result'] is not None and owner and not owner.retired and owner.mode == 'server_host' and owner.anon_confirm:
            return failure('anonymization_confirmation_required')
        if result['result'] is not None and settings.anonymization_enabled:
            if row['tool'] in settings.anonymization_tools:
                anon = await AnonymizerRegistry.get_async(channel)
                # Status must never start dictionary queries behind a busy 1C command.
                if settings.anonymization_dictionary_enabled and anon._dict_matcher is None:
                    return failure('operation_result_policy_not_ready')
                result['result'] = anon.anonymize_response(copy.deepcopy(result['result']), row['tool'])
        result['success'] = True  # status read succeeded, not necessarily execution
        return result
    except OperationError as exc:
        return failure(exc.code)
    except Exception:
        return failure('operation_result_unavailable')


async def execute_operation(channel, request_id, code, execution_context='server', wait_timeout_ms=0):
    """Opt-in durable execute_code, sharing the normal 1C delivery queue."""
    try:
        if type(wait_timeout_ms) is not int or not 0 <= wait_timeout_ms <= 30000:
            return failure('invalid_wait_timeout')
        validated = validate_execute_code_params(code=code, execution_context=execution_context)
        params = {'code': validated.code, 'execution_context': validated.execution_context}
        owner = consumer_registry.consumers.get(channel)
        if owner is not None and owner.retired:
            owner = None
        token = current_consumer.set(owner)
        try:
            do_anon = settings.anonymization_enabled and 'execute_code' in settings.anonymization_tools
            if do_anon or (owner and owner.mode == 'server_host'):
                if owner is None:
                    return failure('consumer_unavailable_for_detokenization')
                anon = await AnonymizerRegistry.get_async(channel)
                if owner.mode == 'server_host':
                    anon.mapper.validate_tokens(params)
                params = anon.detokenize_params_for_tool(params, 'execute_code')
                anon.prune()
            store = channel_command_queue.operation_store()
            existing, _ = store.find(channel, request_id, 'execute_code', params)
            if existing:
                # Repeated request does not wait for or rebind an executor.
                return await operation_status(channel, existing['id'])
            if owner is None:
                return failure('consumer_unavailable')
            if owner.mode == 'server_host' and execution_context == 'client':
                return failure('client_context_unavailable')
            if owner.mode == 'server_host':
                if 'execute_code' not in owner.tools:
                    return failure('tool_unavailable')
                if owner.anon_confirm:
                    return failure('anonymization_confirmation_required')
            if do_anon:
                await AnonymizerRegistry.ensure_dictionary_loaded(channel)
                if settings.anonymization_dictionary_enabled and anon._dict_matcher is None:
                    return failure('operation_result_policy_not_ready')
            identifier = await channel_command_queue.add_operation(channel, request_id, 'execute_code', params)
            if wait_timeout_ms:
                try:
                    await channel_command_queue.wait_for_result(identifier, wait_timeout_ms / 1000)
                except (asyncio.TimeoutError, KeyError):
                    pass  # caller's wait expired; operation remains accepted
            return await operation_status(channel, identifier)
        finally:
            current_consumer.reset(token)
    except OperationError as exc:
        return failure(exc.code)
    except ConsumerChanged:
        return failure('consumer_changed')
    except (ValueError, TypeError):
        return failure('invalid_params')
    except Exception:
        return failure('operation_store_unavailable')
