
import base64
import json
import unittest

from onec_mcp_toolkit_proxy.consumer_registry import Consumer, ConsumerRegistry
from onec_mcp_toolkit_proxy.runtime_diagnostics import (
    add_execution_diagnostics, decode_connection_details, normalize_execution_result,
)


class RuntimeDiagnosticsTests(unittest.TestCase):
    def test_optional_diagnostics_preserve_error_text(self):
        description = "Документ 000012; код справочника K-017; МодульДоступа"
        scope = {"context": '{"execution_context":"client"}'}
        result = {
            "success": False, "error": description, "execution_error": "application_error",
            "error_location": {"category": "script_use_error", "line": 2},
        }
        off = {"status": "failed", "result": result, "error": None}
        add_execution_diagnostics(off, scope, False)
        self.assertNotIn("diagnostics", off)
        self.assertEqual(off["result"], {"success": False, "error": description})
        on = {"status": "failed", "result": result, "error": None}
        add_execution_diagnostics(on, scope, True)
        self.assertEqual(on["result"], off["result"])
        self.assertEqual(on["diagnostics"]["code"], "application_error")
        self.assertEqual(on["diagnostics"]["source"], "1c_runtime")
        self.assertEqual(on["diagnostics"]["execution_context"], "client")
        self.assertEqual(on["diagnostics"]["error_location"], {"category": "script_use_error", "line": 2})

    def test_old_free_form_error_does_not_imply_permission_denial(self):
        result = {"success": False, "error": "МодульДоступа: закрыт период"}
        snapshot = {"status": "failed", "error": None, "result": result}
        add_execution_diagnostics(snapshot, {"context": None}, True)
        self.assertEqual(snapshot["result"], result)
        self.assertEqual(snapshot["diagnostics"]["code"], "execution_error_unclassified")
        self.assertIsNone(snapshot["diagnostics"]["source"])

    def test_same_error_text_keeps_distinct_sources_and_separate_permission(self):
        description = "Вывод запрещен"
        cases = (
            ("application_error", "application_exception", "1c_application", None),
            ("platform_runtime_error", "script_use_error", "1c_runtime", False),
            ("platform_runtime_error", "script_use_error", "1c_runtime", True),
        )
        for code, category, source, output_permission in cases:
            with self.subTest(code=code, output_permission=output_permission):
                result = {
                    "success": False, "error": description, "execution_error": code,
                    "error_location": {"category": category}, "output_permission": output_permission,
                }
                for enabled in (True, False):
                    snapshot = {"status": "failed", "result": result, "error": None}
                    add_execution_diagnostics(snapshot, {"context": None}, enabled)
                    self.assertEqual(snapshot["result"], {"success": False, "error": description})
                    if enabled:
                        self.assertEqual(snapshot["diagnostics"]["code"], code)
                        self.assertEqual(snapshot["diagnostics"]["source"], source)
                        expected = None if output_permission is None else {"output": output_permission}
                        self.assertEqual(snapshot["diagnostics"].get("permissions"), expected)
                    else:
                        self.assertNotIn("diagnostics", snapshot)

    def test_output_permission_requires_a_boolean_observation(self):
        result = normalize_execution_result({"success": False, "output_permission": "false"})
        self.assertNotIn("output_permission", result)

    def test_execution_time_is_only_in_enabled_diagnostics(self):
        cases = (
            ("succeeded", {"success": True, "data": 42, "error": None}, 0),
            ("failed", {"success": False, "error": "Прикладная ошибка 1С"}, 153),
        )
        for status, result, elapsed in cases:
            for enabled in (True, False):
                with self.subTest(status=status, enabled=enabled):
                    snapshot = {"status": status, "error": None, "result": {**result, "execution_ms": elapsed}}
                    add_execution_diagnostics(snapshot, {"context": None}, enabled)
                    self.assertEqual(snapshot["result"], result)
                    if enabled:
                        self.assertEqual(snapshot["diagnostics"]["execution_ms"], elapsed)
                    else:
                        self.assertNotIn("diagnostics", snapshot)

    def test_execution_time_requires_a_valid_final_measurement(self):
        cases = (
            ("running", None),
            ("unknown", {"success": False, "execution_ms": 150}),
            ("rejected", {"success": False, "execution_ms": 0}),
            ("failed", {"success": False, "error": "старый ответ"}),
            ("succeeded", {"success": True, "execution_ms": -5}),
            ("succeeded", {"success": True, "execution_ms": True}),
            ("failed", {"success": False, "execution_ms": "120"}),
        )
        for status, result in cases:
            with self.subTest(status=status, result=result):
                snapshot = {"status": status, "error": None, "result": result}
                add_execution_diagnostics(snapshot, {"context": None}, True)
                self.assertNotIn("execution_ms", snapshot["diagnostics"])
                self.assertNotIn("execution_ms", snapshot["result"] or {})

    def test_error_trace_is_additive_and_respects_the_diagnostics_flag(self):
        original = {"success": False, "error": "Записать: Ошибка обработчика проведения"}
        trace = {
            "error_chain": [
                {"description": "Ошибка обработчика проведения", "categories": ["other_error"]},
                {"description": "Причина", "module": "ОбщийМодуль.Подписка.Модуль", "line": 8,
                 "categories": ["application_exception"]},
            ],
            "stack": [{"module": "", "line": 1, "source": "Провести();"}],
            "hidden_toolkit_frames": 4,
        }
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                snapshot = {"status": "failed", "error": None, "result": {**original, **trace}}
                add_execution_diagnostics(snapshot, {"context": None}, enabled)
                self.assertEqual(snapshot["result"], original)
                if enabled:
                    self.assertEqual({key: snapshot["diagnostics"][key] for key in trace}, trace)
                else:
                    self.assertNotIn("diagnostics", snapshot)

    def test_typed_connection_error_retains_unknown_outcome(self):
        result = normalize_execution_result({"success": False, "execution_error": "connection_lost"})
        self.assertEqual(result["lifecycle_outcome"], "unknown")
        self.assertEqual(result["execution_error"], "connection_lost")

    def test_returns_field_name_only_when_it_is_an_identifier(self):
        location = {"category": "script_use_error", "reason": "read_only_field", "member": "Параметры"}
        failure = {"success": False, "error_location": location, "execution_error": "application_error"}
        self.assertEqual(normalize_execution_result(failure)["error_location"], location)
        location["member"] = "Pwd=SECRET"
        self.assertEqual(normalize_execution_result(failure)["error_location"], {"category": "script_use_error"})

    def test_rejection_and_success_keep_existing_response(self):
        rejected = {"success": False, "rejection_reason": "mode_deny", "error": "Operation denied"}
        self.assertEqual(normalize_execution_result(rejected), rejected)
        self.assertEqual(normalize_execution_result({"success": True, "data": 1}), {
            "success": True, "data": 1, "error": None,
        })

    def test_connection_observation_ignores_raw_connection_string(self):
        observation = {"enabled": True, "base": 'File="C:/Base";Pwd=SECRET;',
                       "platform_version": "8.5.1.1529", "approval_mode": "ask", "password": "SECRET"}
        header = base64.b64encode(json.dumps(observation).encode()).decode()
        self.assertEqual(decode_connection_details(header), {"enabled": True, "connection": {
            "base": None, "platform_version": "8.5.1.1529", "approval_mode": "ask", "mode": "proxy",
        }})
        off = base64.b64encode(b'{"enabled":false}').decode()
        self.assertEqual(decode_connection_details(off), {"enabled": False, "connection": None})
        self.assertIsNone(decode_connection_details("broken input"))

    def test_status_cannot_refresh_an_old_connection_observation(self):
        registry = ConsumerRegistry()
        owner = Consumer("test", "legacy", connection_details={"enabled": True, "connection": {"base": "fixture"}})
        registry.consumers["test"] = owner
        registry.record_activity(owner)
        owner.connection_observed_at = owner.last_seen_monotonic
        observed = owner.last_seen_monotonic
        self.assertEqual(registry.connection_status("test", observed + 1)["readiness"], "ready")
        stale = registry.connection_status("test", observed + 61)
        self.assertEqual(stale["readiness"], "disconnected")
        self.assertIsNotNone(stale["last_seen_at"])
        self.assertIsNone(stale["connection"])
        self.assertEqual(registry.connection_status("other", observed + 61)["readiness"], "unknown")
