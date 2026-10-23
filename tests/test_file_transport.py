import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timedelta

from onec_mcp_toolkit_proxy.command_queue import ChannelCommandQueue
from onec_mcp_toolkit_proxy.file_transport import FileTransport, write_json, configured_channels
from onec_mcp_toolkit_proxy.server import CommandResult


class FileTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.queue = ChannelCommandQueue()
        self.bridge = FileTransport(self.temp.name, 'test', self.queue, 30, CommandResult)

    async def issue(self):
        command_id = await self.queue.add_command('test', 'execute_query', {'query': 'ВЫБРАТЬ 1'})
        await self.bridge.step()
        return command_id

    async def test_round_trip_and_partial_response(self):
        command_id = await self.issue()
        request = self.bridge.directory / (command_id + '.request.json')
        command = json.loads(request.read_text(encoding='utf-8'))
        self.assertEqual(command['params']['query'], 'ВЫБРАТЬ 1')
        waiter = asyncio.create_task(self.queue.wait_for_result(command_id, 1))
        await asyncio.sleep(0)
        request.rename(request.with_name(command_id + '.running'))
        response = self.bridge.directory / (command_id + '.response.json')
        response.with_suffix('.tmp').write_text('{', encoding='utf-8')
        await self.bridge.step()
        self.assertFalse(waiter.done())
        write_json(response, {'id': command_id, 'success': True, 'data': [{'x': 1}], 'count': 1})
        await self.bridge.step()
        self.assertEqual((await waiter)['data'], [{'x': 1}])
        self.assertFalse(request.with_name(command_id + '.running').exists())

    async def test_timeout_does_not_replay_or_dispatch_next(self):
        command_id = await self.issue()
        with self.assertRaises(asyncio.TimeoutError):
            await self.queue.wait_for_result(command_id, 0.001)
        second = await self.queue.add_command('test', 'get_metadata', {})
        await self.bridge.step()
        self.assertEqual(self.bridge.active, command_id)
        self.assertFalse((self.bridge.directory / (second + '.request.json')).exists())

    async def test_other_channel_is_not_consumed(self):
        await self.queue.add_command('other', 'get_metadata', {})
        await self.bridge.step()
        self.assertIsNone(self.bridge.active)

    async def test_wrong_result_id_is_rejected(self):
        command_id = await self.issue()
        write_json(self.bridge.directory / (command_id + '.response.json'),
                   {'id': 'wrong', 'success': True})
        with self.assertRaises(ValueError):
            await self.bridge.step()
        self.assertEqual(self.bridge.active, command_id)

    async def test_restart_uses_new_directory(self):
        await self.issue()
        other = FileTransport(self.temp.name, 'test', self.queue, 30, CommandResult)
        self.assertNotEqual(other.directory, self.bridge.directory)
        await other.step()
        self.assertIsNone(other.active)

    async def test_current_pointer_changes_and_old_response_is_not_consumed(self):
        old_id = await self.issue()
        pointer = self.bridge.directory.parent / 'current.json'
        self.assertEqual(json.loads(pointer.read_text())['session'], self.bridge.directory.name)
        new_queue = ChannelCommandQueue()
        other = FileTransport(self.temp.name, 'test', new_queue, 30, CommandResult)
        current = json.loads(pointer.read_text())
        self.assertEqual(current, {'version': 1, 'channel': 'test', 'session': other.directory.name})
        new_id = await new_queue.add_command('test', 'get_metadata', {})
        await other.step()
        write_json(self.bridge.directory / (old_id + '.response.json'),
                   {'id': old_id, 'success': True, 'data': 'old'})
        await other.step()
        self.assertEqual(other.active, new_id)
        # Завершение старого worker не отзывает указатель нового сеанса.
        task = asyncio.create_task(self.bridge.run())
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(json.loads(pointer.read_text())['session'], other.directory.name)
        self.assertTrue((other.directory / 'session.json').exists())

    async def test_deadline_includes_queue_wait(self):
        command_id = await self.queue.add_command('test', 'get_metadata', {})
        created = datetime.utcnow() - timedelta(seconds=50)
        self.queue._channels['test']._pending[command_id].created_at = created
        await self.bridge.step()
        body = json.loads((self.bridge.directory / (command_id + '.request.json')).read_text())
        self.assertEqual(body['expires_at'], (created + timedelta(seconds=30)).strftime('%Y%m%d%H%M%S'))

    async def test_shutdown_revokes_session(self):
        task = asyncio.create_task(self.bridge.run())
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse((self.bridge.directory / 'session.json').exists())

    async def test_failed_channel_does_not_stop_other_channel(self):
        command_id = await self.issue()
        write_json(self.bridge.directory / (command_id + '.response.json'),
                   {'id': 'wrong', 'success': True})
        other = FileTransport(self.temp.name, 'other', self.queue, 30, CommandResult)
        other_id = await self.queue.add_command('other', 'get_metadata', {})
        task = asyncio.create_task(other.run())
        try:
            await self.bridge.run()  # повреждённый ответ останавливает только этот канал
            await asyncio.sleep(0.05)
            self.assertFalse(task.done())
            self.assertEqual(other.active, other_id)
            self.assertFalse((self.bridge.directory / 'session.json').exists())
            self.assertTrue((other.directory / 'session.json').exists())
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task


class ChannelConfigurationTests(unittest.TestCase):
    def test_single(self):
        self.assertEqual(configured_channels({'FILE_BRIDGE_ROOT': 'root',
                                             'FILE_BRIDGE_CHANNELS': 'client-test'}), ['client-test'])

    def test_multiple(self):
        self.assertEqual(configured_channels({'FILE_BRIDGE_ROOT': 'root',
            'FILE_BRIDGE_CHANNELS': '1703784, 1690771-test', 'FILE_BRIDGE_CHANNEL': 'old'}),
            ['1703784', '1690771-test'])

    def test_old_setting_requires_migration(self):
        with self.assertRaisesRegex(ValueError, 'FILE_BRIDGE_CHANNELS'):
            configured_channels({'FILE_BRIDGE_ROOT': 'root', 'FILE_BRIDGE_CHANNEL': 'old'})

    def test_invalid_channels(self):
        for raw in ('', 'a,', 'a,A', '../a', 'a/b', 'a\\b', 'CON', 'com1', 'тест', 'x'*65):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                configured_channels({'FILE_BRIDGE_ROOT': 'root', 'FILE_BRIDGE_CHANNELS': raw})

    def test_disabled(self):
        self.assertEqual(configured_channels({'FILE_BRIDGE_CHANNELS': 'bad/'}), [])


if __name__ == '__main__':
    unittest.main()
