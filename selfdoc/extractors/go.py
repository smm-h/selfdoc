"""Go source extractor -- resolves directives by extracting from .go files.

Uses regex-based parsing (no Go toolchain required). Handles:
- :::module  -- extract package doc, exported funcs/types/consts/vars
- :::test    -- extract test source code
- :::schema  -- extract struct fields as a table
- :::cli     -- extract usage constants and flag.* calls
- :::config  -- extract config file contents as tables (JSON/TOML/YAML)
"""

import os
import re

from selfdoc.extractors.base import (
    BaseExtractor,
    _config_from_json,
    _config_from_toml,
    format_error,
    read_source,
)
from selfdoc.extractors.python import _format_docstring

# Patterns for exported Go symbols (used by GoExtractor.public_symbols)
_GO_FUNC_RE = re.compile(r"^func\s+([A-Z]\w*)\s*\(")
_GO_METHOD_RE = re.compile(r"^func\s+\([^)]+\)\s+([A-Z]\w*)\s*\(")
_GO_TYPE_RE = re.compile(r"^type\s+([A-Z]\w*)\s+")
_GO_VAR_RE = re.compile(r"^var\s+([A-Z]\w*)")
_GO_CONST_RE = re.compile(r"^const\s+([A-Z]\w*)")


class GoExtractor(BaseExtractor):
    """Go language extractor implementing LanguageExtractor protocol."""

    @property
    def name(self) -> str:
        return "go"

    def detect(self, dir_path: str) -> bool:
        return os.path.isfile(os.path.join(dir_path, "go.mod"))

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None:
        return _resolve_package_dir(path_arg, source_paths, base_dir)

    def extract(
        self,
        directive_name: str,
        attrs: dict[str, str],
        body: list[str],
        source_paths: list[str],
        base_dir: str,
    ) -> str:
        # Reconstruct the old positional arg from attrs
        path = attrs.get("path", "")
        target = attrs.get("target", "")
        arg = f"{path} {target}".strip() if target else path

        handlers = {
            "ref": _handle_module,
            "code-test": _handle_test,
            "table-schema": _handle_schema,
            "code-help": _handle_cli,
            "table-config": _handle_config,
        }
        handler = handlers.get(directive_name)
        if handler is None:
            return format_error(f"unknown directive '{directive_name}' for Go extractor")
        return handler(arg, body, source_paths, base_dir)

    def file_extensions(self) -> list[str]:
        return [".go"]

    def public_symbols(self, file_path: str) -> list[str]:
        """Extract exported (capitalized) symbols from a Go source file.

        Skips lines inside // and /* */ comments.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        lines = source.split("\n")
        symbols = []
        in_block_comment = False

        for line in lines:
            stripped = line.strip()

            if in_block_comment:
                if "*/" in stripped:
                    in_block_comment = False
                    idx = stripped.index("*/")
                    stripped = stripped[idx + 2:].strip()
                    if not stripped:
                        continue
                else:
                    continue

            if "/*" in stripped:
                if "*/" in stripped[stripped.index("/*") + 2:]:
                    stripped = re.sub(r"/\*.*?\*/", "", stripped).strip()
                    if not stripped:
                        continue
                else:
                    in_block_comment = True
                    stripped = stripped[:stripped.index("/*")].strip()
                    if not stripped:
                        continue

            if stripped.startswith("//"):
                continue

            comment_idx = stripped.find("//")
            if comment_idx >= 0:
                stripped = stripped[:comment_idx].strip()

            for pattern in (
                _GO_METHOD_RE,
                _GO_FUNC_RE,
                _GO_TYPE_RE,
                _GO_VAR_RE,
                _GO_CONST_RE,
            ):
                m = pattern.match(stripped)
                if m:
                    sym_name = m.group(1)
                    if sym_name not in symbols:
                        symbols.append(sym_name)
                    break

        return symbols

# ---------------------------------------------------------------------------
# :::module
# ---------------------------------------------------------------------------


def _handle_module(arg, body, source_paths, base_dir):
    """Extract package doc, exported funcs, types, consts, and vars.

    arg is a package directory path (e.g. "internal/commit").
    Finds all .go files in that directory (excluding _test.go),
    extracts the package doc comment and all exported declarations.
    """
    if not arg:
        return format_error(":::module requires a package path argument")

    pkg_dir = _resolve_package_dir(arg, source_paths, base_dir)
    if pkg_dir is None:
        return format_error(f"package '{arg}' not found")

    # Collect all non-test .go files
    go_files = sorted(
        f
        for f in os.listdir(pkg_dir)
        if f.endswith(".go") and not f.endswith("_test.go")
    )

    if not go_files:
        return format_error(f"no .go files in '{arg}'")

    # Read all files and concatenate for processing
    file_contents = {}
    for gf in go_files:
        path = os.path.join(pkg_dir, gf)
        content, _err = read_source(path)
        file_contents[gf] = content if content is not None else ""

    # Extract package doc from the first file that has a package declaration
    package_name, package_doc = _extract_package_doc(file_contents)

    parts = []
    parts.append(f"## {arg}")

    if package_doc:
        parts.append("")
        parts.append(_format_docstring(package_doc))

    # Extract exported declarations from all files
    declarations = []
    for gf in go_files:
        source = file_contents.get(gf, "")
        declarations.extend(_extract_exported_declarations(source))

    # Group by kind for cleaner output
    kind_order = ["const", "var", "type", "func", "method"]
    kind_labels = {
        "const": "Constants",
        "var": "Variables",
        "type": "Types",
        "func": "Functions",
        "method": "Methods",
    }

    for kind in kind_order:
        kind_decls = [d for d in declarations if d["kind"] == kind]
        if not kind_decls:
            continue

        for decl in kind_decls:
            parts.append("")
            parts.append(f"### {decl['name']}")
            parts.append("")
            parts.append(f"```go\n{decl['signature']}\n```")
            if decl["doc"]:
                parts.append("")
                parts.append(_format_docstring(decl["doc"]))

    return "\n".join(parts)


def _resolve_package_dir(arg, source_paths, base_dir):
    """Resolve a package path argument to an actual directory.

    Tries each source_path prefix, then the base_dir directly.
    """
    candidates = []
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, arg))
    candidates.append(os.path.join(base_dir, arg))

    for candidate in candidates:
        if os.path.isdir(candidate):
            # Verify it contains at least one .go file
            if any(f.endswith(".go") for f in os.listdir(candidate)):
                return candidate

    return None


def _extract_package_doc(file_contents):
    """Extract the package name and doc comment from Go source files.

    The package doc is the contiguous // comment block immediately
    above the `package` declaration. Returns (package_name, doc_string).
    """
    for _filename, source in file_contents.items():
        lines = source.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r"^package\s+(\w+)", stripped)
            if match:
                pkg_name = match.group(1)
                doc = _collect_comment_block_above(lines, i)
                if doc:
                    return pkg_name, doc
                # Found package but no doc; keep looking in other files
                # (Go convention: doc comment goes in doc.go or the main file)
                break

    # Second pass: return package name even without doc
    for _filename, source in file_contents.items():
        match = re.search(r"^package\s+(\w+)", source, re.MULTILINE)
        if match:
            return match.group(1), ""

    return "", ""


def _collect_comment_block_above(lines, target_line_idx):
    """Collect contiguous // comment lines immediately above target_line_idx.

    Skips blank lines between the comment block and the declaration.
    Returns the comment text with // prefixes stripped.
    """
    if target_line_idx <= 0:
        return ""

    # Walk upward from the line before the target, skipping blank lines first
    idx = target_line_idx - 1
    while idx >= 0 and lines[idx].strip() == "":
        idx -= 1

    if idx < 0:
        return ""

    # Now collect contiguous // lines going upward
    comment_lines = []
    while idx >= 0:
        stripped = lines[idx].strip()
        if stripped.startswith("//"):
            # Remove the // prefix and one optional leading space
            text = stripped[2:]
            if text.startswith(" "):
                text = text[1:]
            comment_lines.append(text)
            idx -= 1
        else:
            break

    if not comment_lines:
        return ""

    # Reverse since we collected bottom-up
    comment_lines.reverse()
    return "\n".join(comment_lines)


# Patterns for exported Go declarations
_FUNC_RE = re.compile(
    r"^func\s+"
    r"(?:\(\s*\w+\s+\*?(\w+)\s*\)\s+)?"  # optional receiver: (x *Type)
    r"([A-Z]\w*)"                          # exported function name
    r"\s*\(.*$",                           # opening paren of params
    re.MULTILINE,
)

_TYPE_RE = re.compile(
    r"^type\s+([A-Z]\w*)\s+(.+)$",
    re.MULTILINE,
)

_CONST_RE = re.compile(
    r"^\s*([A-Z]\w*)\s*(?:[\w.*\[\]]+)?\s*=",
    re.MULTILINE,
)

_VAR_RE = re.compile(
    r"^\s*([A-Z]\w*)\s+",
    re.MULTILINE,
)


def _extract_exported_declarations(source):
    """Extract all exported declarations from a Go source file.

    Returns a list of dicts with keys: kind, name, signature, doc.
    """
    lines = source.split("\n")
    declarations = []
    seen_names = set()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip lines inside block comments
        # (simple heuristic: skip /* ... */ blocks)

        # func declarations (including methods)
        func_match = re.match(
            r"^func\s+"
            r"(?:\(\s*\w+\s+\*?(\w+)\s*\)\s+)?"  # optional receiver
            r"([A-Z]\w*)"                          # exported name
            r"(\(.*)",                             # rest of signature
            stripped,
        )
        if func_match:
            receiver_type = func_match.group(1)
            func_name = func_match.group(2)
            # Build the full signature line
            sig = stripped.rstrip("{").rstrip()
            doc = _collect_comment_block_above(lines, i)

            if receiver_type:
                display_name = f"{receiver_type}.{func_name}"
                kind = "method"
            else:
                display_name = func_name
                kind = "func"

            if display_name not in seen_names:
                seen_names.add(display_name)
                declarations.append(
                    {
                        "kind": kind,
                        "name": display_name,
                        "signature": sig,
                        "doc": doc,
                    }
                )
            continue

        # type declarations
        type_match = re.match(r"^type\s+([A-Z]\w*)\s+(.*)", stripped)
        if type_match:
            type_name = type_match.group(1)
            type_rest = type_match.group(2)
            sig = stripped.rstrip("{").rstrip()
            doc = _collect_comment_block_above(lines, i)

            if type_name not in seen_names:
                seen_names.add(type_name)
                declarations.append(
                    {
                        "kind": "type",
                        "name": type_name,
                        "signature": sig,
                        "doc": doc,
                    }
                )
            continue

        # const block: `const ( ... )`
        if stripped == "const (" or stripped.startswith("const ("):
            _extract_const_block(lines, i, declarations, seen_names)
            continue

        # Single-line const: `const Name = value` or `const Name Type = value`
        const_match = re.match(
            r"^const\s+([A-Z]\w*)\s*(.*)", stripped
        )
        if const_match:
            const_name = const_match.group(1)
            sig = stripped
            doc = _collect_comment_block_above(lines, i)
            if const_name not in seen_names:
                seen_names.add(const_name)
                declarations.append(
                    {
                        "kind": "const",
                        "name": const_name,
                        "signature": sig,
                        "doc": doc,
                    }
                )
            continue

        # var block: `var ( ... )`
        if stripped == "var (" or stripped.startswith("var ("):
            _extract_var_block(lines, i, declarations, seen_names)
            continue

        # Single-line var: `var Name Type = value`
        var_match = re.match(
            r"^var\s+([A-Z]\w*)\s+(.*)", stripped
        )
        if var_match:
            var_name = var_match.group(1)
            sig = stripped
            doc = _collect_comment_block_above(lines, i)
            if var_name not in seen_names:
                seen_names.add(var_name)
                declarations.append(
                    {
                        "kind": "var",
                        "name": var_name,
                        "signature": sig,
                        "doc": doc,
                    }
                )
            continue

    return declarations


def _extract_const_block(lines, block_start_idx, declarations, seen_names):
    """Extract exported constants from a const (...) block.

    The doc comment for the entire block is attached to the first exported
    constant. Individual constants may also have their own // comments.
    """
    block_doc = _collect_comment_block_above(lines, block_start_idx)

    i = block_start_idx + 1
    first_exported = True
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == ")" or stripped.startswith(")"):
            break

        # Check for exported constant inside the block
        match = re.match(r"^([A-Z]\w*)\s*(.*)", stripped)
        if match:
            name = match.group(1)
            doc = _collect_comment_block_above(lines, i)
            # If this is the first exported const and it has no own doc,
            # use the block doc
            if first_exported and not doc and block_doc:
                doc = block_doc
            first_exported = False

            sig = f"const {stripped}"
            if name not in seen_names:
                seen_names.add(name)
                declarations.append(
                    {
                        "kind": "const",
                        "name": name,
                        "signature": sig,
                        "doc": doc,
                    }
                )
        i += 1


def _extract_var_block(lines, block_start_idx, declarations, seen_names):
    """Extract exported variables from a var (...) block."""
    block_doc = _collect_comment_block_above(lines, block_start_idx)

    i = block_start_idx + 1
    first_exported = True
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == ")" or stripped.startswith(")"):
            break

        match = re.match(r"^([A-Z]\w*)\s+(.*)", stripped)
        if match:
            name = match.group(1)
            doc = _collect_comment_block_above(lines, i)
            if first_exported and not doc and block_doc:
                doc = block_doc
            first_exported = False

            sig = f"var {stripped}"
            if name not in seen_names:
                seen_names.add(name)
                declarations.append(
                    {
                        "kind": "var",
                        "name": name,
                        "signature": sig,
                        "doc": doc,
                    }
                )
        i += 1


# ---------------------------------------------------------------------------
# :::test
# ---------------------------------------------------------------------------


def _handle_test(arg, body, source_paths, base_dir):
    """Extract test source code from a Go test file.

    arg format: <file_path> [TestFuncName]
    """
    if not arg:
        return format_error(":::test requires a file path argument")

    parts = arg.split(None, 1)
    file_path = parts[0]
    target_name = parts[1] if len(parts) > 1 else None

    full_path = _resolve_file_path(file_path, source_paths, base_dir)
    if full_path is None:
        return format_error(f"test file '{file_path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{file_path}': {err}")

    if target_name is None:
        return f"```go\n{source.rstrip()}\n```"

    # Extract the specific test function
    extracted = _extract_go_function(source, target_name)
    if extracted is None:
        return format_error(f"'{target_name}' not found in '{file_path}'")

    return f"```go\n{extracted}\n```"


def _resolve_file_path(file_path, source_paths, base_dir):
    """Resolve a file path relative to base_dir or source_paths."""
    candidates = [os.path.join(base_dir, file_path)]
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, file_path))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _extract_go_function(source, func_name):
    """Extract a complete function from Go source by name.

    Uses brace-counting to find the function body boundaries.
    """
    lines = source.split("\n")

    for i, line in enumerate(lines):
        # Match func declaration line containing the target name
        if re.match(
            rf"^func\s+(?:\(.*?\)\s+)?{re.escape(func_name)}\s*\(",
            line.strip(),
        ):
            # Collect the doc comment above
            doc_start = i
            j = i - 1
            while j >= 0 and lines[j].strip() == "":
                j -= 1
            while j >= 0 and lines[j].strip().startswith("//"):
                doc_start = j
                j -= 1

            # Find the end of the function using brace counting
            brace_count = 0
            func_end = i
            started = False

            for k in range(i, len(lines)):
                for ch in lines[k]:
                    if ch == "{":
                        brace_count += 1
                        started = True
                    elif ch == "}":
                        brace_count -= 1
                if started and brace_count == 0:
                    func_end = k
                    break

            return "\n".join(lines[doc_start : func_end + 1])

    return None


# ---------------------------------------------------------------------------
# :::schema
# ---------------------------------------------------------------------------


def _handle_schema(arg, body, source_paths, base_dir):
    """Extract struct type fields as a markdown table.

    arg format: <file_path> [TypeName]
    If TypeName is omitted, extracts the first exported struct found.
    """
    if not arg:
        return format_error(":::schema requires a file path argument")

    parts = arg.split(None, 1)
    file_path = parts[0]
    type_name = parts[1] if len(parts) > 1 else None

    full_path = _resolve_file_path(file_path, source_paths, base_dir)
    if full_path is None:
        # Also try as JSON/TOML/YAML config
        if file_path.endswith((".json", ".toml", ".yaml", ".yml")):
            return _handle_config(arg, body, source_paths, base_dir)
        return format_error(f"file '{file_path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{file_path}': {err}")

    structs = _extract_structs(source)

    if not structs:
        return format_error(f"no struct types found in '{file_path}'")

    if type_name:
        target = next((s for s in structs if s["name"] == type_name), None)
        if target is None:
            return format_error(
                f"struct '{type_name}' not found in '{file_path}'"
            )
        return _format_struct_table(target)

    # No type specified: format all exported structs
    results = []
    for s in structs:
        results.append(f"### {s['name']}")
        results.append("")
        if s["doc"]:
            results.append(s["doc"])
            results.append("")
        results.append(_format_struct_table(s))
    return "\n".join(results)


def _extract_structs(source):
    """Extract all exported struct type declarations from Go source.

    Returns a list of dicts: {name, doc, fields: [{name, type, tag, comment}]}.
    """
    lines = source.split("\n")
    structs = []

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Match: type Name struct {
        match = re.match(r"^type\s+([A-Z]\w*)\s+struct\s*\{", stripped)
        if match:
            struct_name = match.group(1)
            doc = _collect_comment_block_above(lines, i)

            # Parse fields until closing brace
            fields = []
            j = i + 1
            while j < len(lines):
                field_line = lines[j].strip()
                if field_line == "}" or field_line.startswith("}"):
                    break

                field = _parse_struct_field(field_line, lines, j)
                if field:
                    fields.append(field)
                j += 1

            structs.append(
                {"name": struct_name, "doc": doc, "fields": fields}
            )

        i += 1

    return structs


def _parse_struct_field(field_line, lines, line_idx):
    """Parse a single struct field line.

    Returns {name, type, tag, comment} or None if not a field.
    """
    # Skip blank lines and comments
    if not field_line or field_line.startswith("//"):
        return None

    # Skip embedded types (no field name before type)
    # Exported fields start with uppercase letter
    # Field format: Name Type `tag` // comment
    match = re.match(
        r"^([A-Za-z]\w*)\s+"     # field name
        r"(\S+(?:\s*\[.*?\])?)"  # type (may include generics/slices)
        r"(?:\s+(`[^`]*`))?"     # optional struct tag
        r"(?:\s*//\s*(.*))?"     # optional inline comment
        r"\s*$",
        field_line,
    )
    if not match:
        return None

    name = match.group(1)
    field_type = match.group(2)
    tag = match.group(3) or ""
    inline_comment = match.group(4) or ""

    # Also check for a doc comment above the field
    doc_above = _collect_comment_block_above(lines, line_idx)
    description = inline_comment or doc_above

    return {
        "name": name,
        "type": field_type,
        "tag": tag.strip("`") if tag else "",
        "comment": description,
    }


def _format_struct_table(struct_info):
    """Format a struct's fields as a markdown table."""
    rows = []
    rows.append("| Field | Type | Tag | Description |")
    rows.append("| --- | --- | --- | --- |")

    for field in struct_info["fields"]:
        tag_display = f"`{field['tag']}`" if field["tag"] else ""
        rows.append(
            f"| `{field['name']}` | `{field['type']}` "
            f"| {tag_display} | {field['comment']} |"
        )

    return "\n".join(rows)


# ---------------------------------------------------------------------------
# :::cli
# ---------------------------------------------------------------------------


def _handle_cli(arg, body, source_paths, base_dir):
    """Extract CLI usage/help text and flag definitions from Go source.

    Looks for:
    - String constants named usage, helpText, usageText (case-insensitive match)
    - flag.StringVar, flag.BoolVar, etc. calls
    """
    if not arg:
        return format_error(":::cli requires a file path argument")

    full_path = _resolve_file_path(arg, source_paths, base_dir)
    if full_path is None:
        return format_error(f"file '{arg}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{arg}': {err}")

    parts = []

    # Extract usage/help text constants
    usage_text = _extract_usage_constants(source)
    if usage_text:
        for name, text in usage_text:
            parts.append(f"**{name}:**")
            parts.append("")
            parts.append(f"```\n{text.strip()}\n```")

    # Extract flag definitions
    flags = _extract_flag_calls(source)
    if flags:
        parts.append("")
        parts.append("**Flags:**")
        parts.append("")
        parts.append("| Flag | Type | Default | Description |")
        parts.append("| --- | --- | --- | --- |")
        for flag in flags:
            parts.append(
                f"| `{flag['name']}` | {flag['type']} "
                f"| {flag['default']} | {flag['desc']} |"
            )

    if not parts:
        return format_error(f"no CLI documentation found in '{arg}'")

    return "\n".join(parts)


def _extract_usage_constants(source):
    """Find string constants/functions that return usage text.

    Looks for patterns like:
    - const usage = `...`
    - func usageText() string { return `...` }
    - Any variable/const with "usage" or "help" in the name containing a string
    """
    results = []

    # Match backtick-quoted strings assigned to usage/help-like names
    # Pattern: (const|var|)? name = `...`
    # Also match function returns
    usage_names_re = re.compile(
        r"(?:const|var)?\s*"
        r"(\w*(?:[Uu]sage|[Hh]elp)\w*)"
        r"\s*(?:=|string\s*=)\s*"
        r"`((?:[^`]|\\`)*)`",
        re.DOTALL,
    )

    for match in usage_names_re.finditer(source):
        name = match.group(1)
        text = match.group(2)
        results.append((name, text))

    # Also match return `...` inside func usageText/usage/helpText
    func_re = re.compile(
        r"func\s+(\w*(?:[Uu]sage|[Hh]elp)\w*)\s*\([^)]*\)\s*string\s*\{"
        r"\s*return\s*`((?:[^`]|\\`)*)`",
        re.DOTALL,
    )

    for match in func_re.finditer(source):
        name = match.group(1) + "()"
        text = match.group(2)
        results.append((name, text))

    return results


def _extract_flag_calls(source):
    """Extract flag.XxxVar and flag.Xxx calls from Go source.

    Returns list of {name, type, default, desc}.
    """
    flags = []

    # flag.StringVar(&var, "name", "default", "description")
    # flag.BoolVar(&var, "name", false, "description")
    var_re = re.compile(
        r"flag\.(\w+)Var\s*\(\s*"
        r"&\w+\s*,\s*"
        r'"([^"]*?)"\s*,\s*'      # flag name
        r"([^,]+?)\s*,\s*"        # default value
        r'"([^"]*?)"\s*\)',        # description
    )

    for match in var_re.finditer(source):
        flag_type = match.group(1).lower()
        flags.append(
            {
                "name": match.group(2),
                "type": flag_type,
                "default": match.group(3).strip().strip('"'),
                "desc": match.group(4),
            }
        )

    # flag.String("name", "default", "description")
    # flag.Bool("name", false, "description")
    direct_re = re.compile(
        r"flag\.(\w+)\s*\(\s*"
        r'"([^"]*?)"\s*,\s*'      # flag name
        r"([^,]+?)\s*,\s*"        # default value
        r'"([^"]*?)"\s*\)',        # description
    )

    for match in direct_re.finditer(source):
        call_name = match.group(1)
        # Skip XxxVar calls (already handled) and non-type calls like Parse
        if call_name.endswith("Var") or call_name in (
            "Parse",
            "Visit",
            "VisitAll",
            "Set",
            "Lookup",
            "PrintDefaults",
        ):
            continue
        flags.append(
            {
                "name": match.group(2),
                "type": call_name.lower(),
                "default": match.group(3).strip().strip('"'),
                "desc": match.group(4),
            }
        )

    return flags


# ---------------------------------------------------------------------------
# :::config
# ---------------------------------------------------------------------------


def _handle_config(arg, body, source_paths, base_dir):
    """Extract config file contents as a documented table.

    Supports JSON and TOML. Detects format from file extension.
    Delegates to the same logic as the Python extractor.
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


