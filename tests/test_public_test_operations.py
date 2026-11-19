import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from onec_mcp_toolkit_proxy import operation_api, test_client_operations as api
from onec_mcp_toolkit_proxy.command_queue import ChannelCommandQueue
from onec_mcp_toolkit_proxy.consumer_registry import Consumer, consumer_registry
from onec_mcp_toolkit_proxy.operation_journal import OperationJournal


class PublicOperations(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.q = ChannelCommandQueue()
        self.q._journal = OperationJournal(Path(self.temp.name) / 'journal')
        self.addCleanup(self.q._journal.close)
        for module in (api, operation_api):
            p = patch.object(module, 'channel_command_queue', self.q)
            p.start(); self.addCleanup(p.stop)
        for p in (patch.object(consumer_registry, 'consumers', {'a': Consumer('a', 'client')}),
                  patch.object(api.settings, 'anonymization_enabled', False)):
            p.start(); self.addCleanup(p.stop)
        self.args = dict(request_id='start', action='start', params={'profile_id': 'test'})

    async def test_defaults_repeat_conflict_and_one_dispatch(self):
        one = await api.execute_test_operation('a', 'test_session', self.args)
        two = await api.execute_test_operation('a', 'test_session', {**self.args, 'timeout_ms': 120000})
        self.assertEqual(one['operation_id'], two['operation_id'])
        numeric = await api.execute_test_operation('a', 'test_session', {**self.args, 'timeout_ms': 120000.0})
        self.assertEqual(one['operation_id'], numeric['operation_id'])
        conflict = await api.execute_test_operation('a', 'test_session', {**self.args, 'timeout_ms': 0})
        self.assertEqual(conflict['error']['code'], 'request_conflict')
        self.assertIsNotNone(await self.q.get_next_command('a', 0))
        self.assertIsNone(await self.q.get_next_command('a', 0))
        table = dict(request_id='table', action='read', session_id='s', window={'id': 'w'}, element={'id': 'e'}, params={})
        self.assertEqual(api.normalize('test_table', table),
                         api.normalize('test_table', {**table, 'params': {'limit': 100, 'allow_navigation': False}, 'timeout_ms': 30000}))

    async def test_status_during_approval_and_foreign_channel(self):
        one = await api.execute_test_operation('a', 'test_session', self.args)
        identifier = one['operation_id']
        await self.q.get_next_command('a', 0)
        await self.q.observe_operation('a', identifier, 'awaiting_approval', 1)
        consumer_registry.consumers.clear()
        args = dict(request_id='status', action='status', params={'operation_id': identifier})
        status = await api.execute_test_operation('a', 'test_session', args)
        self.assertEqual(status['data']['operation']['status'], 'awaiting_approval')
        self.assertEqual(status['operation_id'], identifier)
        self.assertEqual((await api.execute_test_operation('b', 'test_session', args))['error']['code'], 'permission_denied')
        self.assertEqual(self.q._journal.get('a', identifier)['state'], 'awaiting_approval')

    async def test_status_does_not_consume_quota_and_refreshes(self):
        one = await api.execute_test_operation('a', 'test_session', self.args)
        identifier = one['operation_id']
        self.q._journal.max_records = 1
        self.q._journal.max_bytes = 1
        args = dict(request_id='read', action='status', params={'operation_id': identifier})
        for n in range(3):
            status = await api.execute_test_operation('a', 'test_session', {**args, 'request_id': f'read-{n}'})
            self.assertEqual(status['data']['operation']['status'], 'queued')
        self.q._journal.transition(identifier, 'running')
        status = await api.execute_test_operation('a', 'test_session', {**args, 'request_id': 'read-0'})
        self.assertEqual(status['data']['operation']['status'], 'running')
        self.assertEqual(self.q._journal.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
        conflict = await api.execute_test_operation('a', 'test_session', {**args, 'request_id': 'start'})
        self.assertEqual(conflict['error']['code'], 'request_conflict')
        refused = await api.execute_test_operation('a', 'test_session', {**self.args, 'request_id': 'new'})
        self.assertEqual(refused['error']['code'], 'operation_quota_exceeded')

    async def test_unknown_result_preserved_and_never_replayed(self):
        one = await api.execute_test_operation('a', 'test_session', self.args)
        identifier = one['operation_id']
        await self.q.get_next_command('a', 0)
        result = api.envelope(self.args, operation_id=identifier, status='unknown', code='connection_lost')
        result['execution'] = 'unknown'
        await self.q.set_result(identifier, {'success': False, 'data': result, 'lifecycle_outcome': 'unknown'})
        self.assertEqual(self.q._journal.get('a', identifier)['state'], 'unknown')
        self.assertEqual((await api.execute_test_operation('a', 'test_session', self.args))['status'], 'unknown')
        self.assertIsNone(await self.q.get_next_command('a', 0))

    async def test_legacy_saved_status_keeps_identity_and_conflict(self):
        one = await api.execute_test_operation('a', 'test_session', self.args)
        args = dict(request_id='legacy-read', action='status', params={'operation_id': one['operation_id']})
        store = self.q._journal
        legacy, _ = store.reserve('a', args['request_id'], 'test_session', api.normalize('test_session', args), context={})
        value = api.envelope(args, operation_id=legacy, status='succeeded')
        value['data'] = {'operation': one}
        store.transition(legacy, 'running')
        store.finish(legacy, {'success': True, 'data': value})
        store.max_records = 1
        result = await api.execute_test_operation('a', 'test_session', args)
        self.assertEqual(result['operation_id'], legacy)
        conflict = await api.execute_test_operation('a', 'test_session', {**args, 'timeout_ms': 1})
        self.assertEqual(conflict['error']['code'], 'request_conflict')

    async def test_expired_result_can_be_read_at_quota(self):
        one = await api.execute_test_operation('a', 'test_session', self.args)
        store = self.q._journal
        store.transition(one['operation_id'], 'running')
        store.finish(one['operation_id'], {'success': True, 'data': {}})
        with store.db:
            store.db.execute('UPDATE operations SET expires=1')
        store.max_records = 1
        store.max_bytes = 1
        result = await api.execute_test_operation('a', 'test_session', dict(request_id='ttl-read', action='status', params={'operation_id':one['operation_id']}))
        self.assertEqual(result['data']['operation']['error']['code'], 'result_expired')
        self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)

    async def test_restart_recovers_identity_without_input(self):
        args = dict(request_id='inspect', session_id='session-before', action='windows', params={})
        one = await api.execute_test_operation('a', 'test_inspect', args)
        self.q._journal.close()
        self.q._journal = OperationJournal(Path(self.temp.name) / 'journal')
        self.addCleanup(self.q._journal.close)
        result = await api.saved_operation('a', one['operation_id'])
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['session_id'], 'session-before')

    async def test_invalid_input_is_not_admitted(self):
        result = await api.execute_test_operation('a', 'test_session', {**self.args, 'code': 'x'})
        self.assertEqual(result['error']['code'], 'invalid_params')
        self.assertEqual(self.q._journal.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 0)

    async def test_server_host_cannot_dispatch_ui(self):
        consumer_registry.consumers['a'] = Consumer('a', 'server_host')
        result = await api.execute_test_operation('a', 'test_session', self.args)
        self.assertEqual(result['error']['code'], 'client_context_unavailable')
        self.assertIsNone(await self.q.get_next_command('a', 0))

    async def test_cached_status_obeys_target_policy_after_policy_change(self):
        from onec_mcp_toolkit_proxy.anonymizer.anonymizer import Anonymizer
        args = dict(request_id='inspect', session_id='session', action='windows', params={})
        admitted = await api.execute_test_operation('a', 'test_inspect', args)
        identifier = admitted['operation_id']
        await self.q.get_next_command('a', 0)
        result = api.envelope(args, operation_id=identifier, status='succeeded')
        result['data'] = {'title': 'fixture.person@example.org'}
        await self.q.set_result(identifier, {'success': True, 'data': result})
        status_args = dict(request_id='cached-status', action='status', params={'operation_id': identifier})
        raw = await api.execute_test_operation('a', 'test_session', status_args)
        self.assertEqual(raw['data']['operation']['data']['title'], 'fixture.person@example.org')
        with patch.object(api.settings, 'anonymization_enabled', True), \
                patch.object(api.settings, 'anonymization_tools', {'test_inspect'}), \
                patch.object(api.settings, 'anonymization_dictionary_enabled', False), \
                patch.object(api.AnonymizerRegistry, 'get_async', AsyncMock(return_value=Anonymizer())):
            protected = await api.execute_test_operation('a', 'test_session', status_args)
        nested = protected['data']['operation']
        self.assertNotEqual(nested['data']['title'], 'fixture.person@example.org')
        self.assertEqual(nested['operation_id'], identifier)


if __name__ == '__main__':
    unittest.main()
