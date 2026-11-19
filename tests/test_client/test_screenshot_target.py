import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import ValidationError
from onec_mcp_toolkit_proxy.tools import GetScreenshotParams
from onec_mcp_toolkit_proxy.mcp_handler import _execute_1c_command, get_screenshot, mcp
from onec_mcp_toolkit_proxy.server import app


class ScreenshotTargetTests(unittest.IsolatedAsyncioTestCase):
    def test_validation(self):
        self.assertNotIn('target', GetScreenshotParams().model_dump(exclude_none=True))
        for bad in ({'target': 'bad'}, {'target': 'test_client'}, {'session_id': 's'},
                    {'target': 'toolkit', 'session_id': 's'}, {'target': 'test_client', 'session_id': 1},
                    {'target': 'test_client', 'session_id': ''},
                    {'target': 'test_client', 'session_id': 's', 'form_name': 'DO_NOT_OPEN'}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                GetScreenshotParams.model_validate(bad)

    async def test_client_dispatches_only_to_bound_client_and_preserves_refusal(self):
        from onec_mcp_toolkit_proxy.consumer_registry import consumer_registry, Consumer
        refused = {'success': False, 'error': 'screenshot_target_unavailable'}
        with patch.object(consumer_registry, 'consumers', {'default': Consumer('default', 'http')}), patch(
                'onec_mcp_toolkit_proxy.mcp_handler._execute_bound_1c_command', new_callable=AsyncMock,
                return_value=refused) as dispatch:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://localhost') as client:
                response = await client.post('/api/get_screenshot', json={'target': 'test_client', 'session_id': 's'})
                self.assertEqual(response.json(), refused)
                self.assertEqual(dispatch.call_args.args[:3], ('get_screenshot', {'target': 'test_client', 'session_id': 's', 'scale_percent': 100, 'show_grid': False}, 'default'))
        with patch.object(consumer_registry, 'consumers', {'default': Consumer('default', 'server_host')}), patch(
                'onec_mcp_toolkit_proxy.mcp_handler._execute_bound_1c_command', new_callable=AsyncMock) as dispatch:
            result = await _execute_1c_command('get_screenshot', {'target': 'test_client', 'session_id': 's'})
            self.assertFalse(result['success'])
            self.assertNotIn('image_base64', result)
            dispatch.assert_not_awaited()

    async def test_capture_identity_survives_callback_and_mcp(self):
        from onec_mcp_toolkit_proxy.result_models import CommandResult
        evidence = {'capture_target': {'process_id': 123, 'created': 'proof'},
                    'target': 'test_client', 'session_id': 'session', 'image_anonymized': False}
        payload = dict(id='capture', success=True, image_base64='iVBORw0KGgo=',
                       mime_type='image/png', window_rect={'x': 0, 'y': 0, 'width': 1, 'height': 1},
                       overlays=[], capture_complete=True, **evidence)
        model = CommandResult(**payload)
        self.assertEqual({k:model.model_dump()[k] for k in evidence}, evidence)
        with patch('onec_mcp_toolkit_proxy.server.channel_command_queue.set_result', new_callable=AsyncMock, return_value=True) as store:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://localhost') as client:
                response = await client.post('/1c/result', json=payload)
                self.assertEqual(response.status_code, 200, response.text)
            stored = store.call_args.args[1]
            self.assertEqual({k:stored[k] for k in evidence}, evidence)
        with patch('onec_mcp_toolkit_proxy.mcp_handler._get_channel_from_context', return_value='test'), patch(
                'onec_mcp_toolkit_proxy.mcp_handler._execute_1c_command', new_callable=AsyncMock, return_value=payload):
            parts = await get_screenshot(None, target='test_client', session_id='session')
            metadata = [json.loads(p.text) for p in parts if p.type == 'text']
            actual = next(p for p in metadata if 'capture_target' in p)
            self.assertEqual({k:actual[k] for k in evidence}, evidence)

    async def test_mcp_and_legacy_params(self):
        with patch('onec_mcp_toolkit_proxy.mcp_handler._get_channel_from_context', return_value='test'), patch(
                'onec_mcp_toolkit_proxy.mcp_handler._execute_1c_command', new_callable=AsyncMock,
                return_value={'success': False, 'error': 'capture stub'}) as execute:
            await get_screenshot(None)
            self.assertEqual(execute.call_args.args[1], {'scale_percent': 100, 'show_grid': False})
            await get_screenshot(None, target='toolkit')
            self.assertEqual(execute.call_args.args[1]['target'], 'toolkit')
            await get_screenshot(None, target='test_client', session_id='s')
            self.assertEqual(execute.call_args.args[1]['session_id'], 's')
        schema = next(t.inputSchema for t in await mcp.list_tools() if t.name == 'get_screenshot')
        self.assertIn('target', schema['properties'])
        self.assertIn('session_id', schema['properties'])


if __name__ == '__main__':
    unittest.main()

