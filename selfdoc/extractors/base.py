"""Shared utilities for language extractors.

Contains functions that were duplicated across python.py, go.py, and
typescript.py: JSON value helpers, TOML flattening, config file readers,
source file reading, and error formatting.

Also provides BaseExtractor with default implementations of optional
LanguageExtractor methods.
"""

import json

from selfdoc.tables import render_markdown_table


def format_error(message):
    """Format a selfdoc error message for display in markdown output."""
    return f"> *[selfdoc: {message}]*"


def parse_comma_set(value: str) -> set[str]:
    """Split a comma-separated string into a set of stripped, non-empty parts."""
    return {part.strip() for part in value.split(",") if part.strip()}


def apply_exclude_keys(
    data: dict, exclude_keys: set[str] | None, display_path: str
) -> dict | str:
    """Filter out excluded keys from a dict.

    Returns the filtered dict, or a format_error string if any key
    in exclude_keys is not present in data.
    """
    if not exclude_keys:
        return data
    for key in exclude_keys:
        if key not in data:
            return format_error(
                f"exclude key '{key}' not found in '{display_path}'"
            )
    return {k: v for k, v in data.items() if k not in exclude_keys}


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


def _config_from_json(full_path, display_path, exclude_keys: set[str] | None = None):
    """Parse JSON config and render as a key-value table."""
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return format_error(f"cannot parse '{display_path}': {exc}")

    if not isinstance(data, dict):
        return f"```json\n{json.dumps(data, indent=2)}\n```"

    result = apply_exclude_keys(data, exclude_keys, display_path)
    if isinstance(result, str):
        return result
    data = result

    rows = []
    for key, value in data.items():
        type_name = _json_type_name(value)
        value_repr = _json_value_repr(value)
        rows.append([f"`{key}`", type_name, value_repr])

    return render_markdown_table(["Key", "Type", "Value"], rows)


class BaseExtractor:
    """Base class for language extractors.

    Provides default implementations for optional LanguageExtractor
    methods. Subclasses must implement name, detect, and extract.
    """

    def file_extensions(self) -> list[str]:
        return []

    def public_symbols(self, file_path: str) -> list[str]:
        return []

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None:
        return None


class StubExtractor(BaseExtractor):
    """Stub extractor for unsupported languages.

    Returns empty results for discovery methods and an error marker
    for extraction. Allows the pipeline to proceed without raising
    ValueError for unknown languages -- the LANG001 lint catches
    these at check time instead.
    """

    def __init__(self, language: str) -> None:
        self._language = language

    @property
    def name(self) -> str:
        return self._language

    def detect(self, dir_path: str) -> bool:
        return False

    def extract(
        self,
        directive_name: str,
        attrs: dict[str, str],
        body: list[str],
        source_paths: list[str],
        base_dir: str,
    ) -> str:
        return format_error(f"no extractor for '{self._language}'")


def _config_from_toml(full_path, display_path, exclude_keys: set[str] | None = None):
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

    result = apply_exclude_keys(data, exclude_keys, display_path)
    if isinstance(result, str):
        return result
    data = result

    rows = []
    rows.append("| Key | Type | Value |")
    rows.append("| --- | --- | --- |")

    _flatten_toml(data, "", rows)

    return "\n".join(rows)
