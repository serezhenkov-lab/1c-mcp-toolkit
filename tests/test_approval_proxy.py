"""The proxy prohibition must remain stronger than the form session mode."""
import unittest
from unittest.mock import AsyncMock, patch

from onec_mcp_toolkit_proxy import mcp_handler


class ApprovalProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_proxy_block_never_enqueues_dangerous_code(self):
        with patch.object(mcp_handler.settings, 'allow_dangerous_with_approval', False), \
                patch.object(mcp_handler, '_execute_1c_command', new_callable=AsyncMock) as execute:
            result = await mcp_handler.execute_code(None, 'Объект.Записать();')
        self.assertFalse(result['success'])
        self.assertIn('Запрет proxy', result['error'])
        execute.assert_not_awaited()

    async def test_proxy_approval_passes_exact_code_to_form(self):
        code = 'Объект.Записать(); Объект.Удалить();'
        with patch.object(mcp_handler.settings, 'allow_dangerous_with_approval', True), \
                patch.object(mcp_handler, '_execute_1c_command', new_callable=AsyncMock,
                             return_value={'success': True, 'data': 1}) as execute:
            result = await mcp_handler.execute_code(None, code)
        self.assertTrue(result['success'])
        execute.assert_awaited_once()
        tool, params = execute.call_args.args
        self.assertEqual(tool, 'execute_code')
        self.assertEqual(params['code'], code)
        self.assertTrue(params['requires_approval'])
        self.assertTrue(params['dangerous_keywords'])

    async def test_safe_code_does_not_request_approval(self):
        with patch.object(mcp_handler.settings, 'allow_dangerous_with_approval', False), \
                patch.object(mcp_handler, '_execute_1c_command', new_callable=AsyncMock,
                             return_value={'success': True, 'data': 42}) as execute:
            result = await mcp_handler.execute_code(None, 'Результат = 42;')
        self.assertEqual(result['data'], 42)
        self.assertNotIn('requires_approval', execute.call_args.args[1])
