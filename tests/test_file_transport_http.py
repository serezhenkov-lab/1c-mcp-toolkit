"""Интеграция MCP HTTP -> очередь -> файлы -> ответ MCP (клиент 1С имитируется)."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import patch

from starlette.testclient import TestClient

from onec_mcp_toolkit_proxy.server import app
from onec_mcp_toolkit_proxy.file_transport import write_json


@contextmanager
def verify_sessions_removed(test, root):
    yield
    test.assertFalse(list(Path(root).glob('*/*/session.json')))
    test.assertEqual(app.state.file_bridges, {})


class HttpIntegrationTests(unittest.TestCase):
    def test_mcp_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            'FILE_BRIDGE_ROOT': root, 'FILE_BRIDGE_CHANNELS': 'rdp-test,1703784',
            'FILE_BRIDGE_CHANNEL': 'ignored-legacy'
        }), patch('onec_mcp_toolkit_proxy.server.settings.timeout', 8), verify_sessions_removed(self, root), TestClient(app) as client:
            self.assertEqual(client.get('/1c/poll?channel=rdp-test').status_code, 409)
            self.assertEqual(client.get('/1c/poll?channel=other').status_code, 204)
            self.assertEqual(client.get('/1c/poll?channel=1703784').status_code, 409)
            self.assertEqual(set(app.state.file_bridges), {'rdp-test', '1703784'})
            headers = {'Accept': 'application/json, text/event-stream'}
            url = '/mcp?channel=rdp-test'
            response = client.post(url, headers=headers, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                           'clientInfo': {'name': 'file-test', 'version': '1'}}})
            self.assertEqual(response.status_code, 200, response.text)
            headers['mcp-session-id'] = response.headers['mcp-session-id']
            client.post(url, headers=headers,
                        json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            with ThreadPoolExecutor() as pool:
                result = pool.submit(client.post, url, headers=headers, json={
                    'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                    'params': {'name': 'execute_query', 'arguments': {'query': 'ВЫБРАТЬ 1 КАК Проверка'}}})
                deadline = time.monotonic() + 5
                requests = []
                while time.monotonic() < deadline:
                    requests = list(Path(root).glob('rdp-test/*/*.request.json'))
                    if requests or result.done():
                        break
                    time.sleep(0.02)
                self.assertTrue(requests, result.result().text if result.done() else 'No file request')
                # Первый канал остаётся без ответа, второй должен завершиться независимо.
                second_headers = {'Accept': 'application/json, text/event-stream'}
                second_url = '/mcp?channel=1703784'
                initialized = client.post(second_url, headers=second_headers, json={
                    'jsonrpc': '2.0', 'id': 10, 'method': 'initialize',
                    'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
                               'clientInfo': {'name': 'second-project', 'version': '1'}}})
                second_headers['mcp-session-id'] = initialized.headers['mcp-session-id']
                client.post(second_url, headers=second_headers,
                            json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                second = pool.submit(client.post, second_url, headers=second_headers, json={
                    'jsonrpc': '2.0', 'id': 11, 'method': 'tools/call',
                    'params': {'name': 'execute_query', 'arguments': {'query': 'ВЫБРАТЬ 2'}}})
                deadline = time.monotonic() + 3
                second_files = []
                while time.monotonic() < deadline:
                    second_files = list(Path(root).glob('1703784/*/*.request.json'))
                    if second_files or second.done():
                        break
                    time.sleep(0.02)
                self.assertTrue(second_files)
                second_request = second_files[0]
                second_body = json.loads(second_request.read_text(encoding='utf-8'))
                self.assertEqual(second_body['channel'], '1703784')
                second_request.rename(second_request.with_name(second_body['id'] + '.running'))
                write_json(second_request.with_name(second_body['id'] + '.response.json'), {
                    'id': second_body['id'], 'success': True, 'data': [{'bridge_marker': 942}], 'count': 1})
                second_response = second.result(timeout=3)
                self.assertIn('942', second_response.text)
                self.assertNotIn('731', second_response.text)
                self.assertFalse(result.done())
                request = requests[0]
                body = json.loads(request.read_text(encoding='utf-8'))
                self.assertEqual(body['channel'], 'rdp-test')
                request.rename(request.with_name(body['id'] + '.running'))
                write_json(request.with_name(body['id'] + '.response.json'), {
                    'id': body['id'], 'success': True, 'data': [{'bridge_marker': 731}], 'count': 1})
                response = result.result(timeout=5)
                self.assertEqual(response.status_code, 200)
                self.assertIn('731', response.text)
                self.assertNotIn('942', response.text)
                self.assertNotIn('"isError":true', response.text)

    def test_http_poll_remains_available_without_file_mode(self):
        with patch.dict(os.environ, {'FILE_BRIDGE_ROOT': ''}):
            client = TestClient(app)
            self.assertEqual(client.get('/1c/poll?channel=rdp-test').status_code, 204)
