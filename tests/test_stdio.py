"""Реальный subprocess stdio MCP; обработка 1С имитируется файлами."""
import asyncio
import json
import os
from pathlib import Path
from queue import Queue, Empty
import subprocess
import socket
import sys
import tempfile
from threading import Thread
import time
import unittest

from onec_mcp_toolkit_proxy.file_transport import write_json
from onec_mcp_toolkit_proxy.mcp_handler import get_mcp_server

ROOT = Path(__file__).resolve().parents[1]


class Peer:
    def __init__(self, root, channel='test', timeout=8):
        self.root = Path(root)
        self.channel = channel
        self.messages = Queue()
        self.stderr = tempfile.TemporaryFile(mode='w+t', encoding='utf-8')
        env = dict(os.environ, RESPONSE_FORMAT='json', ANONYMIZATION_ENABLED='false',
                   ANONYMIZATION_NER_ENABLED='false', TIMEOUT=str(timeout), DEBUG='false',
                   PYTHONIOENCODING='utf-8')
        self.process = subprocess.Popen(
            [sys.executable, '-B', '-m', 'onec_mcp_toolkit_proxy', '--transport', 'stdio',
             '--file-root', str(root), '--channel', channel], cwd=ROOT, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
            encoding='utf-8')
        self.reader = Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except Exception as exc:
                self.messages.put(exc)  # Любой мусор в stdout ломает тест.
        self.messages.put(EOFError('stdio closed'))

    def send(self, method, params=None, ident=None):
        body = {'jsonrpc': '2.0', 'method': method}
        if ident is not None:
            body['id'] = ident
        if params is not None:
            body['params'] = params
        self.process.stdin.write(json.dumps(body, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def receive(self, ident):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            body = self.messages.get(timeout=max(.01, deadline - time.monotonic()))
            if isinstance(body, Exception):
                raise body
            if body.get('id') == ident:
                return body
        raise TimeoutError(ident)

    def initialize(self):
        self.send('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                  'clientInfo': {'name': 'stdio-test', 'version': '1'}}, 1)
        result = self.receive(1)
        self.send('notifications/initialized')
        return result

    def request_file(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            files = list(self.root.glob(f'{self.channel}/*/*.request.json'))
            if files:
                return files[0]
            time.sleep(.02)
        raise AssertionError('No request file')

    def respond(self, request, **result):
        deadline = time.monotonic() + 2
        while True:
            try:
                body = json.loads(request.read_text(encoding='utf-8'))
                request.rename(request.with_name(body['id'] + '.running'))
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
        write_json(request.with_name(body['id'] + '.response.json'), {'id': body['id'], **result})
        return body

    def close(self):
        if not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=6)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.process.stdout.close()
        self.stderr.close()


class StdioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='toolkit-stdio-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def peer(self, channel='test', timeout=8):
        peer = Peer(self.root, channel, timeout)
        self.addCleanup(peer.close)
        peer.initialize()
        return peer

    def test_catalog_query_errors_image_and_clean_eof(self):
        peer = self.peer('project-ca')
        peer.send('tools/list', ident=2)
        catalog = peer.receive(2)['result']['tools']
        expected = asyncio.run(get_mcp_server().list_tools())
        self.assertEqual({t['name']: t['inputSchema'] for t in catalog},
                         {t.name: t.inputSchema for t in expected})
        peer.send('tools/call', {'name': 'execute_query', 'arguments': {'query': 'ВЫБРАТЬ 1 КАК Проверка'}}, 3)
        body = peer.respond(peer.request_file(), success=True, data=[{'Проверка': 1}], count=1)
        self.assertEqual(body['channel'], 'project-ca')
        self.assertEqual(body['params']['query'], 'ВЫБРАТЬ 1 КАК Проверка')
        self.assertIn('Проверка', json.dumps(peer.receive(3), ensure_ascii=False))
        peer.send('tools/call', {'name': 'get_metadata', 'arguments': {}}, 4)
        peer.respond(peer.request_file(), success=False, error='TEST_DATABASE_ERROR')
        self.assertIn('TEST_DATABASE_ERROR', json.dumps(peer.receive(4)))
        peer.send('tools/call', {'name': 'get_screenshot', 'arguments': {}}, 5)
        png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
        peer.respond(peer.request_file(), success=True, image_base64=png, mime_type='image/png')
        images = [b for b in peer.receive(5)['result']['content'] if b['type'] == 'image']
        self.assertEqual(images[0]['data'], png)
        peer.process.stdin.close()
        self.assertEqual(peer.process.wait(timeout=6), 0)
        self.assertFalse(list(self.root.glob('*/*/session.json')))

    def test_same_channel_is_locked_other_channel_is_independent(self):
        first = self.peer()
        pointer = (self.root / 'test/current.json').read_bytes()
        second = Peer(self.root)
        self.addCleanup(second.close)
        self.assertEqual(second.process.wait(timeout=8), 1)
        second.stderr.seek(0)
        self.assertIn('busy', second.stderr.read())
        self.assertEqual(pointer, (self.root / 'test/current.json').read_bytes())
        other = self.peer('other')
        other.send('tools/call', {'name': 'get_metadata', 'arguments': {}}, 3)
        body = other.respond(other.request_file(), success=True, data='OTHER_CHANNEL')
        self.assertEqual(body['channel'], 'other')
        self.assertIn('OTHER_CHANNEL', json.dumps(other.receive(3)))
        self.assertIsNone(first.process.poll())

    def http_process(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        log = tempfile.TemporaryFile(mode='w+t', encoding='utf-8')
        self.addCleanup(log.close)
        env = dict(os.environ, FILE_BRIDGE_ROOT=str(self.root), FILE_BRIDGE_CHANNELS='test',
                   PORT=str(port), DEBUG='false', RESPONSE_FORMAT='json')
        proc = subprocess.Popen([sys.executable, '-B', '-m', 'onec_mcp_toolkit_proxy'],
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
        def stop():
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=5)
        self.addCleanup(stop)
        return proc, log

    def test_http_owner_rejects_stdio_on_same_channel(self):
        proc, _ = self.http_process()
        path = self.root / 'test/current.json'
        deadline = time.monotonic() + 8
        while not path.exists() and time.monotonic() < deadline:
            self.assertIsNone(proc.poll())
            time.sleep(.02)
        pointer = path.read_bytes()
        peer = Peer(self.root)
        self.addCleanup(peer.close)
        self.assertEqual(peer.process.wait(timeout=8), 1)
        self.assertEqual(pointer, path.read_bytes())

    def test_stdio_owner_rejects_http_on_same_channel(self):
        self.peer()
        pointer = (self.root / 'test/current.json').read_bytes()
        proc, log = self.http_process()
        self.assertNotEqual(proc.wait(timeout=8), 0)
        log.seek(0)
        self.assertIn('busy', log.read())
        self.assertEqual(pointer, (self.root / 'test/current.json').read_bytes())

    def test_corrupt_response_stops_stdio_and_revokes_session(self):
        peer = self.peer()
        peer.send('tools/call', {'name': 'get_metadata', 'arguments': {}}, 2)
        request = peer.request_file()
        body = json.loads(request.read_text(encoding='utf-8'))
        write_json(request.with_name(body['id'] + '.response.json'), {'id': 'wrong', 'success': True})
        self.assertEqual(peer.process.wait(timeout=8), 1)
        self.assertFalse(list(self.root.glob('*/*/session.json')))
        self.assertTrue(request.exists())

    def test_timeout_blocks_next_request_until_late_reply(self):
        peer = self.peer(timeout=1)
        peer.send('tools/call', {'name': 'get_metadata', 'arguments': {}}, 2)
        request = peer.request_file()
        self.assertIn('Timeout waiting', json.dumps(peer.receive(2)))
        peer.send('tools/call', {'name': 'get_metadata', 'arguments': {}}, 3)
        time.sleep(.4)
        self.assertEqual(list(self.root.glob('test/*/*.request.json')), [request])
        peer.respond(request, success=True, data='late')
        next_request = peer.request_file()
        # Дождаться удаления первого задания и выдачи второго.
        deadline = time.monotonic() + 3
        while next_request == request and time.monotonic() < deadline:
            time.sleep(.02)
            next_request = peer.request_file()
        self.assertNotEqual(next_request, request)
        peer.respond(next_request, success=True, data='second')
        self.assertIn('second', json.dumps(peer.receive(3)))

    def test_crash_releases_lock_but_unresolved_request_blocks_restart(self):
        peer = self.peer()
        peer.send('tools/call', {'name': 'get_metadata', 'arguments': {}}, 2)
        request = peer.request_file()
        pointer = (self.root / 'test/current.json').read_bytes()
        peer.process.kill()
        peer.process.wait(timeout=5)
        second = Peer(self.root)
        self.addCleanup(second.close)
        self.assertEqual(second.process.wait(timeout=8), 1)
        second.stderr.seek(0)
        self.assertIn('Unresolved file request', second.stderr.read())
        self.assertTrue(request.exists())
        self.assertEqual(pointer, (self.root / 'test/current.json').read_bytes())

    def test_clean_restart_uses_new_session(self):
        peer = self.peer()
        pointer = (self.root / 'test/current.json').read_bytes()
        peer.process.stdin.close()
        self.assertEqual(peer.process.wait(timeout=6), 0)
        self.peer()
        self.assertNotEqual(pointer, (self.root / 'test/current.json').read_bytes())

    def test_eof_during_request_preserves_unknown_outcome(self):
        peer = self.peer(timeout=30)
        peer.send('tools/call', {'name': 'get_metadata', 'arguments': {}}, 2)
        request = peer.request_file()
        peer.process.stdin.close()
        self.assertEqual(peer.process.wait(timeout=6), 0)
        self.assertTrue(request.exists())
        self.assertFalse(list(self.root.glob('*/*/session.json')))

    def test_fragmented_unicode_input(self):
        peer = self.peer()
        packet = (json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
            'params': {'name': 'execute_query', 'arguments': {'query': 'ВЫБРАТЬ 1'}}},
            ensure_ascii=False) + '\n').encode('utf-8')
        for i in range(0, len(packet), 7):
            peer.process.stdin.buffer.write(packet[i:i+7])
            peer.process.stdin.buffer.flush()
        body = peer.respond(peer.request_file(), success=True, data=[{'value': 1}])
        self.assertEqual(body['params']['query'], 'ВЫБРАТЬ 1')
        self.assertFalse(peer.receive(2)['result'].get('isError'))

    def test_invalid_cli_does_not_create_exchange(self):
        for args in ([], ['--file-root', str(self.root)],
                     ['--file-root', str(self.root), '--channel', 'a,b'],
                     ['--file-root', str(self.root), '--channel', '../bad']):
            with self.subTest(args=args):
                env = {k: v for k, v in os.environ.items() if not k.startswith('FILE_BRIDGE_')}
                result = subprocess.run([sys.executable, '-B', '-m', 'onec_mcp_toolkit_proxy',
                    '--transport', 'stdio', *args], cwd=ROOT, env=env, capture_output=True, timeout=8)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b'')
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
