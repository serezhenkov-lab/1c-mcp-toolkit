"""Public diagnostics for durable execution and channel observations."""
import base64
import json
import re


EXECUTION_ERRORS = frozenset(
    {"application_error", "platform_runtime_error", "permission_denied", "connection_lost", "toolkit_denied"}
)
PLATFORM_CATEGORIES = frozenset({
    "access_violation", "network_error", "session_error", "script_compile_error",
    "script_use_error", "script_runtime_error", "application_exception", "other_error",
})
ERROR_TRACE_FIELDS = ("error_chain", "stack", "hidden_toolkit_frames")


def pop_execution_ms(result):
    value = result.pop("execution_ms", None)
    if type(value) is int and value >= 0:
        return value
    return None


def pop_error_trace(result):
    trace = {}
    for field in ("error_chain", "stack"):
        rows = result.pop(field, None)
        if isinstance(rows, list) and rows and all(isinstance(row, dict) for row in rows):
            trace[field] = rows
    hidden = result.pop("hidden_toolkit_frames", None)
    if "stack" in trace and type(hidden) is int and hidden >= 0:
        trace["hidden_toolkit_frames"] = hidden
    return trace


def apply_error_trace_policy(diagnostics, anonymizer, tool):
    trace = {key: diagnostics[key] for key in ERROR_TRACE_FIELDS if key in diagnostics}
    if trace:
        diagnostics.update(anonymizer.anonymize_response({"error": trace}, tool_name=tool)["error"])


def normalize_execution_result(result):
    """Preserve the existing result and validate the additional diagnostic fields."""
    public = dict(result)
    execution_ms = pop_execution_ms(public)
    if execution_ms is not None:
        public["execution_ms"] = execution_ms
    trace = pop_error_trace(public)
    if result.get("success") is True:
        public["error"] = None
        return public
    public.update(trace)
    error = result.get("execution_error")
    public.pop("execution_error", None)
    if isinstance(error, str) and error in EXECUTION_ERRORS:
        public["execution_error"] = error
    if type(public.get("output_permission")) is not bool:
        public.pop("output_permission", None)
    location = public.pop("error_location", None)
    if isinstance(location, dict) and isinstance(location.get("category"), str) and location["category"] in PLATFORM_CATEGORIES:
        public["error_location"] = {"category": location["category"]}
        line = location.get("line")
        if type(line) is int and 0 < line <= 1000000:
            public["error_location"]["line"] = line
        module = location.get("module")
        if isinstance(module, str) and re.fullmatch(r"(?:ОбщийМодуль|Обработка|ВнешняяОбработка|Документ|Справочник)(?:\.[\w]{1,80}){1,6}", module):
            public["error_location"]["module"] = module
        reason, member = location.get("reason"), location.get("member")
        if (location["category"] == "script_use_error" and reason in ("read_only_field", "missing_field")
                and isinstance(member, str) and re.fullmatch(r"[^\W\d]\w{0,79}", member)):
            public["error_location"].update(reason=reason, member=member)
    if result.get("lifecycle_outcome") == "unknown" or error == "connection_lost":
        public["lifecycle_outcome"] = "unknown"
    return public


def execution_diagnostics(status, context=None, error=None):
    if status == "rejected" or error in ("mode_deny", "user_declined", "approval_stale", "toolkit_denied"):
        source = "toolkit_policy"
    elif error == "permission_denied":
        source = "1c_permissions"
    elif error == "application_error":
        source = "1c_application"
    elif error == "platform_runtime_error":
        source = "1c_runtime"
    elif error == "connection_lost":
        source = "connection"
    else:
        source = None
    return {
        "stage": status,
        "code": error,
        "execution_context": context,
        "source": source,
        "messages_status": "unavailable",
        "messages_reason": "call_buffer_not_isolated",
    }


def add_execution_diagnostics(snapshot, row, enabled):
    context = json.loads(row["context"] or "{}")
    result = snapshot["result"]
    code, location, output_permission = snapshot["error"], None, None
    execution_ms = None
    trace = {}
    if result is not None:
        result = normalize_execution_result(result)
        execution_ms = result.pop("execution_ms", None)
        trace = pop_error_trace(result)
        if not result.get("success"):
            location = result.pop("error_location", None)
            execution_error = result.pop("execution_error", None)
            output_permission = result.pop("output_permission", None)
            code = code or result.get("rejection_reason") or execution_error or "execution_error_unclassified"
        snapshot["result"] = result
    if not enabled:
        return
    snapshot["diagnostics"] = execution_diagnostics(snapshot["status"], context.get("execution_context"), code)
    snapshot["diagnostics"].update(trace)
    if execution_ms is not None and snapshot["status"] in ("succeeded", "failed"):
        snapshot["diagnostics"]["execution_ms"] = execution_ms
    if context.get("connection") is not None:
        snapshot["diagnostics"]["connection"] = context["connection"]
    if output_permission is not None:
        snapshot["diagnostics"]["permissions"] = {"output": output_permission}
    if location is not None:
        snapshot["diagnostics"]["error_location"] = location
        if code == "application_error" and location["category"] != "application_exception":
            snapshot["diagnostics"]["source"] = "1c_runtime"


def decode_connection_details(header):
    """Accept only the fields of the executor's current connection observation."""
    try:
        fields = json.loads(base64.b64decode(header, validate=True))
    except (ValueError, UnicodeError):
        return None
    if not isinstance(fields, dict) or type(fields.get("enabled")) is not bool:
        return None
    if not fields["enabled"]:
        return {"enabled": False, "connection": None}
    base, version, approval = (fields.get(key) for key in ("base", "platform_version", "approval_mode"))
    if not isinstance(version, str) or not re.fullmatch(r"\d{1,4}(?:\.\d{1,6}){2,3}", version):
        return None
    if approval not in ("deny", "ask", "session_allow"):
        return None
    if not isinstance(base, str) or not re.fullmatch(r"[\w .()\-]{1,120}", base):
        base = None
    return {"enabled": True, "connection": {
        "base": base, "platform_version": version, "approval_mode": approval, "mode": "proxy",
    }}
