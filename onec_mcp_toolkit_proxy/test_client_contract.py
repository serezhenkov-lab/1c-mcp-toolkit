"""Test-client v1 input contract. Execution requires the shared lifecycle.

These schemas describe requests, not runtime capabilities. They must not be used
as evidence that a platform action or an operation-status registry is available.
"""
from jsonschema import Draft202012Validator


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


STRING = {"type": "string", "minLength": 1}
ID = {**STRING, "maxLength": 128}
TEXT = {"type": "string", "maxLength": 65536}
BOOL = {"type": "boolean"}
EMPTY = obj({})


def array(items, maximum=100):
    return {"type": "array", "items": items, "minItems": 1, "maxItems": maximum}


def selector(properties):
    return {**obj(properties, []), "minProperties": 1}


WINDOW = {"oneOf": [obj({"id": ID}), obj({"active": {"const": True, "type": "boolean"}}),
    obj({"selector": selector({"title": STRING, "form_name": STRING,
                               "navigation_link": STRING})})]}
ELEMENT = {"oneOf": [obj({"id": ID}), obj({"selector": selector({
    "name": STRING, "title": STRING,
    "scope": {"enum": ["form_tree", "command_interface", "command_bars"]},
    "type": {"enum": ["form", "group", "field", "button", "table", "decoration",
                       "command_interface", "command_group", "command_button"]},
    "path": {"type": "array", "items": STRING, "maxItems": 32}})})]}
FINISH_FOCUS = obj({'selector': obj({'name': {**STRING, 'maxLength': 256},
    'title': {**STRING, 'maxLength': 1024}, 'type': {'const': 'field'}}, ['name', 'type']),
    'same_form': {'const': True, 'type': 'boolean'}})
WHERE = array(obj({"column": STRING, "equals": TEXT}))
ROW = {"oneOf": [obj({"id": ID, "snapshot_id": ID}), obj({"where": WHERE})]}
CELL = {"oneOf": [obj({"column": STRING, "text": TEXT}), obj({"column": STRING, "checked": BOOL}),
                  obj({"column": STRING, "number": {"type": "number", "minimum": -999999999999999,
                                                    "maximum": 999999999999999}})]}
CHOICE = {"oneOf": [obj({"list_value": STRING}),
    obj({"selection_window": WINDOW, "table": ELEMENT, "row": ROW}),
    obj({"selection_window": WINDOW["oneOf"][2],
         "table": obj({"selector": obj({"name": STRING, "type": {"const": "table"}}, ["name"])}),
         "row": ROW["oneOf"][1], "source_row": ROW["oneOf"][1],
         "expected_text": {**STRING, "maxLength": 65536}})]}


def variant(action, params=EMPTY, *, session=True, window=False, element=False):
    properties = {"request_id": ID, "params": params,
                  "timeout_ms": {"type": "integer", "minimum": 0, "maximum": 300000}}
    required = ["request_id", "params"]
    if action is not None:
        properties["action"] = {"const": action}
        required.append("action")
    for name, mode, schema in [("session_id", session, ID), ("window", window, WINDOW), ("element", element, ELEMENT)]:
        if mode:
            properties[name] = schema
            if mode != "optional":
                required.append(name)
    return obj(properties, required)


INPUT_SCHEMAS = {
    "test_session": {"oneOf": [
        *(variant(a, obj({"profile_id": STRING}), session=False) for a in ("start", "attach")),
        variant("status", obj({"operation_id": ID}, []), session="optional"),
        *(variant(a) for a in ("detach", "stop"))]},
    "test_open": variant(None, obj({"link": {**STRING, "maxLength": 4096, "pattern": "^e1cib/"}}), window=True),
    "test_inspect": {"oneOf": [variant("windows"),
        *(variant(a, obj({"depth": {"type": "integer", "minimum": 0, "maximum": 32},
                              "max_nodes": {"type": "integer", "minimum": 1, "maximum": 5000}}, []), window=True, element="optional")
          for a in ("tree", "command_interface", "command_bars")),
        variant("values", obj({"targets": array(ELEMENT)}), window=True),
        variant("messages", window=True)]},
    "test_input": {"oneOf": [variant(a, obj({key: schema, **({"finish_focus": FINISH_FOCUS} if a == "text" else {})}, [key]), window=True, element=True)
        for a, key, schema in [("text", "text", TEXT),
                              ("number", "value", {"type": "number", "minimum": -999999999999999, "maximum": 999999999999999}),
                              ("date", "value", {"type": "string", "minLength": 10, "maxLength": 19,
                                                 "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}(T[0-9]{2}:[0-9]{2}:[0-9]{2})?$"}),
                              ("check", "checked", BOOL), ("select", "choice", CHOICE)]]},
    "test_action": {"oneOf": [variant(a, window=True, element=a in ("click", "select_page", "expand", "collapse"))
        for a in ("click", "activate_window", "select_page", "close", "expand", "collapse")]},
    "test_table": {"oneOf": [
        variant("read", obj({"limit": {"type": "integer", "minimum": 1, "maximum": 500},
                             "cursor": ID, "allow_navigation": BOOL}, []), window=True, element=True),
        variant("find", obj({"row": ROW, "allow_navigation": BOOL}, ["row"]), window=True, element=True),
        *(variant(a, obj({"row": ROW}), window=True, element=True) for a in ("select", "delete")),
        variant("add", obj({"values": array(CELL)}, []), window=True, element=True),
        variant("fill", obj({"row": ROW, "values": array(CELL)}), window=True, element=True)]},
    "test_expect": {"oneOf": [variant(None, obj({"condition": obj({
        "property": {"const": prop}, "operator": {"enum": ["equals", "not_equals"]}, "value": schema})}),
        window=True, element=element) for prop, schema, element in [
            ("exists", BOOL, "optional"), ("closed", BOOL, False), ("message", TEXT, False),
            ("title", TEXT, "optional"), ("row", obj({"where": WHERE}), True),
            ("value", TEXT, True), *((p, BOOL, True) for p in ("visible", "enabled", "read_only", "editing"))]]},
}
TEST_TOOLS = frozenset(INPUT_SCHEMAS)
TEST_TOOL_SCHEMAS = [{"name": name, "description": "Test-client v1. Durable request_id; poll test_session/status with params.operation_id. Requires a configured local manager profile.",
                      "inputSchema": {"type": "object", **schema}} for name, schema in INPUT_SCHEMAS.items()]
_VALIDATORS = {name: Draft202012Validator(schema) for name, schema in INPUT_SCHEMAS.items()}


def valid_request(tool, arguments):
    if tool not in _VALIDATORS or not _VALIDATORS[tool].is_valid(arguments):
        return False
    # JSON Schema uniqueItems cannot express uniqueness by column name.
    def unique_columns(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("where", "values") and isinstance(child, list):
                    columns = [item["column"] for item in child]
                    if len(columns) != len(set(columns)):
                        return False
                if not unique_columns(child):
                    return False
        elif isinstance(value, list):
            return all(unique_columns(child) for child in value)
        return True
    return unique_columns(arguments)


def unavailable_result(tool, arguments):
    """Pre-acceptance refusal: no queue entry, operation ID or observed UI state."""
    valid = valid_request(tool, arguments)
    return {"success": False, "error": (
        "client_context_unavailable: test_* transport adapter is not configured"
        if valid else "invalid_params: request does not match test-client v1")}
