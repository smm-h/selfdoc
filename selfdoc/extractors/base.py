"""Shared utilities for language extractors.

Contains functions that were duplicated across python.py, go.py, and
typescript.py: JSON value helpers, TOML flattening, config file readers,
source file reading, and error formatting.
"""

import json


def format_error(message):
    """Format a selfdoc error message for display in markdown output."""
    return f"> *[selfdoc: {message}]*"


def read_source(filepath):
    """Read a source file and return its contents.

    Returns:
        (content, None) on success, or (None, error_string) on failure.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read(), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, str(exc)


def _json_type_name(value):
    """Get a human-readable type name for a JSON value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _json_value_repr(value):
    """Get a compact representation of a JSON value for table display."""
    if value is None:
        return "`null`"
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    if isinstance(value, str):
        if len(value) > 40:
            return f'`"{value[:37]}..."`'
        return f'`"{value}"`'
    if isinstance(value, (int, float)):
        return f"`{value}`"
    if isinstance(value, list):
        if len(value) == 0:
            return "`[]`"
        return f"`[...] ({len(value)} items)`"
    if isinstance(value, dict):
        if len(value) == 0:
            return "`{}`"
        return f"`{{...}} ({len(value)} keys)`"
    return f"`{value}`"


def _flatten_toml(data, prefix, rows):
    """Recursively flatten TOML data into table rows."""
    for key, value in data.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            _flatten_toml(value, full_key, rows)
        else:
            type_name = _json_type_name(value)
            value_repr = _json_value_repr(value)
            rows.append(f"| `{full_key}` | {type_name} | {value_repr} |")


def _config_from_json(full_path, display_path):
    """Parse JSON config and render as a key-value table."""
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return format_error(f"cannot parse '{display_path}': {exc}")

    if not isinstance(data, dict):
        return f"```json\n{json.dumps(data, indent=2)}\n```"

    rows = []
    rows.append("| Key | Type | Value |")
    rows.append("| --- | --- | --- |")

    for key, value in data.items():
        type_name = _json_type_name(value)
        value_repr = _json_value_repr(value)
        rows.append(f"| `{key}` | {type_name} | {value_repr} |")

    return "\n".join(rows)


def _config_from_toml(full_path, display_path):
    """Parse TOML config and render as a key-value table."""
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return format_error(
                "TOML support requires Python 3.11+ "
                "or the 'tomli' package"
            )

    try:
        with open(full_path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, Exception) as exc:
        return format_error(f"cannot parse '{display_path}': {exc}")

    rows = []
    rows.append("| Key | Type | Value |")
    rows.append("| --- | --- | --- |")

    _flatten_toml(data, "", rows)

    return "\n".join(rows)
