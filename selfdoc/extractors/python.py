"""Python source extractor -- resolves directives by extracting from .py files.

Uses stdlib ast for parsing, no external dependencies. Handles:
- :::module  -- extract module docstrings, functions, classes
- :::test    -- extract test source code
- :::schema  -- extract dataclass fields or JSON schema
- :::cli     -- extract CLI help/usage info
- :::config  -- extract config file contents as tables
"""

import ast
import json
import os
import textwrap

from selfdoc.extractors.base import (
    BaseExtractor,
    _config_from_json,
    _config_from_toml,
    _json_type_name,
    _json_value_repr,
    format_error,
    read_source,
)


class PythonExtractor(BaseExtractor):
    """Python language extractor implementing LanguageExtractor protocol."""

    @property
    def name(self) -> str:
        return "python"

    def detect(self, dir_path: str) -> bool:
        return os.path.isfile(os.path.join(dir_path, "pyproject.toml")) or os.path.isfile(
            os.path.join(dir_path, "setup.py")
        )

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None:
        return _resolve_module_path(path_arg, source_paths, base_dir)

    def extract(
        self,
        directive_name: str,
        attrs: dict[str, str],
        body: list[str],
        source_paths: list[str],
        base_dir: str,
    ) -> str:
        # Reconstruct the old positional arg from attrs for backward compat
        path = attrs.get("path", "")
        target = attrs.get("target", "")
        arg = f"{path} {target}".strip() if target else path
        return resolve_python(directive_name, arg, body, source_paths, base_dir)

    def file_extensions(self) -> list[str]:
        return [".py"]

    def public_symbols(self, file_path: str) -> list[str]:
        """Extract public top-level functions and classes from a Python file.

        A public symbol is a top-level function or class whose name does
        not start with underscore.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            return []

        symbols = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    symbols.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    symbols.append(node.name)
        return symbols


def resolve_python(name, arg, body, source_paths, base_dir):
    """Dispatch a directive to the appropriate Python extraction handler.

    Backward-compat wrapper: accepts old directive names (module, test,
    schema, cli, config) and old positional arg string. New code should
    use PythonExtractor.extract() with attrs dict instead.

    Args:
        name: Directive name (old or new).
        arg: Directive argument (path, module name, etc.).
        body: Body lines of the directive block.
        source_paths: List of source directories from selfdoc.json.
        base_dir: Project root directory.

    Returns:
        Markdown string with the extracted content.
    """
    from selfdoc.catalog import DIRECTIVE_NAME_MAPPING

    # Remap old directive names to new canonical names
    name = DIRECTIVE_NAME_MAPPING.get(name, name)

    handlers = {
        "ref": _handle_module,
        "code-test": _handle_test,
        "table-schema": _handle_schema,
        "code-help": _handle_cli,
        "table-config": _handle_config,
    }
    handler = handlers.get(name)
    if handler is None:
        return format_error(f"unknown directive '{name}' for Python extractor")
    return handler(arg, body, source_paths, base_dir)


# ---------------------------------------------------------------------------
# :::module
# ---------------------------------------------------------------------------


def _handle_module(arg, body, source_paths, base_dir):
    """Extract module docstring, functions, and classes.

    Resolves dotted.path or file path to a .py file, parses with ast,
    and formats the result as markdown.
    """
    if not arg:
        return format_error(":::module requires a module path argument")

    filepath = _resolve_module_path(arg, source_paths, base_dir)
    if filepath is None:
        return format_error(f"module '{arg}' not found")

    source, err = read_source(filepath)
    if err:
        return format_error(f"cannot read '{arg}': {err}")

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as exc:
        return format_error(f"syntax error in '{arg}': {exc}")

    # Determine display name from the dotted path
    module_name = arg.replace("/", ".")
    if module_name.endswith(".py"):
        module_name = module_name[:-3]
    if module_name.endswith(".__init__"):
        module_name = module_name[: -len(".__init__")]

    parts = []
    parts.append(f"## {module_name}")

    module_doc = ast.get_docstring(tree)
    if module_doc:
        parts.append("")
        parts.append(_format_docstring(module_doc))

    # Extract top-level functions and classes
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            cls_md = _format_class(node)
            if cls_md:
                parts.append("")
                parts.append(cls_md)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_md = _format_function(node, heading_level=3)
            if func_md:
                parts.append("")
                parts.append(func_md)

    return "\n".join(parts)


def _resolve_module_path(arg, source_paths, base_dir):
    """Try to resolve a module argument to an actual .py file path.

    Tries: dotted-to-path conversion within each source path, then direct path.
    """
    # Try as dotted path: selfdoc.config -> selfdoc/config.py
    dotted_as_path = arg.replace(".", "/") + ".py"
    # Also try as package: selfdoc.config -> selfdoc/config/__init__.py
    dotted_as_pkg = arg.replace(".", "/") + "/__init__.py"

    candidates = []
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, dotted_as_path))
        candidates.append(os.path.join(base_dir, sp, dotted_as_pkg))
    # Try relative to base_dir directly
    candidates.append(os.path.join(base_dir, dotted_as_path))
    candidates.append(os.path.join(base_dir, dotted_as_pkg))

    # Try as a direct file path
    if arg.endswith(".py"):
        candidates.append(os.path.join(base_dir, arg))
        for sp in source_paths:
            candidates.append(os.path.join(base_dir, sp, arg))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return None


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


def _format_function(node, heading_level=2):
    """Format a function/method node as markdown.

    Skips private items (leading _) unless they have a docstring.
    """
    docstring = ast.get_docstring(node)

    # Skip private without docstrings
    if node.name.startswith("_") and not docstring:
        return None

    # Skip undocumented public items
    if not docstring and not node.name.startswith("_"):
        # Still show the signature for public items without docstrings
        pass

    sig = _build_signature(node)
    prefix = "#" * heading_level

    parts = []
    parts.append(f"{prefix} {node.name}")
    parts.append("")
    keyword = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    parts.append(f"```python\n{keyword} {node.name}{sig}\n```")

    if docstring:
        parts.append("")
        parts.append(_format_docstring(docstring))

    return "\n".join(parts)


def _format_class(node):
    """Format a class node as markdown, including its public methods."""
    docstring = ast.get_docstring(node)

    # Skip private classes without docstrings
    if node.name.startswith("_") and not docstring:
        return None

    methods = []
    for item in ast.iter_child_nodes(node):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_md = _format_function(item, heading_level=4)
            if method_md:
                methods.append(method_md)

    # Skip undocumented classes with no documented methods
    if not docstring and not methods:
        return None

    parts = []
    parts.append(f"### {node.name}")

    if docstring:
        parts.append("")
        parts.append(_format_docstring(docstring))

    for method_md in methods:
        parts.append("")
        parts.append(method_md)

    return "\n".join(parts)


def _build_signature(node):
    """Build a human-readable function signature string from ast.arguments."""
    args = node.args
    parts = []

    # Positional-only args
    posonlyargs = getattr(args, "posonlyargs", [])
    all_positional = posonlyargs + args.args

    # Defaults are right-aligned
    num_defaults = len(args.defaults)
    num_positional = len(all_positional)

    for i, arg in enumerate(all_positional):
        name = arg.arg
        annotation = _annotation_str(arg.annotation)
        part = f"{name}: {annotation}" if annotation else name

        default_idx = i - (num_positional - num_defaults)
        if default_idx >= 0:
            default = ast.unparse(args.defaults[default_idx])
            part += f"={default}"

        parts.append(part)

    # Insert / for positional-only
    if posonlyargs:
        parts.insert(len(posonlyargs), "/")

    # *args
    if args.vararg:
        annotation = _annotation_str(args.vararg.annotation)
        if annotation:
            parts.append(f"*{args.vararg.arg}: {annotation}")
        else:
            parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")

    # Keyword-only args
    for i, arg in enumerate(args.kwonlyargs):
        name = arg.arg
        annotation = _annotation_str(arg.annotation)
        part = f"{name}: {annotation}" if annotation else name

        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            default = ast.unparse(args.kw_defaults[i])
            part += f"={default}"

        parts.append(part)

    # **kwargs
    if args.kwarg:
        annotation = _annotation_str(args.kwarg.annotation)
        if annotation:
            parts.append(f"**{args.kwarg.arg}: {annotation}")
        else:
            parts.append(f"**{args.kwarg.arg}")

    # Return annotation
    ret = _annotation_str(node.returns)
    sig = f"({', '.join(parts)})"
    if ret:
        sig += f" -> {ret}"

    return sig


def _annotation_str(node):
    """Convert an annotation AST node to a string, or empty string if None."""
    if node is None:
        return ""
    return ast.unparse(node)


# ---------------------------------------------------------------------------
# :::test
# ---------------------------------------------------------------------------


def _handle_test(arg, body, source_paths, base_dir):
    """Extract test source code from a test file.

    arg format: <file_path> [TestClassName or test_function_name]
    """
    if not arg:
        return format_error(":::test requires a file path argument")

    parts = arg.split(None, 1)
    file_path = parts[0]
    target_name = parts[1] if len(parts) > 1 else None

    full_path = os.path.join(base_dir, file_path)
    if not os.path.isfile(full_path):
        return format_error(f"test file '{file_path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{file_path}': {err}")

    if target_name is None:
        # Show the whole file as a code block
        return f"```python\n{source.rstrip()}\n```"

    # Parse and find the target
    try:
        tree = ast.parse(source, filename=full_path)
    except SyntaxError as exc:
        return format_error(f"syntax error in '{file_path}': {exc}")

    source_lines = source.split("\n")

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == target_name:
                extracted = _extract_node_source(source_lines, node)
                return f"```python\n{extracted}\n```"
        elif isinstance(node, ast.ClassDef):
            if node.name == target_name:
                extracted = _extract_node_source(source_lines, node)
                return f"```python\n{extracted}\n```"

    return format_error(f"'{target_name}' not found in '{file_path}'")


def _extract_node_source(source_lines, node):
    """Extract source lines for an AST node, stripping common indent."""
    # end_lineno is inclusive, 1-based
    start = node.lineno - 1  # convert to 0-based
    end = node.end_lineno  # already exclusive when used as slice end
    lines = source_lines[start:end]
    return textwrap.dedent("\n".join(lines))


# ---------------------------------------------------------------------------
# :::schema
# ---------------------------------------------------------------------------


def _handle_schema(arg, body, source_paths, base_dir):
    """Extract schema information from JSON or Python dataclass.

    arg format:
      - path/to/file.json  -> render JSON keys as table
      - dotted.module ClassName -> extract dataclass fields
    """
    if not arg:
        return format_error(":::schema requires an argument")

    # Check if it's a JSON file
    parts = arg.split(None, 1)
    file_or_module = parts[0]

    if file_or_module.endswith(".json"):
        return _schema_from_json(file_or_module, base_dir)

    # Otherwise, treat as Python module + class name
    if len(parts) < 2:
        return format_error(
            ":::schema for Python requires 'module_path ClassName' format"
        )

    module_path = parts[0]
    class_name = parts[1]
    return _schema_from_dataclass(module_path, class_name, source_paths, base_dir)


def _schema_from_json(file_path, base_dir):
    """Render a JSON file as a documented table of keys, types, and values."""
    full_path = os.path.join(base_dir, file_path)
    if not os.path.isfile(full_path):
        return format_error(f"JSON file '{file_path}' not found")

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return format_error(f"cannot parse '{file_path}': {exc}")

    if not isinstance(data, dict):
        # Non-object JSON: just show as code block
        return f"```json\n{json.dumps(data, indent=2)}\n```"

    # Render as table
    rows = []
    rows.append("| Key | Type | Value |")
    rows.append("| --- | --- | --- |")

    for key, value in data.items():
        type_name = _json_type_name(value)
        value_repr = _json_value_repr(value)
        rows.append(f"| `{key}` | {type_name} | {value_repr} |")

    return "\n".join(rows)


def _schema_from_dataclass(module_path, class_name, source_paths, base_dir):
    """Extract dataclass/class fields with types and defaults from source."""
    filepath = _resolve_module_path(module_path, source_paths, base_dir)
    if filepath is None:
        return format_error(f"module '{module_path}' not found")

    source, err = read_source(filepath)
    if err:
        return format_error(f"cannot read '{module_path}': {err}")

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as exc:
        return format_error(f"syntax error in '{module_path}': {exc}")

    # Find the target class
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return _extract_class_fields(node, source)

    return format_error(f"class '{class_name}' not found in '{module_path}'")


def _extract_class_fields(class_node, source):
    """Extract fields from a class (dataclass or regular class with annotations).

    Produces a markdown table with Field, Type, Default, and Description columns.
    """
    source_lines = source.split("\n")
    rows = []
    rows.append("| Field | Type | Default | Description |")
    rows.append("| --- | --- | --- | --- |")

    found_fields = False

    for node in ast.iter_child_nodes(class_node):
        # Annotated assignments: field_name: Type = default
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            field_name = node.target.id
            if field_name.startswith("_"):
                continue

            type_str = ast.unparse(node.annotation) if node.annotation else ""
            default_str = ast.unparse(node.value) if node.value else ""

            # Try to get a description from an inline comment
            description = _get_inline_comment(source_lines, node.lineno)

            rows.append(
                f"| `{field_name}` | `{type_str}` | "
                f"{_format_default(default_str)} | {description} |"
            )
            found_fields = True

    if not found_fields:
        return format_error(f"no fields found in class '{class_node.name}'")

    return "\n".join(rows)


def _get_inline_comment(source_lines, lineno):
    """Extract an inline # comment from a source line (1-based lineno)."""
    if lineno < 1 or lineno > len(source_lines):
        return ""
    line = source_lines[lineno - 1]
    # Find a # comment that's not inside a string (simple heuristic)
    # Split on # that's not inside quotes
    in_string = False
    quote_char = None
    for i, ch in enumerate(line):
        if ch in ('"', "'") and (i == 0 or line[i - 1] != "\\"):
            if not in_string:
                in_string = True
                quote_char = ch
            elif ch == quote_char:
                in_string = False
        elif ch == "#" and not in_string:
            return line[i + 1 :].strip()
    return ""


def _format_default(default_str):
    """Format a default value for table display."""
    if not default_str:
        return ""
    return f"`{default_str}`"


# ---------------------------------------------------------------------------
# :::cli
# ---------------------------------------------------------------------------


def _handle_cli(arg, body, source_paths, base_dir):
    """Extract CLI help/usage information from a module.

    For v1: extracts the module docstring and any string constants named
    HELP or USAGE, formatted as a code block.
    """
    if not arg:
        return format_error(":::cli requires a module path argument")

    filepath = _resolve_module_path(arg, source_paths, base_dir)
    if filepath is None:
        return format_error(f"module '{arg}' not found")

    source, err = read_source(filepath)
    if err:
        return format_error(f"cannot read '{arg}': {err}")

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as exc:
        return format_error(f"syntax error in '{arg}': {exc}")

    parts = []

    # Module docstring
    module_doc = ast.get_docstring(tree)
    if module_doc:
        parts.append(module_doc)

    # Look for HELP or USAGE string constants
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("HELP", "USAGE"):
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, str
                    ):
                        parts.append(f"```\n{node.value.value.strip()}\n```")

    if not parts:
        return format_error(f"no CLI documentation found in '{arg}'")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# :::config
# ---------------------------------------------------------------------------


def _handle_config(arg, body, source_paths, base_dir):
    """Extract config file contents as a documented table.

    Supports JSON and TOML. Detects format from file extension.
    """
    if not arg:
        return format_error(":::config requires a file path argument")

    full_path = os.path.join(base_dir, arg)
    if not os.path.isfile(full_path):
        return format_error(f"config file '{arg}' not found")

    ext = os.path.splitext(arg)[1].lower()

    if ext == ".json":
        return _config_from_json(full_path, arg)
    elif ext == ".toml":
        return _config_from_toml(full_path, arg)
    else:
        # Unsupported format -- show as code block
        content, err = read_source(full_path)
        if err:
            return format_error(f"cannot read '{arg}': {err}")
        return f"```\n{content.rstrip()}\n```"


