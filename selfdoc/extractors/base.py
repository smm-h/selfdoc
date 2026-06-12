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
    """Recursively flatten TOML data into row data lists."""
    for key, value in data.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            _flatten_toml(value, full_key, rows)
        else:
            type_name = _json_type_name(value)
            value_repr = _json_value_repr(value)
            rows.append([f"`{full_key}`", type_name, value_repr])


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
    _flatten_toml(data, "", rows)

    return render_markdown_table(["Key", "Type", "Value"], rows)


# Section headers recognized in Google-style docstrings
_SECTION_HEADERS = {
    "Args",
    "Arguments",
    "Returns",
    "Return",
    "Raises",
    "Yields",
    "Yield",
    "Attributes",
    "Note",
    "Notes",
    "Example",
    "Examples",
    "References",
    "See Also",
    "Todo",
    "Keyword Args",
    "Keyword Arguments",
}


def _format_docstring(docstring):
    """Transform Google-style docstring sections into markdown.

    Detects section headers like ``Args:``, ``Returns:``, ``Raises:``
    followed by indented ``name: description`` lines and converts them
    to bold headers with bullet lists so the markdown converter renders
    them as structured HTML instead of collapsing whitespace.
    """
    lines = docstring.split("\n")
    out = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check for a section header: "Args:", "Returns:", etc.
        header_name = _match_section_header(stripped)
        if header_name is not None:
            # Emit a blank line before the header for markdown spacing
            if out and out[-1] != "":
                out.append("")
            out.append(f"**{header_name}:**")
            out.append("")
            i += 1

            # Collect indented lines under this header as list items
            # Determine the indent of the first content line
            if i < len(lines):
                first_content = lines[i]
                base_indent = len(first_content) - len(first_content.lstrip())
            else:
                base_indent = 4

            while i < len(lines):
                content_line = lines[i]

                # Empty line: might separate items or end the section
                if not content_line.strip():
                    # Peek ahead: if next non-empty line is still indented,
                    # this is a blank line within the section
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines):
                        next_indent = len(lines[j]) - len(lines[j].lstrip())
                        if next_indent >= base_indent:
                            # Still in the section -- preserve the blank line
                            out.append("")
                            i += 1
                            continue
                    # End of section
                    break

                current_indent = len(content_line) - len(content_line.lstrip())
                if current_indent < base_indent:
                    # No longer indented -- end of section
                    break

                text = content_line.strip()

                # Check if this is a new item (name: description) at the
                # base indent level, or a continuation line (deeper indent)
                if current_indent == base_indent and _is_param_line(text):
                    # New list item: "param_name: description" or
                    # "param_name (type): description"
                    name, desc = _split_param_line(text)
                    out.append(f"- `{name}`: {desc}" if desc else f"- `{name}`")
                elif current_indent == base_indent and not _is_param_line(text):
                    # A plain line at base indent (e.g. Returns section
                    # with just a description, no param name)
                    out.append(f"- {text}")
                else:
                    # Continuation of a previous item (deeper indent)
                    out.append(f"  {text}")

                i += 1
            continue

        # Regular line -- pass through
        out.append(line)
        i += 1

    return "\n".join(out)


def _match_section_header(stripped):
    """If ``stripped`` is a recognized section header like ``Args:``, return
    the header name. Otherwise return None."""
    if not stripped.endswith(":"):
        return None
    candidate = stripped[:-1].strip()
    if candidate in _SECTION_HEADERS:
        return candidate
    return None


def _is_param_line(text):
    """Check if a line looks like ``name: description`` or
    ``name (type): description``."""
    # Must have a colon that is not at the very start
    colon_idx = text.find(":")
    if colon_idx <= 0:
        return False
    # The part before the colon should look like an identifier, possibly
    # followed by a parenthesized type annotation
    before = text[:colon_idx].strip()
    # Strip optional (type) suffix
    if before.endswith(")"):
        paren_idx = before.rfind("(")
        if paren_idx > 0:
            before = before[:paren_idx].strip()
    # Should be a valid identifier-like name (allow dots, *, **)
    before = before.lstrip("*")
    return bool(before) and all(
        c.isalnum() or c in ("_", ".", "-") for c in before
    )


def _split_param_line(text):
    """Split ``name: description`` into (name, description).

    Also handles ``name (type): description``."""
    colon_idx = text.find(":")
    name = text[:colon_idx].strip()
    desc = text[colon_idx + 1 :].strip()
    return name, desc
