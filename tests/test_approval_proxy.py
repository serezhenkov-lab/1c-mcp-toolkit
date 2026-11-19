"""Permissions are decided by 1C; both proxy entry points only relay commands."""
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

from onec_mcp_toolkit_proxy import mcp_handler, rest_api
from onec_mcp_toolkit_proxy.config import Settings


CODES = (
    'ПодключитьВнешнююКомпоненту("barcode.zip", "Barcode", ТипВнешнейКомпоненты.Native);',
    'Объект.Записать(); Объект.Удалить();',
    'УстановитьПривилегированныйРежим(Истина);',
    'Выполнить("Результат = 42;"); ЗапуститьПриложение("test");',
    'Результат = 42;',
)


def rest_request(body):
    receive = AsyncMock(return_value={
        'type': 'http.request', 'body': json.dumps(body).encode(), 'more_body': False,
    })
    return Request({
        'type': 'http', 'method': 'POST', 'path': '/api/execute_code',
        'query_string': b'channel=1629166-ca',
        'headers': [(b'content-type', b'application/json')],
    }, receive)


class ApprovalProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_entry_points_relay_code_despite_legacy_environment(self):
        for legacy_value in (None, 'false', 'true'):
            with patch.dict(os.environ, {'DANGEROUS_KEYWORDS': 'Результат,ПодключитьВнешнююКомпоненту'}):
                if legacy_value is None:
                    os.environ.pop('ALLOW_DANGEROUS_WITH_APPROVAL', None)
                else:
                    os.environ['ALLOW_DANGEROUS_WITH_APPROVAL'] = legacy_value
                settings = Settings()
                for code in CODES:
                    for context in ('client', 'server'):
                        for entry in ('mcp', 'rest'):
                            with self.subTest(legacy=legacy_value, code=code, context=context, entry=entry):
                                response = {'success': True, 'data': {'barcode': 'simulated'}}
                                module = mcp_handler if entry == 'mcp' else rest_api
                                with patch.object(module, 'settings', settings), patch.object(
                                    module, '_execute_1c_command', new_callable=AsyncMock,
                                    return_value=response,
                                ) as execute, patch.object(
                                    mcp_handler, '_get_channel_from_context', return_value='1629166-ca',
                                ):
                                    if entry == 'mcp':
                                        result = await mcp_handler.execute_code(None, code, context)
                                    else:
                                        result = json.loads((await rest_api.execute_code_handler(
                                            rest_request({'code': code, 'execution_context': context})
                                        )).body)
                                self.assertEqual(result, response)
                                execute.assert_awaited_once()
                                self.assertEqual(execute.call_args.args[:2], (
                                    'execute_code', {'code': code, 'execution_context': context},
                                ))
                                channel = (execute.call_args.kwargs['channel'] if entry == 'mcp'
                                           else execute.call_args.args[2])
                                self.assertEqual(channel, '1629166-ca')

    async def test_processing_rejection_and_error_are_preserved(self):
        for response in (
            {'success': False, 'error': 'Опасная операция запрещена режимом Toolkit.'},
            {'success': False, 'error': 'Пользователь отклонил выполнение команды.'},
            {'success': False, 'error': 'Ошибка подключения компоненты', 'line': 1},
        ):
            for module in (mcp_handler, rest_api):
                with self.subTest(response=response, entry=module.__name__), patch.object(
                    module, '_execute_1c_command', new_callable=AsyncMock, return_value=response,
                ) as execute:
                    if module is mcp_handler:
                        result = await mcp_handler.execute_code(None, CODES[0])
                    else:
                        result = json.loads((await rest_api.execute_code_handler(
                            rest_request({'code': CODES[0]})
                        )).body)
                    self.assertEqual(result, response)
                    execute.assert_awaited_once()

    async def test_invalid_parameters_never_reach_processing(self):
        for body in ({'code': ''}, {'code': '   '}, {'code': 'Результат = 1;', 'execution_context': 'invalid'}):
            with self.subTest(body=body), patch.object(
                mcp_handler, '_execute_1c_command', new_callable=AsyncMock,
            ) as mcp_execute, patch.object(
                rest_api, '_execute_1c_command', new_callable=AsyncMock,
            ) as rest_execute:
                result = await mcp_handler.execute_code(None, **body)
                self.assertFalse(result['success'])
                result = await rest_api.execute_code_handler(rest_request(body))
                self.assertEqual(result.status_code, 422)
                mcp_execute.assert_not_awaited()
                rest_execute.assert_not_awaited()
