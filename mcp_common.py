"""Platform-neutral MCP constants and schema validation; standard library only."""
import math
PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = {
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
}
def _contains_lone_surrogate(value) -> bool:
    """Return whether decoded JSON contains text that cannot be encoded as UTF-8.

    Standards-compliant MCP clients send UTF-8.  Some manual Windows shell pipelines can decode
    bytes with the wrong code page and leave lone surrogate characters in an otherwise valid JSON
    string. Reject that input at the protocol boundary before any platform operation.
    """
    if isinstance(value, str):
        return any(0xD800 <= ord(char) <= 0xDFFF for char in value)
    if isinstance(value, list):
        return any(_contains_lone_surrogate(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_lone_surrogate(key) or _contains_lone_surrogate(item)
                   for key, item in value.items())
    return False


def _validate_schema_value(value, schema: dict, path: str) -> str | None:
    """Validate the JSON Schema subset used by MCP tools, including nested unions."""
    if isinstance(value, float) and not math.isfinite(value):
        return f"{path} must be finite"
    branches = schema.get("anyOf")
    if branches is not None:
        errors = [_validate_schema_value(value, branch, path) for branch in branches]
        if any(error is None for error in errors):
            return None
        return f"{path} must match one of the allowed schema forms"

    expected = schema.get("type")
    type_checkers = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
        "null": lambda item: item is None,
    }
    checker = type_checkers.get(expected)
    if checker and not checker(value):
        return f"{path} must be {expected}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} must be one of: {', '.join(map(str, schema['enum']))}"

    if isinstance(value, str):
        text = value.strip() if "[" in path else value
        if len(text) < schema.get("minLength", 0):
            return f"{path} must not be empty"
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path} must be >= {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path} must be <= {schema['maximum']}"
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            return f"{path} must not be empty"
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return f"{path} must contain at most {schema['maxItems']} items"
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                error = _validate_schema_value(item, item_schema, f"{path}[{index}]")
                if error:
                    return error
    elif isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            return f"{path} missing required field(s): {', '.join(missing)}"
        unknown = sorted(set(value) - set(properties))
        if unknown and schema.get("additionalProperties") is False:
            return f"{path} has unknown field(s): {', '.join(unknown)}"
        for key, item in value.items():
            if key in properties:
                error = _validate_schema_value(item, properties[key], f"{path}.{key}")
                if error:
                    return error
    return None


def direction_schema(evidence_calls):
    """Provider-bound evidence names, platform-neutral qualitative vocabulary."""
    text = {"type": "string", "minLength": 1}
    evidence = {"anyOf": [{"type": "string"}, {
        "type": "object", "properties": {"basis": text,
            "call": {"type": "string", "enum": list(evidence_calls)}, "ref": text},
        "required": ["basis", "call", "ref"], "additionalProperties": False}]}
    tag = {"anyOf": [{"type": "string"}, {"type": "object", "properties": {
        "label": text, "axis": {"type": "string", "enum": ["sonic", "context"]},
        "emphasis": {"type": "string", "enum": ["soften", "neutral", "boost"]},
        "evidence": evidence}, "required": ["label"], "additionalProperties": False}]}
    change = {"anyOf": [{"type": "string"}, {"type": "object", "properties": {
        "op": {"type": "string", "enum": ["more", "less", "drop", "add"]},
        "label": text, "axis": {"type": "string", "enum": ["sonic", "context"]},
        "evidence": evidence}, "required": ["op", "label"], "additionalProperties": False}]}
    return {"type": "object", "properties": {
        "tags": {"type": "array", "items": tag, "minItems": 1, "maxItems": 8},
        "adjustments": {"type": "array", "items": change, "maxItems": 30},
        "language": {"type": "string"}, "brief": text},
        "required": ["tags", "brief"], "additionalProperties": False}
