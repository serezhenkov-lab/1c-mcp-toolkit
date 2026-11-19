import tempfile
import unittest
from pydantic import ValidationError
from onec_mcp_toolkit_proxy.operation_journal import OperationJournal, OperationError
from onec_mcp_toolkit_proxy.result_models import CommandResult


def progress(count=0, elapsed=100, phase='waiting', step=None):
    return dict(phase=phase, completed_count=count, elapsed_ms=elapsed, last_confirmed_step=step)


class ProgressTests(unittest.TestCase):
    def test_only_durable_owner_advertises_progress(self):
        from onec_mcp_toolkit_proxy.command_queue import Command
        self.assertNotIn('lifecycle_progress_version', Command('old', 'test_expect', {}).to_dict())
        command = Command('new', 'test_expect', {}, durable=True).to_dict()
        self.assertEqual(command['lifecycle_version'], 1)
        self.assertEqual(command['lifecycle_progress_version'], 1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = OperationJournal(self.temp.name)
        self.addCleanup(lambda: self.store.close())
        self.op, _ = self.store.reserve('a', 'request', 'test_expect', {}, context={'session_id':'session'})
        self.store.transition(self.op, 'running')

    def test_event_schema_no_arbitrary_text_or_inexact_numbers(self):
        CommandResult(id='a', success=False, lifecycle_event='progress', lifecycle_seq=3, progress=progress())
        for value in [dict(progress(), phase='SECRET'), dict(progress(), completed_count=True),
                      dict(progress(), elapsed_ms=1.5), dict(progress(), text='SECRET'),
                      dict(progress(), last_confirmed_step='action')]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                CommandResult(id='a', success=False, lifecycle_event='progress', lifecycle_seq=3, progress=value)
        with self.assertRaises(ValidationError):
            CommandResult(id='a', success=True, progress=progress())

    def test_monotonic_replay_and_final_immutable(self):
        self.assertTrue(self.store.observe(self.op, 'progress', 3, progress()))
        snapshot = self.store.snapshot('a', self.op)
        self.assertEqual(snapshot['status'], 'running')
        self.assertIsNone(snapshot['result'])
        self.assertEqual(snapshot['progress']['operation_id'], self.op)
        self.assertTrue(self.store.observe(self.op, 'progress', 3, progress()))
        self.assertFalse(self.store.observe(self.op, 'progress', 3, progress(elapsed=200)))
        self.assertFalse(self.store.observe(self.op, 'running', 2))
        self.assertFalse(self.store.observe(self.op, 'progress', 4, progress(elapsed=99)))
        self.assertTrue(self.store.observe(self.op, 'progress', 4, progress(1, 200, 'observing', 'action')))
        self.assertFalse(self.store.observe(self.op, 'progress', 5, progress(elapsed=300)))
        final = {'success': True, 'data': {'confirmed': 1}}
        self.store.finish(self.op, final)
        self.assertFalse(self.store.observe(self.op, 'progress', 6, progress(1, 400, 'observing', 'action')))
        self.assertEqual(self.store.snapshot('a', self.op)['result'], final)
        self.assertIsNone(self.store.snapshot('a', self.op)['progress'])

    def test_channel_isolation_and_restart_unknown_without_replay(self):
        self.store.observe(self.op, 'progress', 3, progress())
        with self.assertRaises(OperationError): self.store.snapshot('other', self.op)
        self.store.close()
        self.store = OperationJournal(self.temp.name)
        state = self.store.snapshot('a', self.op)
        self.assertEqual(state['status'], 'unknown')
        self.assertEqual(state['progress']['sequence'], 3)
        self.assertFalse(self.store.observe(self.op, 'progress', 4, progress(elapsed=300)))
        self.assertEqual(self.store.reserve('a', 'request', 'test_expect', {}, context={'session_id':'session'}), (self.op, False))

    def test_optional_progress_quota_does_not_fail_operation(self):
        self.store.max_bytes = 20
        self.assertFalse(self.store.observe(self.op, 'progress', 3, progress()))
        self.assertEqual(self.store.snapshot('a', self.op)['status'], 'running')
        self.assertTrue(self.store.finish(self.op, {'success':True}))
        self.assertEqual(self.store.snapshot('a', self.op)['status'], 'succeeded')

    def test_replacement_accounting_and_expiry(self):
        self.store.observe(self.op, 'progress', 3, progress())
        initial = self.store.get('a', self.op)['progress_bytes']
        self.store.observe(self.op, 'progress', 4, progress(elapsed=200))
        self.assertEqual(self.store.get('a', self.op)['progress_bytes'], initial)
        self.store.finish(self.op, {'success':True})
        self.assertEqual(self.store.get('a', self.op)['progress_bytes'], 0)
        self.store.db.execute('UPDATE operations SET expires=0 WHERE id=?', (self.op,))
        self.assertEqual(self.store.snapshot('a', self.op)['status'], 'result_expired')
        self.assertIsNone(self.store.snapshot('a', self.op)['progress'])


class TransportProgressTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from pathlib import Path
        from onec_mcp_toolkit_proxy.command_queue import ChannelCommandQueue
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.q = ChannelCommandQueue()
        self.q._journal = OperationJournal(Path(self.temp.name) / 'journal')
        self.addCleanup(self.q._journal.close)

    async def test_file_keeps_active_command_and_never_releases_waiter(self):
        from pathlib import Path
        from onec_mcp_toolkit_proxy.file_transport import FileTransport, write_json
        bridge = FileTransport(Path(self.temp.name) / 'files', 'a', self.q, 30, CommandResult)
        op = await self.q.add_operation('a', 'key', 'test_expect', {})
        await bridge.step()
        event = bridge.directory / (op + '.lifecycle.json')
        write_json(event, dict(id=op, success=False, lifecycle_event='progress', lifecycle_seq=3, progress=progress()))
        await bridge.step()
        self.assertEqual(bridge.active, op)
        self.assertFalse(self.q.get_command(op).result_event.is_set())
        self.assertEqual(self.q.operation_store().snapshot('a',op)['progress']['sequence'],3)
        await bridge.step()  # duplicate file is idempotent
        write_json(bridge.directory / (op + '.response.json'), dict(id=op,success=True,data=42))
        await bridge.step()
        self.assertIsNone(bridge.active)
        self.assertEqual(self.q.operation_store().snapshot('a',op)['result']['data'],42)
        self.assertFalse(event.exists())

    async def test_http_channel_stale_final_and_public_view(self):
        import httpx
        from unittest.mock import patch
        from onec_mcp_toolkit_proxy import server, operation_api, test_client_operations
        op = await self.q.add_operation('a', 'key', 'test_expect', {'session_id':'s'})
        await self.q.get_next_command('a',0)
        event = dict(id=op,success=False,lifecycle_event='progress',lifecycle_seq=4,progress=progress(1,200,'observing','action'))
        with patch.object(server,'channel_command_queue',self.q), patch.object(operation_api,'channel_command_queue',self.q), patch.object(test_client_operations,'channel_command_queue',self.q):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(server.app),base_url='http://test') as client:
                self.assertEqual((await client.post('/1c/result?channel=b',json=event)).status_code,404)
                self.assertEqual((await client.post('/1c/result?channel=a',json=event)).status_code,200)
                current = await test_client_operations.saved_operation('a',op)
                self.assertEqual(current['execution'],'invoked')
                self.assertEqual(current['data']['progress']['operation_id'],op)
                self.assertFalse(self.q.get_command(op).result_event.is_set())
                event['lifecycle_seq']=3
                self.assertEqual((await client.post('/1c/result?channel=a',json=event)).status_code,409)
                await self.q.set_result(op,{'success':True,'data':42})
                event['lifecycle_seq']=5
                self.assertEqual((await client.post('/1c/result?channel=a',json=event)).status_code,409)
                self.assertEqual(self.q.operation_store().snapshot('a',op)['result']['data'],42)
