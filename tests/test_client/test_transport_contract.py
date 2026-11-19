"""Contract and real ASGI routing checks; no UI-execution acceptance implied."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from jsonschema import Draft202012Validator

from onec_mcp_toolkit_proxy.test_client_contract import INPUT_SCHEMAS, valid_request
from onec_mcp_toolkit_proxy.mcp_handler import _execute_1c_command
from onec_mcp_toolkit_proxy.server import app
from onec_mcp_toolkit_proxy.consumer_registry import Consumer, consumer_registry
from onec_mcp_toolkit_proxy.operation_journal import OperationError


def examples():
    common = {"request_id": "req-1", "session_id": "s-1", "window": {"id": "w-1"}, "params": {}}
    return {
        "test_session": {"request_id": "req-1", "action": "status", "params": {"operation_id": "op-1"}},
        "test_open": {**common, "params": {"link": "e1cib/list/Catalog.Items"}},
        "test_inspect": {**common, "action": "tree"},
        "test_input": {**common, "action": "check", "element": {"id": "e-1"}, "params": {"checked": True}},
        "test_action": {**common, "action": "click", "element": {"id": "e-1"}},
        "test_table": {**common, "action": "add", "element": {"id": "e-1"}},
        "test_expect": {**common, "params": {"condition": {"property": "closed", "operator": "equals", "value": False}}},
    }


class ContractTests(unittest.TestCase):
    def test_all_actions_have_usable_request_shapes(self):
        common = {"request_id": "r", "session_id": "s", "window": {"active": True}, "element": {"id": "e"}, "params": {}}
        cases = {
            "test_session": [("start", {"profile_id": "p"}), ("attach", {"profile_id": "p"}),
                             ("status", {}), ("detach", {}), ("stop", {})],
            "test_inspect": [("windows", {}), ("tree", {}), ("values", {"targets": [{"id": "e"}]}), ("messages", {})],
            "test_input": [("text", {"text": ""}), ("check", {"checked": False}), ("select", {"choice": {"list_value": "v"}})],
            "test_action": [(a, {}) for a in ("click", "activate_window", "select_page", "close")],
            "test_table": [("read", {}), ("find", {"row": {"where": [{"column": "Name", "equals": ""}]}}),
                           ("select", {"row": {"id": "r", "snapshot_id": "snap"}}), ("add", {}),
                           ("fill", {"row": {"id": "r", "snapshot_id": "snap"}, "values": [{"column": "Name", "text": ""}]}),
                           ("delete", {"row": {"id": "r", "snapshot_id": "snap"}})],
        }
        for tool, actions in cases.items():
            for action, params in actions:
                request = {**common, "action": action, "params": params}
                if tool == "test_session":
                    request.pop("window"); request.pop("element")
                    if action in ("start", "attach"):
                        request.pop("session_id")
                if tool == "test_inspect":
                    request.pop("element")
                    if action == "windows":
                        request.pop("window")
                if tool == "test_action" and action in ("activate_window", "close"):
                    request.pop("element")
                with self.subTest(tool=tool, action=action):
                    self.assertTrue(valid_request(tool, request))

    def test_seven_schemas_and_examples(self):
        self.assertEqual(len(INPUT_SCHEMAS), 7)
        for tool, schema in INPUT_SCHEMAS.items():
            with self.subTest(tool=tool):
                Draft202012Validator.check_schema(schema)
                self.assertTrue(valid_request(tool, examples()[tool]))

    def test_select_opens_picker_from_explicit_table_row(self):
        request = {**examples()["test_input"], "action": "select"}
        choice = {
            "selection_window": {"selector": {"form_name": "Catalog.Items.Form.Choice"}},
            "table": {"selector": {"name": "List"}},
            "row": {"where": [{"column": "Code", "equals": "001"}]},
            "source_row": {"where": [{"column": "LineNumber", "equals": "1"}]},
            "expected_text": "Item",
        }
        self.assertTrue(valid_request("test_input", {**request, "params": {"choice": choice}}))
        for field, invalid in {
            "source_row": {"id": "r", "snapshot_id": "snap"},
            "selection_window": {"active": True},
            "table": {"id": "t"},
            "expected_text": "",
        }.items():
            with self.subTest(field=field):
                params = {"choice": {**choice, field: invalid}}
                self.assertFalse(valid_request("test_input", {**request, "params": params}))

    def test_closed_contract(self):
        for tool, example in examples().items():
            for key, value in [("request_id", ""), ("request_id", None), ("timeout_ms", -1),
                               ("timeout_ms", True), ("timeout_ms", 300001), ("channel", "other"),
                               ("params", None), ("params", {"arbitrary_bsl": "secret"})]:
                with self.subTest(tool=tool, key=key, value=value):
                    self.assertFalse(valid_request(tool, {**example, key: value}))
        request = examples()["test_input"]
        self.assertFalse(valid_request("test_input", {**request, "params": {"checked": "true"}}))
        self.assertFalse(valid_request("test_input", {**request, "window": {"id": "w", "active": True}}))
        self.assertFalse(valid_request("test_input", {**request, "element": {"selector": {}}}))
        request = examples()["test_table"]
        cells = [{"column": "Name", "text": "same"}] * 2
        self.assertFalse(valid_request("test_table", {**request, "params": {"values": cells}}))
        row = {"where": [{"column": "Name", "equals": "same"}] * 2}
        self.assertFalse(valid_request("test_table", {**request, "action": "select", "params": {"row": row}}))


class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_rest_routes_refuse_without_common_store_for_every_consumer_mode(self):
        channel = "task062-test"
        old = consumer_registry.consumers.get(channel)
        try:
            with patch("onec_mcp_toolkit_proxy.mcp_handler._execute_bound_1c_command", new_callable=AsyncMock) as dispatch, \
                    patch("onec_mcp_toolkit_proxy.test_client_operations.channel_command_queue.operation_store",
                          side_effect=OperationError('operation_store_not_configured')):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
                    for mode in ("http", "file", "server_host"):
                        consumer_registry.consumers[channel] = Consumer(channel, mode)
                        for tool, arguments in examples().items():
                            with self.subTest(mode=mode, tool=tool):
                                response = await client.post("/api/" + tool + "?channel=" + channel, json=arguments)
                                self.assertEqual(response.status_code, 200)
                                expected = response.json()
                                self.assertEqual(expected['error']['code'], 'operation_store_not_configured')
                                self.assertIsNone(expected['operation_id'])
                                self.assertEqual(expected['contract_version'], '1')
                                self.assertEqual(await _execute_1c_command(tool, arguments, channel), expected)
                    dispatch.assert_not_awaited()
                    bad = await client.post("/api/test_input", json={"params": {"password": "DO_NOT_ECHO"}})
                    self.assertEqual("invalid_params", bad.json()["error"]['code'])
                    self.assertNotIn("DO_NOT_ECHO", bad.text)
                    self.assertEqual((await client.post("/api/test_session", content="{")).status_code, 415)
                    self.assertEqual((await client.post("/api/test_session", content="{", headers={"Content-Type": "application/json"})).status_code, 400)
        finally:
            if old is None:
                consumer_registry.consumers.pop(channel, None)
            else:
                consumer_registry.consumers[channel] = old

    async def test_status_does_not_wait_for_consumer_or_long_command(self):
        with patch.object(consumer_registry, "wait", new_callable=AsyncMock) as wait:
            result = await asyncio.wait_for(_execute_1c_command("test_session", examples()["test_session"], "no-consumer"), 0.2)
            self.assertEqual("operation_store_not_configured", result["error"]['code'])
            wait.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
