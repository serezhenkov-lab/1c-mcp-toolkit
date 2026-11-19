"""Public contract for changing the existing Toolkit session approval mode."""

SET_APPROVAL_MODE_SCHEMA = {
    "name": "set_approval_mode",
    "description": (
        "Set dangerous-operation mode for the current Toolkit session: "
        "deny, ask, or session_allow. Shared by all clients of this session. "
        "session_allow resets on disconnect/restart and is never persisted. "
        "Does not grant 1C platform permissions or execute pending commands."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"mode": {"type": "string", "enum": ["deny", "ask", "session_allow"]}},
        "required": ["mode"],
        "additionalProperties": False,
    },
}
