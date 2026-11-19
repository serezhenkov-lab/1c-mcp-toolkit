"""Mode control relays to the selected session without a second approval filter."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from mcp.server.fastmcp.exceptions import ToolError
from starlette.requests import Request

from onec_mcp_toolkit_proxy import mcp_handler, rest_api
from onec_mcp_toolkit_proxy.tools import SetApprovalModeParams


def request(body):
    return Request({
        "type": "http", "method": "POST", "path": "/api/set_approval_mode",
        "query_string": b"channel=approval-test",
        "headers": [(b"content-type", b"application/json")],
    }, AsyncMock(return_value={
        "type": "http.request", "body": json.dumps(body).encode(), "more_body": False,
    }))


class ApprovalControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_three_modes_reach_selected_channel_and_preserve_response(self):
        for mode in ("deny", "ask", "session_allow"):
            response = {"success": True, "data": {"mode": mode, "scope": "toolkit_session"}}
            for module in (mcp_handler, rest_api):
                with self.subTest(mode=mode, entry=module.__name__), patch.object(
                    module, "_execute_1c_command", new_callable=AsyncMock, return_value=response,
                ) as execute, patch.object(mcp_handler, "_get_channel_from_context", return_value="approval-test"):
                    if module is mcp_handler:
                        result = await mcp_handler.set_approval_mode(None, mode)
                    else:
                        result = json.loads((await rest_api.set_approval_mode_handler(request({"mode": mode}))).body)
                    self.assertEqual(result, response)
                    execute.assert_awaited_once()
                    self.assertEqual(execute.call_args.args[:2], ("set_approval_mode", {"mode": mode}))
                    channel = execute.call_args.kwargs.get("channel") or execute.call_args.args[2]
                    self.assertEqual(channel, "approval-test")

    async def test_invalid_arguments_never_change_session(self):
        for body in ({}, {"mode": "permanent"}, {"mode": "ASK"}, {"mode": True},
                     {"mode": None}, {"mode": "session_allow", "persist": True}, []):
            with self.subTest(body=body), patch.object(rest_api, "_execute_1c_command", new_callable=AsyncMock) as execute:
                with self.assertRaises(ValidationError):
                    SetApprovalModeParams.model_validate(body)
                result = await rest_api.set_approval_mode_handler(request(body))
                self.assertEqual(result.status_code, 400 if isinstance(body, list) else 422)
                execute.assert_not_awaited()
        with patch.object(mcp_handler, "_execute_1c_command", new_callable=AsyncMock) as execute:
            self.assertFalse((await mcp_handler.set_approval_mode(None, "always"))["success"])
            execute.assert_not_awaited()

    async def test_tool_is_discoverable_with_exact_mode_enum(self):
        tools = await mcp_handler.mcp.list_tools()
        schema = next(tool.inputSchema for tool in tools if tool.name == "set_approval_mode")
        self.assertEqual(schema["properties"]["mode"]["enum"], ["deny", "ask", "session_allow"])
        self.assertEqual(schema["required"], ["mode"])
        self.assertFalse(schema["additionalProperties"])

    async def test_sdk_rejects_extra_arguments_before_dispatch(self):
        with patch.object(mcp_handler, "_execute_1c_command", new_callable=AsyncMock) as execute:
            with self.assertRaises(ToolError):
                await mcp_handler.mcp.call_tool("set_approval_mode", {"mode": "ask", "persist": True})
            execute.assert_not_awaited()
