"""Zig source extractor for selfdoc -- parses .zig files to extract public declarations, doc comments, and test blocks for documentation pages.

Uses regex-based parsing (no Zig toolchain required). Handles:
- :::ref     -- extract module doc, pub declarations with doc comments
- :::prose-desc -- extract module-level //! doc comments only
- :::table-schema -- extract struct fields as a table
- :::code-test -- extract test blocks
- :::table-config -- extract config file contents as tables (JSON/TOML)
"""

import os
import re

from selfdoc_core.extractors.base import (
    BaseExtractor,
    _extract_brace_block,
    _format_docstring,
    format_error,
    handle_table_config,
    read_source,
)
from selfdoc_core.tables import render_markdown_table

# Patterns for public Zig declarations (used by ZigExtractor.public_symbols)
# pub fn name(...)
_ZIG_PUB_FN_RE = re.compile(
    r"^pub\s+(?:extern\s+|export\s+|inline\s+)?fn\s+(\w+)\s*\("
)
# pub const Name = struct/enum/union/error/value
_ZIG_PUB_CONST_RE = re.compile(r"^pub\s+const\s+(\w+)\s*[=:]")
# pub var name
_ZIG_PUB_VAR_RE = re.compile(r"^pub\s+var\s+(\w+)")


class ZigExtractor(BaseExtractor):
    """Zig language extractor implementing LanguageExtractor protocol."""

    @property
    def name(self) -> str:
        return "zig"

    def detect(self, dir_path: str) -> bool:
        return os.path.isfile(
            os.path.join(dir_path, "build.zig")
        ) or os.path.isfile(os.path.join(dir_path, "build.zig.zon"))

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None:
        return _resolve_zig_path(path_arg, source_paths, base_dir)

    def file_extensions(self) -> list[str]:
        return [".zig"]

    def public_symbols(self, file_path: str) -> list[str]:
        """Extract public (pub) symbols from a Zig source file.

        Handles pub fn, pub extern fn, pub export fn, pub inline fn,
        pub const, and pub var. Skips test blocks and private declarations.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        lines = source.split("\n")
        symbols = []

        for line in lines:
            stripped = line.strip()

            # Skip comment-only lines
            if stripped.startswith("//"):
                continue

            # Skip test blocks
            if stripped.startswith("test "):
                continue

            # Remove trailing inline comments
            comment_idx = stripped.find("//")
            if comment_idx >= 0:
                stripped = stripped[:comment_idx].strip()

            for pattern in (_ZIG_PUB_FN_RE, _ZIG_PUB_CONST_RE, _ZIG_PUB_VAR_RE):
                m = pattern.match(stripped)
                if m:
                    sym_name = m.group(1)
                    if sym_name not in symbols:
                        symbols.append(sym_name)
                    break

        return symbols

    def module_docstring(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return ""
        return _extract_module_doc(source)

    def symbol_details(self, file_path: str, symbol_name: str) -> dict | None:
        """Extract detailed parameter and return info for a Zig function.

        Supports dotted names (e.g. "Config.init") to extract a method
        from within a struct/enum/union body.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return None

        if "." in symbol_name:
            return _dotted_symbol_details(source, symbol_name)

        lines = source.split("\n")
        pattern = re.compile(
            r"^(?:pub\s+)?(?:extern\s+|export\s+|inline\s+)?fn\s+"
            + re.escape(symbol_name)
            + r"\s*\("
        )

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if pattern.match(stripped):
                return _zig_symbol_details(lines, i)

        return None


# ---------------------------------------------------------------------------
# symbol_details helpers
# ---------------------------------------------------------------------------


def _dotted_symbol_details(source, symbol_name):
    """Extract symbol details for a dotted name like "Config.init".

    Finds the container type (struct/enum/union), extracts its brace-delimited
    body, then searches within that body for the member function.
    """
    type_name, member_name = symbol_name.rsplit(".", 1)

    # Find the container declaration line
    container_re = re.compile(
        r"^pub\s+const\s+" + re.escape(type_name)
        + r"\s*=\s*(?:struct|enum|union)(?:\s*\(.*?\))?\s*\{"
    )

    lines = source.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if container_re.match(stripped):
            # Find the position of the opening brace in the full source
            # by computing offset up to line i, then finding '{' in that line
            line_start = sum(len(line) + 1 for line in lines[:i])
            brace_offset = lines[i].index("{")
            open_brace_pos = line_start + brace_offset

            body = _extract_brace_block(source, open_brace_pos)
            if body is None:
                return None

            # Search within the body for the member function
            body_lines = body.split("\n")
            member_pattern = re.compile(
                r"^(?:pub\s+)?(?:extern\s+|export\s+|inline\s+)?fn\s+"
                + re.escape(member_name)
                + r"\s*\("
            )
            for j, bline in enumerate(body_lines):
                bstripped = bline.strip()
                if bstripped.startswith("//"):
                    continue
                if member_pattern.match(bstripped):
                    return _zig_symbol_details(body_lines, j)

            return None

    return None


def _parse_zig_params(param_str):
    """Parse Zig function parameters from the text between parentheses.

    Returns list of {"name": str, "type": str|None}.
    Strips comptime keyword. Skips 'self' parameter.
    """
    params = []
    for part in param_str.split(","):
        part = part.strip()
        if not part:
            continue
        # Strip comptime keyword
        if part.startswith("comptime "):
            part = part[len("comptime "):]
        # Split on first colon
        if ":" not in part:
            continue
        name, type_str = part.split(":", 1)
        name = name.strip()
        type_str = type_str.strip()
        # Skip self parameter
        if name == "self":
            continue
        params.append({
            "name": name,
            "type": type_str if type_str else None,
        })
    return params


def _zig_symbol_details(lines, decl_line_idx):
    """Build symbol_details dict for a Zig function declaration."""
    sig = _extract_fn_signature(lines, decl_line_idx)

    # Extract parameter string between first ( and matching )
    open_idx = sig.find("(")
    if open_idx == -1:
        return {"params": [], "return_type": None, "return_documented": False}

    depth = 0
    close_idx = None
    for i in range(open_idx, len(sig)):
        if sig[i] == "(":
            depth += 1
        elif sig[i] == ")":
            depth -= 1
            if depth == 0:
                close_idx = i
                break

    if close_idx is None:
        return {"params": [], "return_type": None, "return_documented": False}

    param_str = sig[open_idx + 1 : close_idx]
    raw_params = _parse_zig_params(param_str)

    # Extract return type: everything after the closing paren
    return_type_str = sig[close_idx + 1 :].strip()
    return_type = return_type_str if return_type_str else None

    # Get doc comment
    doc_text = _collect_doc_comment_above(lines, decl_line_idx)

    # Check param documentation
    params = []
    for p in raw_params:
        documented = bool(
            doc_text and re.search(rf"\b{re.escape(p['name'])}\b", doc_text)
        )
        params.append({
            "name": p["name"],
            "type": p["type"],
            "documented": documented,
        })

    return_documented = (
        bool(re.search(r"\breturns?\b", doc_text, re.IGNORECASE))
        if doc_text
        else False
    )

    return {
        "params": params,
        "return_type": return_type,
        "return_documented": return_documented,
    }


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _resolve_zig_path(path_arg, source_paths, base_dir):
    """Resolve a path argument to a Zig source file or directory.

    Tries each source_path prefix, then the base_dir directly.
    Checks for both directories containing .zig files and direct .zig files.
    """
    candidates = []
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, path_arg))
    candidates.append(os.path.join(base_dir, path_arg))

    for candidate in candidates:
        if os.path.isdir(candidate):
            if any(f.endswith(".zig") for f in os.listdir(candidate)):
                return candidate
        if os.path.isfile(candidate):
            return candidate
        # Try appending .zig extension
        zig_candidate = candidate + ".zig"
        if os.path.isfile(zig_candidate):
            return zig_candidate

    return None


def _resolve_file_path(file_path, source_paths, base_dir):
    """Resolve a file path relative to base_dir or source_paths."""
    candidates = [os.path.join(base_dir, file_path)]
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, file_path))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Module doc extraction (//! comments)
# ---------------------------------------------------------------------------


def _extract_module_doc(source):
    """Extract module-level doc comments (//! lines) from Zig source.

    Returns the doc text with //! prefixes stripped.
    """
    lines = source.split("\n")
    doc_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("//!"):
            text = stripped[3:]
            if text.startswith(" "):
                text = text[1:]
            doc_lines.append(text)
        elif doc_lines:
            # Module doc is contiguous at the top; stop after first non-//! line
            break
        elif stripped and not stripped.startswith("//"):
            # Non-comment, non-blank line before any //! -- no module doc
            break

    return "\n".join(doc_lines) if doc_lines else ""


# ---------------------------------------------------------------------------
# Doc comment extraction (/// comments above declarations)
# ---------------------------------------------------------------------------


def _collect_doc_comment_above(lines, target_line_idx):
    """Collect contiguous /// doc comment lines immediately above target_line_idx.

    Skips blank lines between the comment block and the declaration.
    Returns the doc comment text with /// prefixes stripped.
    """
    if target_line_idx <= 0:
        return ""

    idx = target_line_idx - 1
    # Skip blank lines
    while idx >= 0 and lines[idx].strip() == "":
        idx -= 1

    if idx < 0:
        return ""

    # Collect contiguous /// lines going upward
    comment_lines = []
    while idx >= 0:
        stripped = lines[idx].strip()
        if stripped.startswith("///"):
            text = stripped[3:]
            if text.startswith(" "):
                text = text[1:]
            comment_lines.append(text)
            idx -= 1
        else:
            break

    if not comment_lines:
        return ""

    comment_lines.reverse()
    return "\n".join(comment_lines)


# ---------------------------------------------------------------------------
# :::ref
# ---------------------------------------------------------------------------


def _handle_ref(path, target, body, source_paths, base_dir, attrs):
    """Extract module doc and all pub declarations with their doc comments.

    path is a file path (e.g. "src/core/audio.zig") or a directory path.
    """
    if not path:
        return format_error(":::ref requires a file path argument")

    resolved = _resolve_zig_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    # If it's a directory, collect all .zig files
    if os.path.isdir(resolved):
        zig_files = sorted(
            f for f in os.listdir(resolved) if f.endswith(".zig")
        )
        if not zig_files:
            return format_error(f"no .zig files in '{path}'")
        file_contents = {}
        for zf in zig_files:
            zf_path = os.path.join(resolved, zf)
            content, _err = read_source(zf_path)
            file_contents[zf] = content if content is not None else ""
    else:
        content, err = read_source(resolved)
        if err:
            return format_error(f"cannot read '{path}': {err}")
        file_contents = {os.path.basename(resolved): content}

    parts = []
    parts.append(f"## {path}")

    # Extract module doc from the first file that has one
    for _filename, source in file_contents.items():
        module_doc = _extract_module_doc(source)
        if module_doc:
            parts.append("")
            parts.append(_format_docstring(module_doc))
            break

    # Extract pub declarations from all files
    declarations = []
    for _filename in sorted(file_contents.keys()):
        source = file_contents[_filename]
        declarations.extend(_extract_pub_declarations(source))

    if target:
        matched = [d for d in declarations if d["name"] == target]
        if not matched:
            return format_error(f"symbol '{target}' not found in '{path}'")
        decl = matched[0]
        parts_t = []
        parts_t.append(f"### {decl['name']}")
        parts_t.append("")
        parts_t.append(f"```zig\n{decl['signature']}\n```")
        if decl["doc"]:
            parts_t.append("")
            parts_t.append(_format_docstring(decl["doc"]))
        return "\n".join(parts_t)

    # Group by kind
    kind_order = ["const", "var", "fn"]
    for kind in kind_order:
        kind_decls = [d for d in declarations if d["kind"] == kind]
        for decl in kind_decls:
            parts.append("")
            parts.append(f"### {decl['name']}")
            parts.append("")
            parts.append(f"```zig\n{decl['signature']}\n```")
            if decl["doc"]:
                parts.append("")
                parts.append(_format_docstring(decl["doc"]))

    return "\n".join(parts)


def _extract_pub_declarations(source):
    """Extract all pub declarations from Zig source.

    Returns a list of dicts with keys: kind, name, signature, doc.
    """
    lines = source.split("\n")
    declarations = []
    seen_names = set()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip comment-only lines
        if stripped.startswith("//"):
            continue

        # Skip test blocks
        if stripped.startswith("test "):
            continue

        # pub fn (including extern, export, inline variants)
        fn_match = re.match(
            r"^pub\s+((?:extern|export|inline)\s+)?fn\s+(\w+)\s*(\(.*)",
            stripped,
        )
        if fn_match:
            fn_name = fn_match.group(2)
            # Build signature up to the opening brace or semicolon
            sig = _extract_fn_signature(lines, i)
            doc = _collect_doc_comment_above(lines, i)

            if fn_name not in seen_names:
                seen_names.add(fn_name)
                declarations.append({
                    "kind": "fn",
                    "name": fn_name,
                    "signature": sig,
                    "doc": doc,
                })
            continue

        # pub const
        const_match = re.match(
            r"^pub\s+const\s+(\w+)\s*(.*)", stripped
        )
        if const_match:
            const_name = const_match.group(1)
            sig = _clean_signature(stripped)
            doc = _collect_doc_comment_above(lines, i)

            if const_name not in seen_names:
                seen_names.add(const_name)
                declarations.append({
                    "kind": "const",
                    "name": const_name,
                    "signature": sig,
                    "doc": doc,
                })
            continue

        # pub var
        var_match = re.match(
            r"^pub\s+var\s+(\w+)\s*(.*)", stripped
        )
        if var_match:
            var_name = var_match.group(1)
            sig = _clean_signature(stripped)
            doc = _collect_doc_comment_above(lines, i)

            if var_name not in seen_names:
                seen_names.add(var_name)
                declarations.append({
                    "kind": "var",
                    "name": var_name,
                    "signature": sig,
                    "doc": doc,
                })
            continue

    return declarations


def _extract_fn_signature(lines, start_idx):
    """Extract a function signature from the declaration line.

    Returns the signature without the function body (strips trailing { and ;).
    """
    sig_parts = []
    for i in range(start_idx, min(start_idx + 5, len(lines))):
        line = lines[i].strip()
        sig_parts.append(line)
        if "{" in line or ";" in line:
            break

    sig = " ".join(sig_parts)
    # Remove trailing body opener
    sig = re.sub(r"\s*\{.*$", "", sig)
    # Remove trailing semicolon (for extern fn)
    sig = sig.rstrip(";").rstrip()
    return sig


def _clean_signature(line):
    """Clean a const/var declaration line for display.

    Strips trailing struct/enum/union body openers and semicolons.
    """
    # For struct/enum/union/error set definitions, keep just the type keyword
    line = re.sub(r"\s*\{[^}]*$", "", line)
    line = line.rstrip(";").rstrip()
    return line


# ---------------------------------------------------------------------------
# :::prose-desc
# ---------------------------------------------------------------------------


def _handle_prose_desc(path, target, body, source_paths, base_dir, attrs):
    """Extract only the module-level //! doc comments as prose markdown."""
    if not path:
        return format_error(":::prose-desc requires a file path argument")

    resolved = _resolve_zig_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    if os.path.isdir(resolved):
        # Try each .zig file for module doc
        zig_files = sorted(
            f for f in os.listdir(resolved) if f.endswith(".zig")
        )
        for zf in zig_files:
            content, _err = read_source(os.path.join(resolved, zf))
            if content:
                doc = _extract_module_doc(content)
                if doc:
                    return _format_docstring(doc)
        return format_error(f"no module doc comment found in '{path}'")
    else:
        content, err = read_source(resolved)
        if err:
            return format_error(f"cannot read '{path}': {err}")
        doc = _extract_module_doc(content)
        if not doc:
            return format_error(f"no module doc comment found in '{path}'")
        return _format_docstring(doc)


# ---------------------------------------------------------------------------
# :::table-schema
# ---------------------------------------------------------------------------


def _handle_table_schema(path, target, body, source_paths, base_dir, attrs):
    """Extract struct fields as a markdown table.

    path is the file path, target is an optional struct name.
    """
    if not path:
        return format_error(":::table-schema requires a file path argument")

    # JSON/TOML files are config files, not Zig source -- delegate
    if path.endswith((".json", ".toml")):
        return handle_table_config(path, None, body, source_paths, base_dir, attrs)

    full_path = _resolve_file_path(path, source_paths, base_dir)
    if full_path is None:
        return format_error(f"file '{path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    structs = _extract_structs(source)

    if not structs:
        return format_error(f"no struct types found in '{path}'")

    if target:
        matched = next((s for s in structs if s["name"] == target), None)
        if matched is None:
            return format_error(
                f"struct '{target}' not found in '{path}'"
            )
        return _format_struct_table(matched)

    # No type specified: format all pub structs
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
    """Extract pub struct type declarations from Zig source.

    Returns a list of dicts: {name, doc, fields: [{name, type, default, comment}]}.
    """
    lines = source.split("\n")
    structs = []

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Match: pub const Name = struct {
        match = re.match(
            r"^pub\s+const\s+(\w+)\s*=\s*struct\s*\{", stripped
        )
        if match:
            struct_name = match.group(1)
            doc = _collect_doc_comment_above(lines, i)

            # Parse fields until closing brace (tracking brace depth)
            fields = []
            brace_depth = 1
            j = i + 1
            while j < len(lines) and brace_depth > 0:
                field_line = lines[j].strip()
                for ch in field_line:
                    if ch == "{":
                        brace_depth += 1
                    elif ch == "}":
                        brace_depth -= 1

                # Only parse fields at the top level of the struct
                if brace_depth == 1:
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
    """Parse a single Zig struct field line.

    Zig struct fields look like:
        name: Type = default, // comment
        name: Type, // comment
        name: Type = default,

    Returns {name, type, default, comment} or None if not a field.
    """
    # Skip blank lines, comments, and function declarations
    if not field_line or field_line.startswith("//") or field_line.startswith("pub ") or field_line.startswith("fn "):
        return None

    # Match field: name: Type [= default][,] [// comment]
    match = re.match(
        r"^(\w+)\s*:\s*"          # field name and type separator
        r"([^=,/]+?)"             # type
        r"(?:\s*=\s*([^,/]+?))?"  # optional default
        r"\s*,?\s*"               # optional trailing comma
        r"(?://\s*(.*))?"         # optional inline comment
        r"\s*$",
        field_line,
    )
    if not match:
        return None

    name = match.group(1)
    field_type = match.group(2).strip()
    default = (match.group(3) or "").strip()
    inline_comment = (match.group(4) or "").strip()

    # Also check for a /// doc comment above the field
    doc_above = _collect_doc_comment_above(lines, line_idx)
    description = inline_comment or doc_above

    return {
        "name": name,
        "type": field_type,
        "default": default,
        "comment": description,
    }


def _format_struct_table(struct_info):
    """Format a struct's fields as a markdown table."""
    rows = []

    for field in struct_info["fields"]:
        default_display = f"`{field['default']}`" if field["default"] else ""
        rows.append([
            f"`{field['name']}`",
            f"`{field['type']}`",
            default_display,
            field["comment"],
        ])

    return render_markdown_table(
        ["Field", "Type", "Default", "Description"], rows
    )


# ---------------------------------------------------------------------------
# :::code-test
# ---------------------------------------------------------------------------


def _handle_code_test(path, target, body, source_paths, base_dir, attrs):
    """Extract test blocks from Zig source.

    path is the file path, target is an optional test name.
    If target is provided, extracts only that test block.
    Otherwise, extracts all test blocks.
    """
    if not path:
        return format_error(":::code-test requires a file path argument")

    target_name = target.strip('"') if target else None

    full_path = _resolve_file_path(path, source_paths, base_dir)
    if full_path is None:
        return format_error(f"test file '{path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    if target_name is None:
        # Extract all test blocks
        tests = _extract_all_test_blocks(source)
        if not tests:
            return format_error(f"no test blocks found in '{path}'")
        results = []
        for test_name, test_source in tests:
            results.append(f"```zig\n{test_source}\n```")
        return "\n\n".join(results)

    # Extract specific test block
    extracted = _extract_test_block(source, target_name)
    if extracted is None:
        return format_error(f"test '{target_name}' not found in '{path}'")

    return f"```zig\n{extracted}\n```"


def _extract_test_block(source, test_name):
    """Extract a specific test block by name from Zig source.

    Matches: test "name" { ... }
    Uses brace counting to find the block boundaries.
    """
    lines = source.split("\n")
    # Build pattern to match test "name" {
    pattern = re.compile(
        rf'^test\s+"{re.escape(test_name)}"\s*\{{'
    )

    for i, line in enumerate(lines):
        stripped = line.strip()
        if pattern.match(stripped):
            # Find the end using brace counting
            brace_count = 0
            started = False
            for k in range(i, len(lines)):
                for ch in lines[k]:
                    if ch == "{":
                        brace_count += 1
                        started = True
                    elif ch == "}":
                        brace_count -= 1
                if started and brace_count == 0:
                    return "\n".join(lines[i : k + 1])

    return None


def _extract_all_test_blocks(source):
    """Extract all test blocks from Zig source.

    Returns list of (name, source) tuples.
    """
    lines = source.split("\n")
    tests = []
    test_re = re.compile(r'^test\s+"([^"]+)"\s*\{')

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        match = test_re.match(stripped)
        if match:
            test_name = match.group(1)
            brace_count = 0
            started = False
            for k in range(i, len(lines)):
                for ch in lines[k]:
                    if ch == "{":
                        brace_count += 1
                        started = True
                    elif ch == "}":
                        brace_count -= 1
                if started and brace_count == 0:
                    tests.append((test_name, "\n".join(lines[i : k + 1])))
                    i = k + 1
                    break
            else:
                i += 1
        else:
            i += 1

    return tests


ZigExtractor._HANDLERS = {
    "ref": _handle_ref,
    "prose-desc": _handle_prose_desc,
    "table-schema": _handle_table_schema,
    "code-test": _handle_code_test,
    "table-config": handle_table_config,
}
