"""Data-only policy for test-client v1; never enables command execution."""

TEST_CLIENT_TOOLS = frozenset({"test_session", "test_open", "test_inspect", "test_input",
                               "test_action", "test_table", "test_expect"})
TECHNICAL_KEYS = frozenset({"request_id", "operation_id", "session_id", "window_id", "element_id",
                          "row_id", "snapshot_id", "cursor", "next_cursor", "contract_version",
                          "execution", "verification", "status", "observed_at", "expires_at"})
SECRET_KEYS = frozenset({"password", "pwd", "пароль", "connection", "connection_string",
                       "строкасоединения", "authorization", "access_token", "refresh_token"})


def transform_response(value, transform, key="", include_errors=True, in_error=False):
    """Preserve protocol scalars, not arbitrary subtrees or generic business 'id'."""
    if key.lower() in SECRET_KEYS:
        return "[REDACTED]"
    in_error = in_error or key == "error"
    if isinstance(value, dict):
        return {k: transform_response(v, transform, k, include_errors, in_error)
                for k, v in value.items()}
    if isinstance(value, list):
        return [transform_response(v, transform, key, include_errors, in_error) for v in value]
    if isinstance(value, str):
        if key in TECHNICAL_KEYS or not include_errors and in_error:
            return value
        return transform(value, key)
    return value


def detokenize_request(value, detokenize, key="", parent=""):
    """Only user-text slots are restored; IDs, metadata and protocol stay literal."""
    if isinstance(value, dict):
        return {k: detokenize_request(v, detokenize, k, key) for k, v in value.items()}
    if isinstance(value, list):
        return [detokenize_request(v, detokenize, key, parent) for v in value]
    if isinstance(value, str) and (key in {"text", "title", "equals", "list_value"}
                                   or key == "value" and parent == "condition"):
        return detokenize(value)
    return value
