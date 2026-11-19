import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

from onec_mcp_toolkit_proxy.command_queue import ChannelCommandQueue
from onec_mcp_toolkit_proxy.operation_journal import OperationJournal, OperationError
from onec_mcp_toolkit_proxy.file_transport import FileTransport, write_json
from onec_mcp_toolkit_proxy.result_models import CommandResult
from onec_mcp_toolkit_proxy import operation_api
from onec_mcp_toolkit_proxy.consumer_registry import consumer_registry, current_consumer, ConsumerChanged


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.store = OperationJournal(self.temp.name, result_ttl=10, clock=lambda: self.now)
        self.addCleanup(lambda: self.store.close())

    def test_conflict_canonical_types_and_channel_isolation(self):
        op, fresh = self.store.reserve('a', 'key', 'execute_code', {'a': 1, 'b': '1'})
        self.assertTrue(fresh)
        self.assertEqual(self.store.reserve('a', 'key', 'execute_code', {'b': '1', 'a': 1}), (op, False))
        with self.assertRaisesRegex(OperationError, 'request_conflict'):
            self.store.reserve('a', 'key', 'execute_code', {'a': '1', 'b': '1'})
        with self.assertRaisesRegex(OperationError, 'operation_not_found'):
            self.store.get('b', op)
        self.assertNotEqual(self.store.reserve('b', 'key', 'execute_code', {'a': 1})[0], op)

    def test_restart_never_replays_and_preserves_confirmed(self):
        pending, _ = self.store.reserve('a', 'pending', 'execute_code', {'code': 'SECRET_CODE'})
        done, _ = self.store.reserve('a', 'done', 'execute_code', {})
        self.store.transition(done, 'running')
        self.store.finish(done, {'success': True, 'data': 42})
        self.store.close()
        self.store = OperationJournal(self.temp.name, clock=lambda: self.now)
        self.assertEqual(self.store.get('a', pending)['state'], 'unknown')
        self.assertEqual(self.store.snapshot('a', done)['result']['data'], 42)
        self.assertEqual(self.store.reserve('a', 'pending', 'execute_code', {'code': 'SECRET_CODE'}), (pending, False))
        self.assertNotIn(b'SECRET_CODE', (Path(self.temp.name) / 'operations.sqlite3').read_bytes())

    def test_expired_result_keeps_key_and_active_unknown_are_not_expired(self):
        op, _ = self.store.reserve('a', 'done', 'execute_code', {})
        self.store.transition(op, 'running')
        self.store.finish(op, {'success': True})
        running, _ = self.store.reserve('a', 'running', 'execute_code', {})
        self.store.transition(running, 'running')
        unknown, _ = self.store.reserve('a', 'unknown', 'execute_code', {})
        self.store.transition(unknown, 'unknown')
        self.now += 100
        self.assertEqual(self.store.snapshot('a', op)['status'], 'result_expired')
        self.assertIsNone(self.store.snapshot('a', op)['result'])
        self.assertEqual(self.store.reserve('a', 'done', 'execute_code', {}), (op, False))
        self.assertEqual(self.store.get('a', running)['state'], 'running')
        self.assertEqual(self.store.get('a', unknown)['state'], 'unknown')

    def test_quota_never_evicts_unknown_or_keys(self):
        self.store.max_records = 1
        op, _ = self.store.reserve('a', 'key', 'execute_code', {})
        self.store.transition(op, 'unknown')
        with self.assertRaisesRegex(OperationError, 'operation_quota_exceeded'):
            self.store.reserve('a', 'new', 'execute_code', {})
        self.assertEqual(self.store.reserve('a', 'key', 'execute_code', {}), (op, False))

    def test_result_quota_is_unknown_not_false_success(self):
        self.store.max_result_bytes = 10
        op, _ = self.store.reserve('a', 'key', 'execute_code', {})
        self.store.transition(op, 'running')
        self.store.finish(op, {'success': True, 'data': 'a' * 100})
        result = self.store.snapshot('a', op)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['error'], 'result_storage_quota')
        self.assertIsNone(result['result'])

    def test_second_owner_and_unwritable_location_fail_closed(self):
        with self.assertRaisesRegex(OperationError, 'operation_store_unavailable'):
            OperationJournal(self.temp.name)
        path = Path(self.temp.name) / 'not-directory'
        path.write_text('x')
        with self.assertRaisesRegex(OperationError, 'operation_store_unavailable'):
            OperationJournal(path)


    def test_approval_recovery_rejection_ttl_and_old_schema_migration(self):
        pending, _ = self.store.reserve('a', 'pending', 'execute_code', {})
        self.store.transition(pending, 'running')
        self.assertTrue(self.store.observe(pending, 'awaiting_approval', 1))
        rejected, _ = self.store.reserve('a', 'rejected', 'execute_code', {})
        self.store.transition(rejected, 'running')
        self.store.finish(rejected, {'success': False, 'lifecycle_outcome': 'rejected', 'rejection_reason': 'mode_deny'})
        self.store.db.execute('ALTER TABLE operations DROP COLUMN event_seq')
        self.store.close()
        self.store = OperationJournal(self.temp.name, result_ttl=10, clock=lambda: self.now)
        self.assertEqual(self.store.get('a', pending)['state'], 'unknown')
        self.assertFalse(self.store.observe(pending, 'running', 2))
        self.assertEqual(self.store.get('a', rejected)['state'], 'rejected')
        self.now += 11
        self.assertEqual(self.store.get('a', rejected)['state'], 'result_expired')
        self.assertEqual(self.store.reserve('a', 'rejected', 'execute_code', {}), (rejected, False))


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.q = ChannelCommandQueue()
        self.q._journal = OperationJournal(Path(self.temp.name) / 'journal')
        self.addCleanup(self.q._journal.close)

    async def test_wait_timeout_cancel_late_result_and_repeat_once(self):
        op = await self.q.add_operation('a', 'key', 'execute_code', {'code': 'test'})
        with self.assertRaises(asyncio.TimeoutError):
            await self.q.wait_for_result(op, .001)
        waiter = asyncio.create_task(self.q.wait_for_result(op, 100))
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        again = await self.q.add_operation('a', 'key', 'execute_code', {'code': 'test'})
        self.assertEqual(op, again)
        cmd = await self.q.get_next_command('a', 0)
        self.assertEqual(cmd.id, op)
        self.assertIsNone(await self.q.get_next_command('a', 0))
        self.assertTrue(self.q.command_states('a', [op])[0]['active'])
        self.assertTrue(await self.q.set_result(op, {'success': True, 'data': 123}))
        self.assertEqual((await self.q.wait_for_result(op, .01))['result']['data'], 123)
        await self.q.cleanup_expired(0)
        self.assertEqual(self.q.operation_store().snapshot('a', op)['result']['data'], 123)
        self.assertEqual(await self.q.add_operation('a', 'key', 'execute_code', {'code': 'test'}), op)
        self.assertIsNone(await self.q.get_next_command('a', 0))

    async def test_storage_failure_before_dispatch_and_admission(self):
        with patch.object(self.q._journal, 'reserve', side_effect=OperationError('operation_store_unavailable')):
            with self.assertRaises(OperationError):
                await self.q.add_operation('a', 'key', 'execute_code', {})
        self.assertIsNone(await self.q.get_next_command('a', 0))
        op = await self.q.add_operation('a', 'key', 'execute_code', {})
        with patch.object(self.q._journal, 'transition', side_effect=OperationError('operation_store_unavailable')):
            with self.assertRaises(OperationError):
                await self.q.get_next_command('a', 0)
        self.assertEqual(self.q.operation_store().get('a', op)['state'], 'queued')
        self.assertIsNone(await self.q.get_next_command('a', 0))  # no uncommitted dispatch

    async def test_file_transport_late_response_is_durable(self):
        bridge = FileTransport(Path(self.temp.name) / 'files', 'a', self.q, 30, CommandResult)
        op = await self.q.add_operation('a', 'key', 'execute_code', {})
        await bridge.step()
        with self.assertRaises(asyncio.TimeoutError):
            await self.q.wait_for_result(op, .001)
        write_json(bridge.directory / (op + '.response.json'), {'id': op, 'success': True, 'data': 'late'})
        await bridge.step()
        self.assertEqual(self.q.operation_store().snapshot('a', op)['result']['data'], 'late')
        self.assertFalse(list(bridge.directory.glob('*.request.json')))

    async def test_api_status_does_not_wait_for_consumer_or_execute(self):
        with patch.object(operation_api, 'channel_command_queue', self.q), patch.object(consumer_registry, 'consumers', {}):
            op = await self.q.add_operation('a', 'key', 'execute_code', {})
            result = await operation_api.operation_status('a', op)
            self.assertEqual(result['status'], 'queued')
            self.assertEqual((await operation_api.operation_status('b', op))['error'], 'operation_not_found')
            self.assertEqual((await operation_api.execute_operation('a', 'new', 'Результат = 1;'))['error'], 'consumer_unavailable')

    async def test_native_api_conflict_and_late_success(self):
        with patch.object(operation_api, 'channel_command_queue', self.q), patch.object(consumer_registry, 'consumers', {}):
            consumer_registry.bind('a', 'legacy')
            first = await operation_api.execute_operation('a', 'key', 'Результат = 1;', wait_timeout_ms=1)
            self.assertEqual(first['status'], 'queued')
            again = await operation_api.execute_operation('a', 'key', 'Результат = 1;')
            self.assertEqual(first['operation_id'], again['operation_id'])
            conflict = await operation_api.execute_operation('a', 'key', 'Результат = 2;')
            self.assertEqual(conflict['error'], 'request_conflict')
            cmd = await self.q.get_next_command('a', 0)
            await self.q.set_result(cmd.id, {'success': True, 'data': 1})
            self.assertEqual((await operation_api.operation_status('a', cmd.id))['result']['data'], 1)

    async def test_durable_command_blocks_owner_takeover_after_old_deadline(self):
        from onec_mcp_toolkit_proxy import command_queue
        with patch.object(command_queue, 'channel_command_queue', self.q), patch.object(consumer_registry, 'consumers', {}):
            owner = consumer_registry.bind('a', 'legacy')
            token = current_consumer.set(owner)
            try:
                op = await self.q.add_operation('a', 'key', 'execute_code', {})
            finally:
                current_consumer.reset(token)
            owner.seen = 0
            self.q.get_command(op).deadline = 0
            with self.assertRaises(ConsumerChanged):
                consumer_registry.bind('a', 'server_host', identity=('other',))
            consumer_registry.retire(owner)
            self.assertEqual(self.q.operation_store().snapshot('a', op)['status'], 'unknown')
            self.assertFalse(await self.q.set_result(op, {'success': True}))

    async def test_result_policy_never_queries_or_returns_raw_without_dictionary(self):
        op = await self.q.add_operation('a', 'key', 'execute_code', {})
        await self.q.get_next_command('a', 0)
        await self.q.set_result(op, {'success': True, 'data': 'private'})
        anon = MagicMock()
        anon._dict_matcher = None
        with patch.object(operation_api, 'channel_command_queue', self.q), \
             patch.object(operation_api.settings, 'anonymization_enabled', True), \
             patch.object(operation_api.settings, 'anonymization_tools', ['execute_code']), \
             patch.object(operation_api.settings, 'anonymization_dictionary_enabled', True), \
             patch.object(operation_api.AnonymizerRegistry, 'get_async', AsyncMock(return_value=anon)), \
             patch.object(operation_api.AnonymizerRegistry, 'ensure_dictionary_loaded', AsyncMock()) as preload:
            result = await operation_api.operation_status('a', op)
            self.assertEqual(result['error'], 'operation_result_policy_not_ready')
            preload.assert_not_called()
            anon.anonymize_response.assert_not_called()
            anon._dict_matcher = object()
            anon.anonymize_response.return_value = {'success': True, 'data': 'TOKEN'}
            result = await operation_api.operation_status('a', op)
            self.assertEqual(result['result']['data'], 'TOKEN')
            self.assertEqual(self.q.operation_store().snapshot('a', op)['result']['data'], 'private')

    async def test_server_host_permissions_are_not_bypassed(self):
        anon = MagicMock()
        anon.detokenize_params_for_tool.side_effect = lambda params, tool: params
        with patch.object(operation_api, 'channel_command_queue', self.q), \
             patch.object(consumer_registry, 'consumers', {}), \
             patch.object(operation_api.AnonymizerRegistry, 'get_async', AsyncMock(return_value=anon)):
            owner = consumer_registry.bind('a', 'server_host', tools=frozenset())
            self.assertEqual((await operation_api.execute_operation('a', 'key', 'Результат = 1;'))['error'], 'tool_unavailable')
            owner.tools = frozenset({'execute_code'})
            owner.anon_confirm = True
            self.assertEqual((await operation_api.execute_operation('a', 'key', 'Результат = 1;'))['error'], 'anonymization_confirmation_required')
            self.assertIsNone(await self.q.get_next_command('a', 0))

    async def test_approval_events_order_channel_and_rejected_result(self):
        op = await self.q.add_operation('a', 'key', 'execute_code', {})
        self.assertFalse(await self.q.observe_operation('a', op, 'awaiting_approval', 1))
        cmd = await self.q.get_next_command('a', 0)
        self.assertEqual(cmd.to_dict()['lifecycle_version'], 1)
        self.assertFalse(await self.q.observe_operation('b', op, 'awaiting_approval', 1))
        self.assertTrue(await self.q.observe_operation('a', op, 'awaiting_approval', 1))
        self.assertTrue(await self.q.observe_operation('a', op, 'awaiting_approval', 1))
        self.assertFalse(cmd.result_event.is_set())
        with self.assertRaises(asyncio.TimeoutError):
            await self.q.wait_for_result(op, .001)
        self.assertEqual(self.q.operation_store().get('a', op)['state'], 'awaiting_approval')
        self.assertTrue(await self.q.observe_operation('a', op, 'running', 2))
        self.assertFalse(await self.q.observe_operation('a', op, 'awaiting_approval', 1))
        self.assertTrue(await self.q.set_result(op, {'success': False, 'error': 'arbitrary text',
            'lifecycle_outcome': 'rejected', 'rejection_reason': 'approval_stale'}))
        self.assertEqual(self.q.operation_store().get('a', op)['state'], 'rejected')
        self.assertFalse(await self.q.observe_operation('a', op, 'running', 2))
        self.assertEqual(await self.q.add_operation('a', 'key', 'execute_code', {}), op)

    async def test_error_text_is_not_rejection_and_legacy_has_no_protocol_flag(self):
        legacy = await self.q.add_command('a', 'execute_code', {})
        self.assertNotIn('lifecycle_version', self.q.get_command(legacy).to_dict())
        self.assertFalse(await self.q.observe_operation('a', legacy, 'awaiting_approval', 1))
        op = await self.q.add_operation('a', 'key', 'execute_code', {})
        await self.q.get_next_command('a', 0)
        await self.q.get_next_command('a', 0)
        await self.q.set_result(op, {'success': False, 'error': 'Operation rejected by user'})
        self.assertEqual(self.q.operation_store().get('a', op)['state'], 'failed')

    async def test_file_approval_event_does_not_finish_command(self):
        bridge = FileTransport(Path(self.temp.name) / 'approval-files', 'a', self.q, 30, CommandResult)
        op = await self.q.add_operation('a', 'key', 'execute_code', {})
        await bridge.step()
        event = bridge.directory / (op + '.lifecycle.json')
        write_json(event, {'id': op, 'success': False, 'lifecycle_event': 'awaiting_approval', 'lifecycle_seq': 1})
        await bridge.step()
        self.assertEqual(bridge.active, op)
        self.assertEqual(self.q.operation_store().get('a', op)['state'], 'awaiting_approval')
        write_json(bridge.directory / (op + '.response.json'), {'id': op, 'success': False,
            'lifecycle_outcome': 'rejected', 'rejection_reason': 'user_declined'})
        await bridge.step()
        self.assertEqual(self.q.operation_store().get('a', op)['state'], 'rejected')
        self.assertFalse(event.exists())
        self.assertIsNone(bridge.active)

    async def test_http_events_validated_and_readable_without_finishing_wait(self):
        import httpx
        from onec_mcp_toolkit_proxy import server
        op = await self.q.add_operation('a', 'key', 'execute_code', {})
        await self.q.get_next_command('a', 0)
        with patch.object(server, 'channel_command_queue', self.q):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test') as client:
                event = {'id': op, 'success': False, 'lifecycle_event': 'awaiting_approval', 'lifecycle_seq': 1}
                self.assertEqual((await client.post('/1c/result?channel=b', json=event)).status_code, 404)
                self.assertEqual((await client.post('/1c/result?channel=a', json=event)).status_code, 200)
                self.assertEqual(self.q.operation_store().get('a', op)['state'], 'awaiting_approval')
                self.assertFalse(self.q.get_command(op).result_event.is_set())
                event['lifecycle_seq'] = 2
                self.assertEqual((await client.post('/1c/result?channel=a', json=event)).status_code, 422)
                result = {'id': op, 'success': False, 'lifecycle_outcome': 'rejected', 'rejection_reason': 'mode_deny'}
                self.assertEqual((await client.post('/1c/result?channel=a', json=result)).status_code, 200)
                self.assertEqual(self.q.operation_store().get('a', op)['state'], 'rejected')


if __name__ == '__main__':
    unittest.main()
