"""Swift source extractor for selfdoc -- parses .swift files to extract public declarations, doc comments, and struct schemas for documentation pages.

Uses regex-based parsing (no Swift toolchain required). Handles:
- :::ref         -- extract module doc, public/open declarations with doc comments
- :::prose-desc  -- extract module-level /// doc comments only
- :::table-schema -- extract struct fields as a table
- :::table-config -- extract config file contents as tables (JSON/TOML)
"""

import os
import re

from selfdoc.extractors.base import (
    BaseExtractor,
    _format_docstring,
    collect_comment_lines_above,
    format_error,
    handle_table_config,
    read_source,
)
from selfdoc.tables import render_markdown_table

# ---------------------------------------------------------------------------
# Regex patterns for public/open Swift declarations
# ---------------------------------------------------------------------------

# public/open func name(
_SWIFT_FUNC_RE = re.compile(
    r"^(?:public|open)\s+(?:(?:static|class|final)\s+)*func\s+(\w+)"
)
# public/open class/struct/enum/protocol/actor name
_SWIFT_TYPE_RE = re.compile(
    r"^(?:public|open)\s+(?:final\s+)?(?:class|struct|enum|protocol|actor)\s+(\w+)"
)
# public typealias name
_SWIFT_TYPEALIAS_RE = re.compile(
    r"^(?:public|open)\s+typealias\s+(\w+)"
)
# public/open var/let name
_SWIFT_PROP_RE = re.compile(
    r"^(?:public|open)\s+(?:(?:static|class)\s+)?(?:var|let)\s+(\w+)"
)


class SwiftExtractor(BaseExtractor):
    """Swift language extractor implementing LanguageExtractor protocol."""

    @property
    def name(self) -> str:
        return "swift"

    def detect(self, dir_path: str) -> bool:
        return os.path.isfile(os.path.join(dir_path, "Package.swift"))

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None:
        return _resolve_swift_path(path_arg, source_paths, base_dir)

    def file_extensions(self) -> list[str]:
        return [".swift"]

    def public_symbols(self, file_path: str) -> list[str]:
        """Extract public/open symbols from a Swift source file.

        Handles public/open func, class, struct, enum, protocol, actor,
        typealias, var, and let. Skips comment-only lines.
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

            # Remove trailing inline comments
            comment_idx = stripped.find("//")
            if comment_idx >= 0:
                stripped = stripped[:comment_idx].strip()

            for pattern in (
                _SWIFT_FUNC_RE,
                _SWIFT_TYPE_RE,
                _SWIFT_TYPEALIAS_RE,
                _SWIFT_PROP_RE,
            ):
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
        """Extract detailed parameter and return info for a Swift function."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return None

        lines = source.split("\n")

        # Regex matching both public/open func and unmodified func
        func_re = re.compile(
            r"^(?:(?:public|open)\s+)?(?:(?:static|class|final)\s+)*func\s+"
            + re.escape(symbol_name)
            + r"\s*\("
        )

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if func_re.match(stripped):
                return _swift_symbol_details(lines, i)

        return None


# ---------------------------------------------------------------------------
# symbol_details helpers
# ---------------------------------------------------------------------------


def _parse_swift_params(param_str):
    """Parse Swift function parameter list into structured dicts.

    Takes the text between '(' and ')' of a Swift function signature.
    Swift params: ``func f(label name: Type, _ name: Type = default)``

    Returns list of {"name": str, "type": str|None}.
    """
    params = []
    if not param_str.strip():
        return params

    # Split on commas respecting nested brackets/parens/generics
    parts = _split_swift_params(param_str)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Strip default value: everything after top-level '='
        eq_idx = _find_top_level_char(part, "=")
        if eq_idx >= 0:
            part = part[:eq_idx].strip()

        # Split on ':' to separate name(s) from type
        colon_idx = _find_top_level_char(part, ":")
        if colon_idx < 0:
            # No type annotation (unusual but possible in closures)
            name = part.strip()
            if name == "self":
                continue
            params.append({"name": name, "type": None})
            continue

        name_part = part[:colon_idx].strip()
        type_part = part[colon_idx + 1:].strip()

        # Parse name_part: could be "label name", "_ name", or just "name"
        tokens = name_part.split()
        if len(tokens) == 2:
            # (label name) or (_ name) -- use the internal name (second)
            name = tokens[1]
        elif len(tokens) == 1:
            name = tokens[0]
        else:
            # Unusual, take the last token
            name = tokens[-1] if tokens else name_part

        if name == "self":
            continue

        # Clean type: strip @escaping, @autoclosure etc. but keep them
        # as part of the type for accuracy
        param_type = type_part if type_part else None

        params.append({"name": name, "type": param_type})

    return params


def _split_swift_params(s):
    """Split a Swift parameter string on commas, respecting nested brackets."""
    parts = []
    depth = 0
    current = []
    for ch in s:
        if ch in "(<[":
            depth += 1
            current.append(ch)
        elif ch in ")>]":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _find_top_level_char(s, char):
    """Find the first occurrence of char at nesting depth 0."""
    depth = 0
    for i, ch in enumerate(s):
        if ch in "(<[":
            depth += 1
        elif ch in ")>]":
            depth -= 1
        elif ch == char and depth == 0:
            return i
    return -1


def _extract_swift_doc_param_names(doc_text):
    """Extract parameter names documented in Swift doc comments.

    Handles both:
    - ``- Parameter name: desc`` (individual syntax)
    - ``- Parameters:`` block with ``  - name: desc`` sub-items
    """
    names = set()
    if not doc_text:
        return names

    lines = doc_text.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Individual: - Parameter name: desc
        m = re.match(r"^-\s+Parameter\s+(\w+)\s*:", stripped)
        if m:
            names.add(m.group(1))
            i += 1
            continue

        # Block: - Parameters:
        if re.match(r"^-\s+Parameters\s*:", stripped):
            i += 1
            while i < len(lines):
                sub_stripped = lines[i].strip()
                sub_m = re.match(r"^-\s+(\w+)\s*:", sub_stripped)
                if sub_m and len(lines[i]) > len(lines[i].lstrip()):
                    names.add(sub_m.group(1))
                    i += 1
                elif not sub_stripped:
                    i += 1
                else:
                    break
            continue

        i += 1

    return names


def _has_swift_return_doc(doc_text):
    """Check whether Swift doc text contains a ``- Returns:`` tag."""
    if not doc_text:
        return False
    return bool(re.search(r"^-\s+Returns\s*:", doc_text, re.MULTILINE))


def _extract_swift_return_type(signature):
    """Extract the return type from a Swift function signature.

    Looks for ``-> ReturnType`` after the closing ``)`` of the parameter list.
    """
    # Find the last ')' that closes the parameter list
    paren_depth = 0
    last_close = -1
    for idx, ch in enumerate(signature):
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
            if paren_depth == 0:
                last_close = idx
                break

    if last_close < 0:
        return None

    after_params = signature[last_close + 1:].strip()

    # Handle throws/rethrows before return type
    after_params = re.sub(r"^(?:throws|rethrows)\s*", "", after_params).strip()

    # Look for -> ReturnType
    arrow_match = re.match(r"^->\s*(.+)$", after_params)
    if not arrow_match:
        return None

    return_type = arrow_match.group(1).strip()
    # Remove trailing { or where clause
    return_type = re.sub(r"\s*\{.*$", "", return_type).strip()
    return_type = re.sub(r"\s+where\s+.*$", "", return_type).strip()

    return return_type if return_type else None


def _swift_symbol_details(lines, decl_line_idx):
    """Build symbol_details dict for a Swift function declaration."""
    sig = _extract_func_signature(lines, decl_line_idx)
    doc_text = collect_comment_lines_above(
        lines, decl_line_idx, "///", skip_blank_lines=False
    )

    # Extract params from signature
    paren_start = sig.find("(")
    if paren_start < 0:
        return {
            "params": [],
            "return_type": _extract_swift_return_type(sig),
            "return_documented": _has_swift_return_doc(doc_text),
        }

    # Find matching close paren
    paren_depth = 0
    paren_end = -1
    for idx in range(paren_start, len(sig)):
        if sig[idx] == "(":
            paren_depth += 1
        elif sig[idx] == ")":
            paren_depth -= 1
            if paren_depth == 0:
                paren_end = idx
                break

    if paren_end < 0:
        inner = sig[paren_start + 1:]
    else:
        inner = sig[paren_start + 1:paren_end]

    documented_names = _extract_swift_doc_param_names(doc_text)
    parsed_params = _parse_swift_params(inner)

    params = []
    for p in parsed_params:
        params.append({
            "name": p["name"],
            "type": p["type"],
            "documented": p["name"] in documented_names,
        })

    return {
        "params": params,
        "return_type": _extract_swift_return_type(sig),
        "return_documented": _has_swift_return_doc(doc_text),
    }


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _resolve_swift_path(path_arg, source_paths, base_dir):
    """Resolve a path argument to a Swift source file or directory.

    Tries each source_path prefix, then the base_dir directly.
    Checks for both directories containing .swift files and direct .swift files.
    """
    candidates = []
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, path_arg))
    candidates.append(os.path.join(base_dir, path_arg))

    for candidate in candidates:
        if os.path.isdir(candidate):
            if any(f.endswith(".swift") for f in os.listdir(candidate)):
                return candidate
        if os.path.isfile(candidate):
            return candidate
        # Try appending .swift extension
        swift_candidate = candidate + ".swift"
        if os.path.isfile(swift_candidate):
            return swift_candidate

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
# Module doc extraction (/// comments at the top of the file)
# ---------------------------------------------------------------------------


def _extract_module_doc(source):
    """Extract module-level doc comments (/// lines) from Swift source.

    Module doc in Swift: /// comments at the very top of the file before any
    declaration or import statement. Stops at the first non-comment, non-blank
    line.

    Returns the doc text with /// prefixes stripped.
    """
    lines = source.split("\n")
    doc_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("///"):
            text = stripped[3:]
            if text.startswith(" "):
                text = text[1:]
            doc_lines.append(text)
        elif doc_lines:
            # Module doc is contiguous at the top; stop after first non-/// line
            break
        elif stripped and not stripped.startswith("//"):
            # Non-comment, non-blank line before any /// -- no module doc
            break

    return "\n".join(doc_lines) if doc_lines else ""


# ---------------------------------------------------------------------------
# Swift doc comment processing
# ---------------------------------------------------------------------------

# Callout keywords recognized in Swift doc comments
_SWIFT_CALLOUT_KEYWORDS = {
    "Note",
    "Warning",
    "Important",
    "Precondition",
    "Postcondition",
    "Complexity",
    "SeeAlso",
    "Remark",
    "Requires",
    "Version",
    "Author",
    "Since",
    "Attention",
    "Bug",
    "Experiment",
    "TODO",
}

# Double backtick to single backtick: ``Symbol`` -> `Symbol`
_DOUBLE_BACKTICK_RE = re.compile(r"``(\w+)``")


def _parse_swift_doc_comment(text):
    """Process Swift doc comment text into markdown.

    Handles Swift-specific doc comment syntax:
    - ``Symbol`` (double backtick) -> `Symbol` (single backtick)
    - ``- Parameter name: desc`` -> collected into a Parameters section
    - ``- Parameters:`` block with indented ``  - name: desc`` lines
    - ``- Returns: desc`` -> ``**Returns:** desc``
    - ``- Throws: desc`` -> ``**Throws:** desc``
    - Callout keywords (Note, Warning, etc.) -> ``**Keyword:** content``
    - All other lines pass through unchanged

    The result is then passed through _format_docstring for general formatting.
    """
    if not text:
        return ""

    # Convert double backticks to single backticks throughout
    text = _DOUBLE_BACKTICK_RE.sub(r"`\1`", text)

    lines = text.split("\n")
    out = []
    params = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # - Parameter name: desc (individual parameter syntax)
        param_match = re.match(
            r"^-\s+Parameter\s+(\w+)\s*:\s*(.*)", stripped
        )
        if param_match:
            param_name = param_match.group(1)
            param_desc = param_match.group(2).strip()
            # Collect continuation lines (indented lines following)
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                if not next_stripped or next_stripped.startswith("- "):
                    break
                # Continuation line -- must be indented relative to the parameter
                next_line = lines[i]
                if len(next_line) > len(next_line.lstrip()):
                    param_desc += " " + next_stripped
                    i += 1
                else:
                    break
            params.append((param_name, param_desc))
            continue

        # - Parameters: (block syntax with indented sub-items)
        if re.match(r"^-\s+Parameters\s*:", stripped):
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                # Indented sub-item: - name: desc
                sub_match = re.match(r"^-\s+(\w+)\s*:\s*(.*)", next_stripped)
                if sub_match and (
                    len(lines[i]) - len(lines[i].lstrip()) > 0
                ):
                    sub_name = sub_match.group(1)
                    sub_desc = sub_match.group(2).strip()
                    # Collect continuation lines
                    i += 1
                    while i < len(lines):
                        cont_stripped = lines[i].strip()
                        if not cont_stripped or cont_stripped.startswith("- "):
                            break
                        cont_line = lines[i]
                        if len(cont_line) > len(cont_line.lstrip()):
                            sub_desc += " " + cont_stripped
                            i += 1
                        else:
                            break
                    params.append((sub_name, sub_desc))
                elif not next_stripped:
                    # Blank line within parameters block -- skip
                    i += 1
                else:
                    # Non-indented or non-matching line -- end of Parameters block
                    break
            continue

        # - Returns: desc
        returns_match = re.match(r"^-\s+Returns\s*:\s*(.*)", stripped)
        if returns_match:
            # Flush any pending params first
            if params:
                _flush_params(out, params)
                params = []
            desc = returns_match.group(1).strip()
            i += 1
            # Collect continuation lines
            while i < len(lines):
                next_stripped = lines[i].strip()
                if not next_stripped or next_stripped.startswith("- "):
                    break
                next_line = lines[i]
                if len(next_line) > len(next_line.lstrip()):
                    desc += " " + next_stripped
                    i += 1
                else:
                    break
            out.append(f"**Returns:** {desc}")
            continue

        # - Throws: desc
        throws_match = re.match(r"^-\s+Throws\s*:\s*(.*)", stripped)
        if throws_match:
            if params:
                _flush_params(out, params)
                params = []
            desc = throws_match.group(1).strip()
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                if not next_stripped or next_stripped.startswith("- "):
                    break
                next_line = lines[i]
                if len(next_line) > len(next_line.lstrip()):
                    desc += " " + next_stripped
                    i += 1
                else:
                    break
            out.append(f"**Throws:** {desc}")
            continue

        # Callout keywords: - Note: content, - Warning: content, etc.
        callout_match = re.match(r"^-\s+(\w+)\s*:\s*(.*)", stripped)
        if callout_match and callout_match.group(1) in _SWIFT_CALLOUT_KEYWORDS:
            if params:
                _flush_params(out, params)
                params = []
            keyword = callout_match.group(1)
            content = callout_match.group(2).strip()
            i += 1
            while i < len(lines):
                next_stripped = lines[i].strip()
                if not next_stripped or next_stripped.startswith("- "):
                    break
                next_line = lines[i]
                if len(next_line) > len(next_line.lstrip()):
                    content += " " + next_stripped
                    i += 1
                else:
                    break
            out.append(f"**{keyword}:** {content}")
            continue

        # Regular line -- flush params if pending, then pass through
        if params:
            _flush_params(out, params)
            params = []
        out.append(line)
        i += 1

    # Flush any remaining params
    if params:
        _flush_params(out, params)

    return "\n".join(out)


def _flush_params(out, params):
    """Flush accumulated parameter entries as a formatted section."""
    if out and out[-1] != "":
        out.append("")
    out.append("**Parameters:**")
    out.append("")
    for param_name, param_desc in params:
        if param_desc:
            out.append(f"- `{param_name}`: {param_desc}")
        else:
            out.append(f"- `{param_name}`")
    out.append("")
    params.clear()


# ---------------------------------------------------------------------------
# Public declaration extraction
# ---------------------------------------------------------------------------


def _extract_pub_declarations(source):
    """Extract all public/open declarations from Swift source.

    Returns a list of dicts with keys: kind, name, signature, doc.
    kind is one of: "type", "func", "prop".
    """
    lines = source.split("\n")
    declarations = []
    seen_names = set()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip comment-only lines
        if stripped.startswith("//"):
            continue

        # Skip blank lines
        if not stripped:
            continue

        # Type declarations: class, struct, enum, protocol, actor, typealias
        type_match = _SWIFT_TYPE_RE.match(stripped)
        if type_match:
            type_name = type_match.group(1)
            sig = _clean_type_signature(stripped)
            doc_text = collect_comment_lines_above(
                lines, i, "///", skip_blank_lines=False
            )
            doc = _parse_swift_doc_comment(doc_text)

            if type_name not in seen_names:
                seen_names.add(type_name)
                declarations.append({
                    "kind": "type",
                    "name": type_name,
                    "signature": sig,
                    "doc": doc,
                })
            continue

        typealias_match = _SWIFT_TYPEALIAS_RE.match(stripped)
        if typealias_match:
            alias_name = typealias_match.group(1)
            sig = stripped.rstrip()
            doc_text = collect_comment_lines_above(
                lines, i, "///", skip_blank_lines=False
            )
            doc = _parse_swift_doc_comment(doc_text)

            if alias_name not in seen_names:
                seen_names.add(alias_name)
                declarations.append({
                    "kind": "type",
                    "name": alias_name,
                    "signature": sig,
                    "doc": doc,
                })
            continue

        # Function declarations
        func_match = _SWIFT_FUNC_RE.match(stripped)
        if func_match:
            func_name = func_match.group(1)
            sig = _extract_func_signature(lines, i)
            doc_text = collect_comment_lines_above(
                lines, i, "///", skip_blank_lines=False
            )
            doc = _parse_swift_doc_comment(doc_text)

            if func_name not in seen_names:
                seen_names.add(func_name)
                declarations.append({
                    "kind": "func",
                    "name": func_name,
                    "signature": sig,
                    "doc": doc,
                })
            continue

        # Property declarations (var/let)
        prop_match = _SWIFT_PROP_RE.match(stripped)
        if prop_match:
            prop_name = prop_match.group(1)
            sig = _clean_prop_signature(stripped)
            doc_text = collect_comment_lines_above(
                lines, i, "///", skip_blank_lines=False
            )
            doc = _parse_swift_doc_comment(doc_text)

            if prop_name not in seen_names:
                seen_names.add(prop_name)
                declarations.append({
                    "kind": "prop",
                    "name": prop_name,
                    "signature": sig,
                    "doc": doc,
                })
            continue

    return declarations


def _extract_func_signature(lines, start_idx):
    """Extract a function signature from the declaration line.

    Collects lines until the opening brace or end of parameters,
    then strips the function body.
    """
    sig_parts = []
    for i in range(start_idx, min(start_idx + 10, len(lines))):
        line = lines[i].strip()
        sig_parts.append(line)
        if "{" in line:
            break
        # If line ends with return type and no brace, stop
        if i > start_idx and not line.endswith(",") and not line.endswith("("):
            break

    sig = " ".join(sig_parts)
    # Remove trailing body opener
    sig = re.sub(r"\s*\{.*$", "", sig)
    return sig.rstrip()


def _clean_type_signature(line):
    """Clean a type declaration line for display.

    Strips trailing body opener brace and inheritance/conformance details
    are kept for context.
    """
    line = re.sub(r"\s*\{[^}]*$", "", line)
    return line.rstrip()


def _clean_prop_signature(line):
    """Clean a property declaration line for display.

    Strips trailing body opener brace (for computed properties).
    """
    line = re.sub(r"\s*\{[^}]*$", "", line)
    return line.rstrip()


# ---------------------------------------------------------------------------
# :::ref
# ---------------------------------------------------------------------------


def _handle_ref(path, target, body, source_paths, base_dir, attrs):
    """Extract module doc and all public/open declarations with their doc comments.

    path is a file path (e.g. "Sources/Core/Parser.swift") or a directory path.
    """
    if not path:
        return format_error(":::ref requires a file path argument")

    resolved = _resolve_swift_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    # If it's a directory, collect all .swift files
    if os.path.isdir(resolved):
        swift_files = sorted(
            f for f in os.listdir(resolved) if f.endswith(".swift")
        )
        if not swift_files:
            return format_error(f"no .swift files in '{path}'")
        file_contents = {}
        for sf in swift_files:
            sf_path = os.path.join(resolved, sf)
            content, _err = read_source(sf_path)
            file_contents[sf] = content if content is not None else ""
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

    # Extract public/open declarations from all files
    declarations = []
    for _filename in sorted(file_contents.keys()):
        source = file_contents[_filename]
        declarations.extend(_extract_pub_declarations(source))

    # Group by kind: types first, then functions, then properties
    kind_order = ["type", "func", "prop"]
    for kind in kind_order:
        kind_decls = [d for d in declarations if d["kind"] == kind]
        for decl in kind_decls:
            parts.append("")
            parts.append(f"### {decl['name']}")
            parts.append("")
            parts.append(f"```swift\n{decl['signature']}\n```")
            if decl["doc"]:
                parts.append("")
                parts.append(decl["doc"])

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# :::prose-desc
# ---------------------------------------------------------------------------


def _handle_prose_desc(path, target, body, source_paths, base_dir, attrs):
    """Extract only the module-level /// doc comments as prose markdown."""
    if not path:
        return format_error(":::prose-desc requires a file path argument")

    resolved = _resolve_swift_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    if os.path.isdir(resolved):
        # Try each .swift file for module doc
        swift_files = sorted(
            f for f in os.listdir(resolved) if f.endswith(".swift")
        )
        for sf in swift_files:
            content, _err = read_source(os.path.join(resolved, sf))
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

    path is the file path, target is the optional struct name.
    """
    if not path:
        return format_error(":::table-schema requires a file path argument")

    # JSON/TOML files are config files, not Swift source -- delegate
    if path.endswith((".json", ".toml")):
        return handle_table_config(path, None, body, source_paths, base_dir, attrs)

    full_path = _resolve_file_path(path, source_paths, base_dir)
    if full_path is None:
        return format_error(f"file '{path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    structs = _extract_struct_fields(source)

    if not structs:
        return format_error(f"no struct types found in '{path}'")

    if target:
        matched = next((s for s in structs if s["name"] == target), None)
        if matched is None:
            return format_error(
                f"struct '{target}' not found in '{path}'"
            )
        return _format_struct_table(matched)

    # No type specified: format all public structs
    results = []
    for s in structs:
        results.append(f"### {s['name']}")
        results.append("")
        if s["doc"]:
            results.append(s["doc"])
            results.append("")
        results.append(_format_struct_table(s))
    return "\n".join(results)


# ---------------------------------------------------------------------------
# Struct field extraction
# ---------------------------------------------------------------------------


def _extract_struct_fields(source, struct_name=None):
    """Extract struct declarations and their fields from Swift source.

    Finds public struct blocks and parses fields within. Fields inside a
    public struct don't need the public keyword themselves.

    If struct_name is provided, only extracts that specific struct.

    Returns a list of dicts: {name, doc, fields: [{name, type, default, comment}]}.
    """
    lines = source.split("\n")
    structs = []

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Match: public struct Name { or public struct Name: Protocol {
        match = re.match(
            r"^(?:public|open)\s+(?:final\s+)?struct\s+(\w+)\s*(?::[^{]*)?\s*\{",
            stripped,
        )
        if match:
            name = match.group(1)

            if struct_name is not None and name != struct_name:
                i += 1
                continue

            doc_text = collect_comment_lines_above(
                lines, i, "///", skip_blank_lines=False
            )
            doc = _parse_swift_doc_comment(doc_text)

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

            structs.append({"name": name, "doc": doc, "fields": fields})

        i += 1

    return structs


def _parse_struct_field(field_line, lines, line_idx):
    """Parse a single Swift struct field line.

    Swift struct fields look like:
        public var name: String = "default"
        public let count: Int
        var name: String = "default"  // inside public struct
        let count: Int

    Returns {name, type, default, comment} or None if not a field.
    """
    # Skip blank lines, comments, and function/type declarations
    if (
        not field_line
        or field_line.startswith("//")
        or field_line.startswith("func ")
        or field_line.startswith("public func ")
        or field_line.startswith("open func ")
        or field_line.startswith("private ")
        or field_line.startswith("internal ")
        or field_line.startswith("init(")
        or field_line.startswith("public init(")
        or field_line.startswith("case ")
    ):
        return None

    # Match field: [public|open] (var|let) name: Type [= default] [// comment]
    match = re.match(
        r"^(?:(?:public|open)\s+)?"  # optional access modifier
        r"(?:(?:static|class)\s+)?"  # optional static/class
        r"(var|let)\s+"  # var or let
        r"(\w+)\s*:\s*"  # field name
        r"([^=/{]+?)"  # type
        r"(?:\s*=\s*([^/{]*?))?"  # optional default value
        r"\s*"
        r"(?://\s*(.*))?"  # optional inline comment
        r"\s*$",
        field_line,
    )
    if not match:
        return None

    name = match.group(2)
    field_type = match.group(3).strip()
    default = (match.group(4) or "").strip()
    inline_comment = (match.group(5) or "").strip()

    # Also check for a /// doc comment above the field
    doc_above = collect_comment_lines_above(
        lines, line_idx, "///", skip_blank_lines=False
    )
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
# Handler registration
# ---------------------------------------------------------------------------

SwiftExtractor._HANDLERS = {
    "ref": _handle_ref,
    "prose-desc": _handle_prose_desc,
    "table-schema": _handle_table_schema,
    "table-config": handle_table_config,
}
