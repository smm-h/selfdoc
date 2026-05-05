"""TypeScript/JavaScript source extractor -- resolves directives by extracting from .ts/.js files.

Uses regex-based parsing (no external dependencies). Handles:
- :::module  -- extract module-level JSDoc, exported functions/classes/interfaces/types
- :::test    -- extract test blocks (describe/it/test) by name
- :::schema  -- extract interface/type fields as table
- :::cli     -- extract help/usage strings or module-level JSDoc
- :::config  -- extract JSON/JSONC/TOML config files as tables
"""

import json
import os
import re


def resolve_typescript(name, arg, body, source_paths, base_dir):
    """Dispatch a directive to the appropriate TypeScript/JS extraction handler.

    Args:
        name: Directive name (module, test, schema, cli, config).
        arg: Directive argument (path, type name, etc.).
        body: Body lines of the directive block.
        source_paths: List of source directories from selfdoc.json.
        base_dir: Project root directory.

    Returns:
        Markdown string with the extracted content.
    """
    handlers = {
        "module": _handle_module,
        "test": _handle_test,
        "schema": _handle_schema,
        "cli": _handle_cli,
        "config": _handle_config,
    }
    handler = handlers.get(name)
    if handler is None:
        return f"> *[selfdoc: unknown directive '{name}' for TypeScript extractor]*"
    return handler(arg, body, source_paths, base_dir)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Regex for a JSDoc block: /** ... */
# Uses re.DOTALL so . matches newlines within the block.
_JSDOC_RE = re.compile(r"/\*\*\s*\n(.*?)\*/", re.DOTALL)

# Matches export declarations we care about:
#   export function, export default function, export async function,
#   export class, export default class,
#   export interface, export type, export const, export let, export var,
#   export enum, export default
_EXPORT_RE = re.compile(
    r"^export\s+"
    r"(?:default\s+)?"
    r"(?:async\s+)?"
    r"(?:function\s+|class\s+|interface\s+|type\s+|const\s+|let\s+|var\s+|enum\s+)?"
    r"(\w+)?",
    re.MULTILINE,
)

# Known TS/JS file extensions
_TS_JS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs", ".cts", ".cjs"}


def _resolve_file_path(arg, source_paths, base_dir):
    """Resolve a file path argument to an actual TS/JS file on disk.

    Tries the arg as-is (relative to base_dir and each source path),
    then with common extensions appended.
    """
    candidates = []

    # Direct path attempts
    candidates.append(os.path.join(base_dir, arg))
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, arg))

    # If no extension, try common ones
    _, ext = os.path.splitext(arg)
    if ext not in _TS_JS_EXTENSIONS:
        for try_ext in [".ts", ".tsx", ".js", ".jsx"]:
            candidates.append(os.path.join(base_dir, arg + try_ext))
            for sp in source_paths:
                candidates.append(os.path.join(base_dir, sp, arg + try_ext))
            # Also try index files: arg/index.ts etc.
            candidates.append(os.path.join(base_dir, arg, "index" + try_ext))
            for sp in source_paths:
                candidates.append(os.path.join(base_dir, sp, arg, "index" + try_ext))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return None


def _read_file(filepath):
    """Read a file and return its contents, or raise an error string."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def _parse_jsdoc_text(raw_jsdoc):
    """Parse raw JSDoc content (the lines between /** and */).

    Returns a dict with:
      - description: the main description text
      - params: list of {name, description}
      - returns: return description or None
      - tags: list of {tag, name, description} for other tags
    """
    lines = raw_jsdoc.split("\n")
    cleaned = []
    for line in lines:
        # Strip leading whitespace and the leading " * " or " *" prefix
        stripped = re.sub(r"^\s*\*\s?", "", line)
        cleaned.append(stripped)

    description_parts = []
    params = []
    returns = None
    tags = []

    i = 0
    while i < len(cleaned):
        line = cleaned[i]
        # Check for @tag
        tag_match = re.match(r"^@(\w+)\s*(.*)", line)
        if tag_match:
            tag_name = tag_match.group(1)
            tag_rest = tag_match.group(2).strip()

            if tag_name == "param":
                # @param {type} name description  OR  @param name description
                param_match = re.match(
                    r"(?:\{[^}]*\}\s+)?(\w+)\s*(.*)", tag_rest
                )
                if param_match:
                    params.append(
                        {
                            "name": param_match.group(1),
                            "description": param_match.group(2).strip(),
                        }
                    )
            elif tag_name in ("returns", "return"):
                # @returns {type} description  OR  @returns description
                ret_match = re.match(r"(?:\{[^}]*\}\s+)?(.*)", tag_rest)
                returns = ret_match.group(1).strip() if ret_match else tag_rest
            else:
                tags.append(
                    {"tag": tag_name, "name": "", "description": tag_rest}
                )
        else:
            description_parts.append(line)
        i += 1

    # Trim trailing empty lines from description
    while description_parts and not description_parts[-1].strip():
        description_parts.pop()
    # Trim leading empty lines from description
    while description_parts and not description_parts[0].strip():
        description_parts.pop(0)

    return {
        "description": "\n".join(description_parts),
        "params": params,
        "returns": returns,
        "tags": tags,
    }


def _find_jsdoc_before(source, pos):
    """Find the JSDoc block that ends right before `pos` in the source.

    Looks backwards from pos for a */ that's part of a /** ... */ block,
    allowing only whitespace between the end of the JSDoc and pos.
    """
    # Get the text before pos
    before = source[:pos]
    # Strip trailing whitespace to find */
    stripped = before.rstrip()
    if not stripped.endswith("*/"):
        return None

    # Find the matching /**
    end_idx = stripped.rfind("*/")
    # Search backwards for the opening /**
    search_start = stripped.rfind("/**", 0, end_idx)
    if search_start == -1:
        return None

    raw = stripped[search_start + 3 : end_idx]
    return _parse_jsdoc_text(raw)


def _format_jsdoc_as_markdown(jsdoc):
    """Format a parsed JSDoc dict as markdown text."""
    parts = []
    if jsdoc["description"]:
        parts.append(jsdoc["description"])

    if jsdoc["params"]:
        parts.append("")
        parts.append("**Parameters:**")
        for p in jsdoc["params"]:
            desc = f" -- {p['description']}" if p["description"] else ""
            parts.append(f"- `{p['name']}`{desc}")

    if jsdoc["returns"]:
        parts.append("")
        parts.append(f"**Returns:** {jsdoc['returns']}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# :::module
# ---------------------------------------------------------------------------


def _handle_module(arg, body, source_paths, base_dir):
    """Extract module-level JSDoc and exported declarations from a TS/JS file."""
    if not arg:
        return "> *[selfdoc: :::module requires a file path argument]*"

    filepath = _resolve_file_path(arg, source_paths, base_dir)
    if filepath is None:
        return f"> *[selfdoc: module '{arg}' not found]*"

    try:
        source = _read_file(filepath)
    except (OSError, UnicodeDecodeError) as exc:
        return f"> *[selfdoc: cannot read '{arg}': {exc}]*"

    # Display name: strip extension, use forward slashes
    display_name = arg.replace("\\", "/")
    for ext in _TS_JS_EXTENSIONS:
        if display_name.endswith(ext):
            display_name = display_name[: -len(ext)]
            break

    parts = []
    parts.append(f"# {display_name}")

    # Module-level JSDoc: the first /** */ block before any declaration
    module_jsdoc = _extract_module_jsdoc(source)
    if module_jsdoc:
        parts.append("")
        parts.append(module_jsdoc["description"])

    # Extract all exported declarations with their JSDoc
    exports = _extract_exports(source)
    for export in exports:
        parts.append("")
        parts.append(f"## {export['name']}")
        parts.append("")

        # Show the signature as a code block
        lang = "typescript" if filepath.endswith((".ts", ".tsx")) else "javascript"
        parts.append(f"```{lang}\n{export['signature']}\n```")

        if export["jsdoc"]:
            parts.append("")
            parts.append(_format_jsdoc_as_markdown(export["jsdoc"]))

    return "\n".join(parts)


def _extract_module_jsdoc(source):
    """Extract the first JSDoc block that appears before any declaration.

    A module-level JSDoc is a /** */ block at the top of the file, before
    any import/export/declaration.
    """
    # Find the first JSDoc block
    match = _JSDOC_RE.search(source)
    if match is None:
        return None

    # Check that nothing significant comes before it (only whitespace/comments)
    before = source[: match.start()].strip()
    if before:
        # There's code before this JSDoc -- it's not module-level
        return None

    # Check that the next non-whitespace after the JSDoc is an import/export
    # or end of significant content -- meaning this JSDoc isn't attached to
    # a specific export. We check if the next line is an export/declaration.
    after_pos = match.end()
    after_text = source[after_pos:].lstrip()

    # If the next thing is an import or export, this JSDoc is module-level
    # only if the export is NOT immediately following (i.e., there's a blank line
    # or an import between them). But in practice, if a JSDoc is the first thing
    # in the file and is followed by an import, it's the module doc.
    if after_text.startswith("import ") or after_text.startswith("import{"):
        return _parse_jsdoc_text(match.group(1))

    # If followed directly by an export, it's attached to that export, not module-level
    if re.match(r"export\s", after_text):
        return _parse_jsdoc_text(match.group(1))

    # Otherwise it's a standalone module doc
    return _parse_jsdoc_text(match.group(1))


def _extract_exports(source):
    """Extract all exported declarations with their JSDoc and signatures.

    Returns a list of dicts with: name, signature, jsdoc (parsed or None).
    """
    results = []
    # Regex that matches the start of an export declaration and captures
    # the full signature line (up to { or newline)
    export_pattern = re.compile(
        r"^(export\s+"
        r"(?:default\s+)?"
        r"(?:async\s+)?"
        r"(?:function\s*\*?\s*|class\s+|interface\s+|type\s+|const\s+|let\s+|var\s+|enum\s+)"
        r"[^\n{;]*(?:[{;]|\([^)]*\)[^{;]*[{;])?"
        r")",
        re.MULTILINE,
    )

    for match in export_pattern.finditer(source):
        sig_raw = match.group(1).strip()
        # Extract the name from the signature
        name = _extract_name_from_signature(sig_raw)
        if not name:
            continue

        # Clean up the signature: remove trailing { or ;
        signature = re.sub(r"\s*[{;]\s*$", "", sig_raw).strip()

        # Look for JSDoc above this export
        jsdoc = _find_jsdoc_before(source, match.start())

        results.append(
            {"name": name, "signature": signature, "jsdoc": jsdoc}
        )

    return results


def _extract_name_from_signature(sig):
    """Extract the declaration name from an export signature string."""
    # Try to match: export [default] [async] (function|class|interface|type|const|...) NAME
    m = re.match(
        r"export\s+(?:default\s+)?(?:async\s+)?"
        r"(?:function\s*\*?\s*|class\s+|interface\s+|type\s+|const\s+|let\s+|var\s+|enum\s+)"
        r"(\w+)",
        sig,
    )
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# :::test
# ---------------------------------------------------------------------------


def _handle_test(arg, body, source_paths, base_dir):
    """Extract test source code from a test file.

    arg format: <file_path> [TestName]

    For TS/JS test files, looks for describe("TestName", ...),
    it("TestName", ...), or test("TestName", ...) blocks.
    """
    if not arg:
        return "> *[selfdoc: :::test requires a file path argument]*"

    parts = arg.split(None, 1)
    file_path = parts[0]
    target_name = parts[1] if len(parts) > 1 else None

    # Resolve the file
    full_path = os.path.join(base_dir, file_path)
    if not os.path.isfile(full_path):
        # Try with source paths
        full_path = _resolve_file_path(file_path, source_paths, base_dir)
        if full_path is None:
            return f"> *[selfdoc: test file '{file_path}' not found]*"

    try:
        source = _read_file(full_path)
    except (OSError, UnicodeDecodeError) as exc:
        return f"> *[selfdoc: cannot read '{file_path}': {exc}]*"

    lang = "typescript" if full_path.endswith((".ts", ".tsx")) else "javascript"

    if target_name is None:
        return f"```{lang}\n{source.rstrip()}\n```"

    # Find the target test block by name
    block = _extract_test_block(source, target_name)
    if block is None:
        return f"> *[selfdoc: '{target_name}' not found in '{file_path}']*"

    return f"```{lang}\n{block}\n```"


def _extract_test_block(source, target_name):
    """Find a describe/it/test block by name and extract its source.

    Searches for patterns like:
      describe("Name", ...
      it("Name", ...
      test("Name", ...
    Then tracks brace depth to find the end of the block.
    """
    # Escape the target name for regex, support both quote styles
    escaped = re.escape(target_name)
    pattern = re.compile(
        rf"""(describe|it|test)\s*\(\s*(?:['"]){escaped}(?:['"])""",
    )

    match = pattern.search(source)
    if match is None:
        return None

    # Find the start of the full statement (the describe/it/test keyword)
    start = match.start()

    # Track brace/paren depth to find the end of this block
    # We need to find the matching closing paren for the outer call
    pos = match.end()
    paren_depth = 1  # We're inside the opening ( of describe/it/test
    brace_depth = 0
    in_string = False
    string_char = None
    in_template = False
    template_depth = 0

    while pos < len(source) and paren_depth > 0:
        ch = source[pos]

        # Handle escape sequences in strings
        if in_string and ch == "\\":
            pos += 2
            continue

        if in_string:
            if ch == string_char:
                in_string = False
            pos += 1
            continue

        if in_template:
            if ch == "\\" :
                pos += 2
                continue
            if ch == "$" and pos + 1 < len(source) and source[pos + 1] == "{":
                template_depth += 1
                pos += 2
                continue
            if ch == "}" and template_depth > 0:
                template_depth -= 1
                pos += 1
                continue
            if ch == "`" and template_depth == 0:
                in_template = False
            pos += 1
            continue

        # Check for string/template start
        if ch in ("'", '"'):
            in_string = True
            string_char = ch
            pos += 1
            continue
        if ch == "`":
            in_template = True
            template_depth = 0
            pos += 1
            continue

        # Check for line comments
        if ch == "/" and pos + 1 < len(source):
            next_ch = source[pos + 1]
            if next_ch == "/":
                # Skip to end of line
                nl = source.find("\n", pos)
                pos = nl + 1 if nl != -1 else len(source)
                continue
            if next_ch == "*":
                # Skip to end of block comment
                end = source.find("*/", pos + 2)
                pos = end + 2 if end != -1 else len(source)
                continue

        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
        elif ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1

        pos += 1

    # pos is now just past the closing )
    # Include any trailing semicolon
    end = pos
    remaining = source[end:].lstrip()
    if remaining.startswith(";"):
        end = source.index(";", end) + 1

    block = source[start:end]

    # Dedent the block
    lines = block.split("\n")
    if lines:
        # Find minimum indentation (ignoring empty lines)
        min_indent = float("inf")
        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)
        if min_indent < float("inf") and min_indent > 0:
            lines = [
                line[min_indent:] if len(line) >= min_indent else line
                for line in lines
            ]
        block = "\n".join(lines)

    return block


# ---------------------------------------------------------------------------
# :::schema
# ---------------------------------------------------------------------------


def _handle_schema(arg, body, source_paths, base_dir):
    """Extract interface or type definition fields as a markdown table.

    arg format:
      - path/to/file.json  -> render JSON keys as table
      - path/to/file.ts TypeName -> extract interface/type fields
      - path/to/file.ts -> if only one interface, extract it
    """
    if not arg:
        return "> *[selfdoc: :::schema requires an argument]*"

    parts = arg.split(None, 1)
    file_or_module = parts[0]

    # Check if it's a JSON file
    if file_or_module.endswith(".json"):
        return _schema_from_json(file_or_module, base_dir)

    # TS/JS file with optional type name
    type_name = parts[1] if len(parts) > 1 else None

    filepath = _resolve_file_path(file_or_module, source_paths, base_dir)
    if filepath is None:
        return f"> *[selfdoc: file '{file_or_module}' not found]*"

    try:
        source = _read_file(filepath)
    except (OSError, UnicodeDecodeError) as exc:
        return f"> *[selfdoc: cannot read '{file_or_module}': {exc}]*"

    return _schema_from_ts(source, type_name, file_or_module)


def _schema_from_json(file_path, base_dir):
    """Render a JSON file as a documented table of keys, types, and values."""
    full_path = os.path.join(base_dir, file_path)
    if not os.path.isfile(full_path):
        return f"> *[selfdoc: JSON file '{file_path}' not found]*"

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return f"> *[selfdoc: cannot parse '{file_path}': {exc}]*"

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


def _schema_from_ts(source, type_name, display_path):
    """Extract interface or type fields from TypeScript source as a markdown table."""
    # Find all interface and type declarations
    # Pattern for interface: [export] interface Name [<generics>] [extends ...] {
    interface_pattern = re.compile(
        r"(?:export\s+)?interface\s+(\w+)(?:<[^>]*>)?\s*(?:extends\s+[^{]*)?\{",
        re.MULTILINE,
    )
    # Pattern for type: [export] type Name = { ... }
    type_pattern = re.compile(
        r"(?:export\s+)?type\s+(\w+)(?:<[^>]*>)?\s*=\s*\{",
        re.MULTILINE,
    )

    targets = []

    for match in interface_pattern.finditer(source):
        name = match.group(1)
        if type_name is None or name == type_name:
            targets.append(("interface", name, match))

    for match in type_pattern.finditer(source):
        name = match.group(1)
        if type_name is None or name == type_name:
            targets.append(("type", name, match))

    if not targets:
        if type_name:
            return (
                f"> *[selfdoc: type '{type_name}' not found in "
                f"'{display_path}']*"
            )
        return f"> *[selfdoc: no interfaces or types found in '{display_path}']*"

    # If type_name specified, use the first match; otherwise use first found
    kind, name, match = targets[0]

    # Extract the body of the interface/type (track brace depth)
    body_start = match.end()  # position right after the opening {
    body_text = _extract_brace_block(source, body_start - 1)
    if body_text is None:
        return f"> *[selfdoc: could not parse body of '{name}']*"

    # Parse fields from the body
    fields = _parse_interface_fields(body_text)

    if not fields:
        return f"> *[selfdoc: no fields found in '{name}']*"

    rows = []
    rows.append("| Field | Type | Description |")
    rows.append("| --- | --- | --- |")

    for field in fields:
        desc = field.get("description", "")
        rows.append(f"| `{field['name']}` | `{field['type']}` | {desc} |")

    return "\n".join(rows)


def _extract_brace_block(source, open_brace_pos):
    """Extract the content between matched braces starting at open_brace_pos.

    Returns the content between { and } (exclusive), or None if unmatched.
    """
    if source[open_brace_pos] != "{":
        return None

    depth = 0
    pos = open_brace_pos
    in_string = False
    string_char = None

    while pos < len(source):
        ch = source[pos]

        if in_string:
            if ch == "\\" :
                pos += 2
                continue
            if ch == string_char:
                in_string = False
            pos += 1
            continue

        if ch in ("'", '"', "`"):
            in_string = True
            string_char = ch
            pos += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace_pos + 1 : pos]

        pos += 1

    return None


def _parse_interface_fields(body):
    """Parse fields from an interface/type body string.

    Each field looks like:
      fieldName: Type;
      fieldName?: Type;
    Possibly preceded by a JSDoc comment or inline comment.
    """
    fields = []

    # Split into lines for processing
    lines = body.split("\n")
    pending_jsdoc = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Check for JSDoc block start (single-line or multi-line)
        if line.startswith("/**"):
            # Collect the full JSDoc block
            jsdoc_lines = [line]
            if "*/" not in line:
                i += 1
                while i < len(lines):
                    jsdoc_lines.append(lines[i])
                    if "*/" in lines[i]:
                        break
                    i += 1
            jsdoc_text = "\n".join(jsdoc_lines)
            # Extract the content between /** and */
            m = re.search(r"/\*\*\s*(.*?)\s*\*/", jsdoc_text, re.DOTALL)
            if m:
                parsed = _parse_jsdoc_text(m.group(1))
                pending_jsdoc = parsed["description"]
            i += 1
            continue

        # Check for single-line comment
        if line.startswith("//"):
            comment_text = line[2:].strip()
            pending_jsdoc = comment_text
            i += 1
            continue

        # Check for field declaration
        # Match: [readonly] name[?]: Type[;]  or  name[?]: Type[;]
        field_match = re.match(
            r"(?:readonly\s+)?(\w+)(\?)?:\s*(.+?)(?:;|,)?\s*$", line
        )
        if field_match:
            field_name = field_match.group(1)
            optional = field_match.group(2) == "?"
            field_type = field_match.group(3).strip()

            # Check for inline comment
            inline_comment = ""
            comment_idx = _find_inline_comment(line)
            if comment_idx is not None:
                inline_comment = line[comment_idx:].strip()
                # Re-parse the type without the comment
                before_comment = line[:comment_idx].strip()
                field_re = re.match(
                    r"(?:readonly\s+)?(\w+)(\?)?:\s*(.+?)(?:;|,)?\s*$",
                    before_comment,
                )
                if field_re:
                    field_type = field_re.group(3).strip()

            if optional:
                field_type += " (optional)"

            description = pending_jsdoc or inline_comment
            pending_jsdoc = None

            fields.append(
                {
                    "name": field_name,
                    "type": field_type,
                    "description": description,
                }
            )
        else:
            # Not a field -- reset pending jsdoc unless it's an empty line
            if line:
                pending_jsdoc = None

        i += 1

    return fields


def _find_inline_comment(line):
    """Find the position of an inline // comment, ignoring those inside strings.

    Returns the index of the // or None if no inline comment found.
    """
    in_string = False
    string_char = None
    i = 0
    while i < len(line):
        ch = line[i]
        if in_string:
            if ch == "\\" :
                i += 2
                continue
            if ch == string_char:
                in_string = False
            i += 1
            continue
        if ch in ("'", '"', "`"):
            in_string = True
            string_char = ch
            i += 1
            continue
        if ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
            return i
        i += 1
    return None


# ---------------------------------------------------------------------------
# :::cli
# ---------------------------------------------------------------------------


def _handle_cli(arg, body, source_paths, base_dir):
    """Extract CLI help/usage information from a TS/JS file.

    Looks for:
    - Module-level JSDoc comment
    - const help = "..." or const usage = "..." string constants
    - yargs/commander setup patterns
    """
    if not arg:
        return "> *[selfdoc: :::cli requires a file path argument]*"

    filepath = _resolve_file_path(arg, source_paths, base_dir)
    if filepath is None:
        return f"> *[selfdoc: module '{arg}' not found]*"

    try:
        source = _read_file(filepath)
    except (OSError, UnicodeDecodeError) as exc:
        return f"> *[selfdoc: cannot read '{arg}': {exc}]*"

    parts = []

    # Module-level JSDoc
    module_jsdoc = _extract_module_jsdoc(source)
    if module_jsdoc and module_jsdoc["description"]:
        parts.append(module_jsdoc["description"])

    # Look for help/usage string constants
    # Matches: const HELP = "..." or const USAGE = `...` etc.
    help_pattern = re.compile(
        r"(?:const|let|var)\s+(help|usage|HELP|USAGE)\s*=\s*"
        r"(?:"
        r"'([^']*(?:\\'[^']*)*)'"  # single-quoted
        r"|\"([^\"]*(?:\\\"[^\"]*)*)\""  # double-quoted
        r"|`([^`]*(?:\\`[^`]*)*)`"  # template literal
        r")",
        re.IGNORECASE,
    )
    for match in help_pattern.finditer(source):
        value = match.group(2) or match.group(3) or match.group(4)
        if value:
            parts.append(f"```\n{value.strip()}\n```")

    if not parts:
        return f"> *[selfdoc: no CLI documentation found in '{arg}']*"

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# :::config
# ---------------------------------------------------------------------------


def _handle_config(arg, body, source_paths, base_dir):
    """Extract config file contents as a documented table.

    Supports JSON, JSONC (strips // and /* */ comments), and TOML.
    """
    if not arg:
        return "> *[selfdoc: :::config requires a file path argument]*"

    full_path = os.path.join(base_dir, arg)
    if not os.path.isfile(full_path):
        return f"> *[selfdoc: config file '{arg}' not found]*"

    ext = os.path.splitext(arg)[1].lower()

    if ext == ".json":
        return _config_from_json(full_path, arg)
    elif ext == ".jsonc":
        return _config_from_jsonc(full_path, arg)
    elif ext == ".toml":
        return _config_from_toml(full_path, arg)
    else:
        # Unsupported format -- show as code block
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            return f"```\n{content.rstrip()}\n```"
        except (OSError, UnicodeDecodeError) as exc:
            return f"> *[selfdoc: cannot read '{arg}': {exc}]*"


def _config_from_json(full_path, display_path):
    """Parse JSON config and render as a key-value table."""
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return f"> *[selfdoc: cannot parse '{display_path}': {exc}]*"

    if not isinstance(data, dict):
        return f"```json\n{json.dumps(data, indent=2)}\n```"

    return _render_json_table(data)


def _config_from_jsonc(full_path, display_path):
    """Parse JSONC config (strip comments) and render as a key-value table."""
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        return f"> *[selfdoc: cannot read '{display_path}': {exc}]*"

    stripped = _strip_jsonc_comments(raw)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return f"> *[selfdoc: cannot parse '{display_path}': {exc}]*"

    if not isinstance(data, dict):
        return f"```json\n{json.dumps(data, indent=2)}\n```"

    return _render_json_table(data)


def _strip_jsonc_comments(text):
    """Strip // and /* */ comments from JSONC text, respecting strings."""
    result = []
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if escape:
            result.append(ch)
            escape = False
            i += 1
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            result.append(ch)
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(text):
            next_ch = text[i + 1]
            if next_ch == "/":
                # Line comment: skip to end of line
                while i < len(text) and text[i] != "\n":
                    i += 1
                result.append("\n")
                continue
            if next_ch == "*":
                # Block comment: skip to */
                i += 2
                while i < len(text) and not (
                    text[i] == "*" and i + 1 < len(text) and text[i + 1] == "/"
                ):
                    i += 1
                i += 2  # skip past */
                continue
        result.append(ch)
        i += 1

    # Strip trailing commas before } or ] (common JSONC pattern)
    joined = "".join(result)
    return re.sub(r",\s*([}\]])", r"\1", joined)


def _config_from_toml(full_path, display_path):
    """Parse TOML config and render as a key-value table."""
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return (
                "> *[selfdoc: TOML support requires Python 3.11+ "
                "or the 'tomli' package]*"
            )

    try:
        with open(full_path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, Exception) as exc:
        return f"> *[selfdoc: cannot parse '{display_path}': {exc}]*"

    rows = []
    rows.append("| Key | Type | Value |")
    rows.append("| --- | --- | --- |")
    _flatten_toml(data, "", rows)
    return "\n".join(rows)


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


def _render_json_table(data):
    """Render a JSON dict as a markdown key-value table."""
    rows = []
    rows.append("| Key | Type | Value |")
    rows.append("| --- | --- | --- |")

    for key, value in data.items():
        type_name = _json_type_name(value)
        value_repr = _json_value_repr(value)
        rows.append(f"| `{key}` | {type_name} | {value_repr} |")

    return "\n".join(rows)


# Shared JSON helpers (duplicated from python.py to avoid cross-extractor deps)


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
