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

from selfdoc.tables import render_markdown_table
from selfdoc.extractors.base import (
    BaseExtractor,
    _format_docstring,
    format_error,
    handle_table_config,
    read_source,
)

# Patterns for exported Go symbols (used by GoExtractor.public_symbols)
_GO_FUNC_RE = re.compile(r"^func\s+([A-Z]\w*)\s*\(")
_GO_METHOD_RE = re.compile(r"^func\s+\(\s*\w+\s+\*?(\w+)\s*\)\s+([A-Z]\w*)\s*\(")
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

    def file_extensions(self) -> list[str]:
        return [".go"]

    def module_docstring(self, path: str) -> str:
        """Extract package-level doc comment from a Go package.

        path may be a directory (Go's resolve_path returns directories)
        or a single .go file. For directories, reads all non-test .go
        files and passes them to _extract_package_doc.
        """
        if os.path.isdir(path):
            pkg_dir = path
        elif os.path.isfile(path):
            pkg_dir = os.path.dirname(path)
        else:
            return ""
        file_contents = {}
        try:
            for name in os.listdir(pkg_dir):
                if name.endswith(".go") and not name.endswith("_test.go"):
                    full = os.path.join(pkg_dir, name)
                    try:
                        with open(full, "r", encoding="utf-8") as f:
                            file_contents[name] = f.read()
                    except (OSError, UnicodeDecodeError):
                        continue
        except OSError:
            return ""
        if not file_contents:
            return ""
        _pkg_name, doc = _extract_package_doc(file_contents)
        return doc

    def public_symbols(self, file_path: str) -> list[str]:
        """Extract exported (capitalized) symbols from a Go source file.

        Skips lines inside // and /* */ comments.
        Handles const (...) and var (...) blocks.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        lines = source.split("\n")
        symbols = []
        in_block_comment = False
        in_const_var_block = False

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

            # Track const/var block boundaries
            if not in_const_var_block:
                if stripped == "const (" or stripped.startswith("const ("):
                    in_const_var_block = True
                    continue
                if stripped == "var (" or stripped.startswith("var ("):
                    in_const_var_block = True
                    continue

            if in_const_var_block:
                if stripped == ")" or stripped.startswith(")"):
                    in_const_var_block = False
                    continue
                # Inside a block: exported symbol starts with uppercase
                m = re.match(r"^([A-Z]\w*)", stripped)
                if m:
                    sym_name = m.group(1)
                    if sym_name not in symbols:
                        symbols.append(sym_name)
                continue

            for pattern in (
                _GO_METHOD_RE,
                _GO_FUNC_RE,
                _GO_TYPE_RE,
                _GO_VAR_RE,
                _GO_CONST_RE,
            ):
                m = pattern.match(stripped)
                if m:
                    if pattern is _GO_METHOD_RE:
                        sym_name = f"{m.group(1)}.{m.group(2)}"
                    else:
                        sym_name = m.group(1)
                    if sym_name not in symbols:
                        symbols.append(sym_name)
                    break

        return symbols

    def symbol_details(self, file_path: str, symbol_name: str) -> dict | None:
        """Extract parameter and return type details for a Go function/method.

        file_path may be a directory (Go's resolve_path returns directories)
        or a single .go file. For directories, scans all non-test .go files.

        Supports dotted names (e.g., "Server.Handle") to target a method
        with a specific receiver type.
        """
        # Dotted name: split into receiver type and method name
        if "." in symbol_name:
            type_name, method_name = symbol_name.rsplit(".", 1)
        else:
            type_name, method_name = None, symbol_name

        if os.path.isdir(file_path):
            try:
                go_files = sorted(
                    os.path.join(file_path, f)
                    for f in os.listdir(file_path)
                    if f.endswith(".go") and not f.endswith("_test.go")
                )
            except OSError:
                return None
        elif os.path.isfile(file_path):
            go_files = [file_path]
        else:
            return None

        for gf in go_files:
            try:
                with open(gf, "r", encoding="utf-8") as f:
                    source = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            lines = source.split("\n")
            for i, line in enumerate(lines):
                stripped = line.strip()
                if type_name is not None:
                    # Dotted target: match method with specific receiver type
                    m = re.match(
                        r"^func\s+\(\s*\w+\s+\*?(\w+)\s*\)\s+"
                        + re.escape(method_name)
                        + r"\s*\(",
                        stripped,
                    )
                    if m and m.group(1) == type_name:
                        return _go_symbol_details(lines, i)
                else:
                    # Plain name: match any function/method with this name
                    if re.match(
                        rf"^func\s+(?:\(.*?\)\s+)?{re.escape(method_name)}\s*\(",
                        stripped,
                    ):
                        return _go_symbol_details(lines, i)

        return None


# ---------------------------------------------------------------------------
# symbol_details helpers
# ---------------------------------------------------------------------------


def _go_symbol_details(lines, decl_line_idx):
    """Build a symbol_details dict from a Go function declaration line.

    Parses the function signature for parameters and return type,
    and checks the doc comment for parameter/return documentation.
    """
    # Collect the full signature (may span multiple lines)
    sig = lines[decl_line_idx].strip()
    # If the signature doesn't contain the opening brace or a closing paren
    # for the return type, it may span multiple lines
    j = decl_line_idx + 1
    while j < len(lines) and "{" not in sig and not sig.rstrip().endswith(")"):
        sig += " " + lines[j].strip()
        j += 1
    # Include one more line if we still haven't found the opening brace
    if j < len(lines) and "{" not in sig:
        sig += " " + lines[j].strip()

    # Collect doc comment above
    doc_text = _collect_comment_block_above(lines, decl_line_idx)

    # Strip receiver: func (x *Type) Name(...) -> find Name(
    # We need to find the parameter list, skipping the receiver
    m = re.match(
        r"^func\s+"
        r"(?:\([^)]*\)\s+)?"  # optional receiver
        r"\w+\s*"             # function name
        r"\((.*)",            # opening paren + rest
        sig,
    )
    if not m:
        return {"params": [], "return_type": None, "return_documented": False}

    rest = m.group(1)

    # Find the matching close paren for the param list
    param_str, after_params = _split_at_matching_paren(rest)

    # Parse parameters
    params = _parse_go_params(param_str)

    # Check documentation for each param
    for p in params:
        p["documented"] = bool(
            doc_text and re.search(rf"\b{re.escape(p['name'])}\b", doc_text)
        )

    # Parse return type from after_params
    return_type = _extract_go_return_type(after_params)

    # Check if return is documented
    return_documented = bool(
        doc_text and re.search(r"\breturn", doc_text, re.IGNORECASE)
    )

    return {
        "params": params,
        "return_type": return_type,
        "return_documented": return_documented,
    }


def _split_at_matching_paren(s):
    """Split string at the matching closing paren.

    Given the content after the opening '(' of the param list,
    returns (param_content, rest_after_close_paren).
    """
    depth = 1
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return s[:i], s[i + 1:]
    return s, ""


def _parse_go_params(param_str):
    """Parse a Go parameter list string into a list of param dicts.

    Handles grouped params (a, b int), variadic (...Type),
    pointer types (*Type), and qualified types (pkg.Type).
    """
    param_str = param_str.strip()
    if not param_str:
        return []

    # Split on commas, respecting parentheses depth (for func types)
    segments = _split_go_params(param_str)

    # Parse each segment into (names, type_str) pairs
    # Process right-to-left to propagate types for grouped params
    parsed = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        # Try to split into name + type
        name, type_str = _parse_go_param_segment(seg)
        parsed.append((name, type_str))

    # Right-to-left type propagation for grouped params
    # e.g., "a, b int, sep string" -> segments: ["a", "b int", "sep string"]
    # "a" has no type, "b int" has type "int", so "a" gets "int"
    current_type = None
    for i in range(len(parsed) - 1, -1, -1):
        name, type_str = parsed[i]
        if type_str is not None:
            current_type = type_str
        else:
            type_str = current_type
        parsed[i] = (name, type_str)

    return [
        {"name": name, "type": type_str}
        for name, type_str in parsed
    ]


def _split_go_params(param_str):
    """Split a Go parameter string by commas, respecting parentheses."""
    segments = []
    depth = 0
    current = []
    for ch in param_str:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            segments.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        segments.append("".join(current))
    return segments


def _parse_go_param_segment(seg):
    """Parse a single Go parameter segment into (name, type_str | None).

    A segment is either:
    - "name Type" (has both) -> ("name", "Type")
    - "name" (type comes from next group) -> ("name", None)
    - "name ...Type" (variadic) -> ("name", "...Type")
    """
    seg = seg.strip()
    # Variadic: "name ...Type"
    m = re.match(r"^(\w+)\s+(\.\.\.[\w.*\[\]]+)$", seg)
    if m:
        return m.group(1), m.group(2)

    # "name Type" where Type can be *pkg.Type, []Type, map[K]V, func(...), etc.
    # Strategy: first token is the name, rest is the type
    parts = seg.split(None, 1)
    if len(parts) == 2:
        name_candidate, type_candidate = parts
        # Verify the first part looks like a Go identifier (not a type)
        # Types start with *, [, map, func, chan, interface, struct, or uppercase
        # Names are lowercase identifiers
        if re.match(r"^[a-z_]\w*$", name_candidate):
            return name_candidate, type_candidate
        # If the whole thing looks like a single type (unnamed param),
        # this shouldn't happen for exported functions normally
        return name_candidate, type_candidate

    # Single token: just a name (type comes from the next group)
    return seg, None


def _extract_go_return_type(after_params):
    """Extract the return type from the text after the param closing paren.

    Examples:
    - " int {" -> "int"
    - " (int, error) {" -> "(int, error)"
    - " {" -> None (no return type)
    - "" -> None
    """
    s = after_params.strip()
    if not s or s.startswith("{"):
        return None

    # Multiple/named returns: (...)
    if s.startswith("("):
        # Find matching close paren
        depth = 0
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return s[: i + 1]
        return None

    # Single return type: everything before '{'
    brace_idx = s.find("{")
    if brace_idx >= 0:
        return s[:brace_idx].strip() or None
    return s.strip() or None


# ---------------------------------------------------------------------------
# :::module
# ---------------------------------------------------------------------------


def _handle_module(path, target, body, source_paths, base_dir, attrs):
    """Extract package doc, exported funcs, types, consts, and vars.

    path is a package directory path (e.g. "internal/commit").
    Finds all .go files in that directory (excluding _test.go),
    extracts the package doc comment and all exported declarations.
    """
    if not path:
        return format_error(":::module requires a package path argument")

    pkg_dir = _resolve_package_dir(path, source_paths, base_dir)
    if pkg_dir is None:
        return format_error(f"package '{path}' not found")

    # Collect all non-test .go files
    go_files = sorted(
        f
        for f in os.listdir(pkg_dir)
        if f.endswith(".go") and not f.endswith("_test.go")
    )

    if not go_files:
        return format_error(f"no .go files in '{path}'")

    # Read all files and concatenate for processing
    file_contents = {}
    for gf in go_files:
        file_path = os.path.join(pkg_dir, gf)
        content, _err = read_source(file_path)
        file_contents[gf] = content if content is not None else ""

    # Extract package doc from the first file that has a package declaration
    package_name, package_doc = _extract_package_doc(file_contents)

    parts = []
    parts.append(f"## {path}")

    if package_doc:
        parts.append("")
        parts.append(_format_docstring(package_doc))

    # Extract exported declarations from all files
    declarations = []
    for gf in go_files:
        source = file_contents.get(gf, "")
        declarations.extend(_extract_exported_declarations(source))

    if target:
        matched = [d for d in declarations if d["name"] == target]
        if not matched:
            return format_error(f"symbol '{target}' not found in '{path}'")
        decl = matched[0]
        parts_t = []
        parts_t.append(f"### {decl['name']}")
        parts_t.append("")
        parts_t.append(f"```go\n{decl['signature']}\n```")
        if decl["doc"]:
            parts_t.append("")
            parts_t.append(_format_docstring(decl["doc"]))
        return "\n".join(parts_t)

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


def _handle_test(path, target, body, source_paths, base_dir, attrs):
    """Extract test source code from a Go test file.

    path: file path to the test file
    target: optional test function name to extract
    """
    if not path:
        return format_error(":::test requires a file path argument")

    full_path = _resolve_file_path(path, source_paths, base_dir)
    if full_path is None:
        return format_error(f"test file '{path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    if target is None:
        return f"```go\n{source.rstrip()}\n```"

    # Extract the specific test function
    extracted = _extract_go_function(source, target)
    if extracted is None:
        return format_error(f"'{target}' not found in '{path}'")

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


def _handle_schema(path, target, body, source_paths, base_dir, attrs):
    """Extract struct type fields as a markdown table.

    path: file path to the Go source or config file
    target: optional struct type name to extract
    If target is omitted, extracts the first exported struct found.
    """
    if not path:
        return format_error(":::schema requires a file path argument")

    # JSON/TOML/YAML files are config files, not Go source -- delegate
    if path.endswith((".json", ".toml", ".yaml", ".yml")):
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
        match = next((s for s in structs if s["name"] == target), None)
        if match is None:
            return format_error(
                f"struct '{target}' not found in '{path}'"
            )
        return _format_struct_table(match)

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
    headers = ["Field", "Type", "Tag", "Description"]
    rows = []
    for field in struct_info["fields"]:
        tag_display = f"`{field['tag']}`" if field["tag"] else ""
        rows.append([
            f"`{field['name']}`",
            f"`{field['type']}`",
            tag_display,
            field["comment"],
        ])
    return render_markdown_table(headers, rows)


# ---------------------------------------------------------------------------
# :::cli
# ---------------------------------------------------------------------------


def _handle_cli(path, target, body, source_paths, base_dir, attrs):
    """Extract CLI usage/help text and flag definitions from Go source.

    Looks for:
    - String constants named usage, helpText, usageText (case-insensitive match)
    - flag.StringVar, flag.BoolVar, etc. calls
    - strictcli BoolFlag/StringFlag/Command calls

    path can be a file path or a package directory path (like :::module).
    Resolves via _resolve_package_dir first, then _resolve_file_path as fallback.
    """
    if not path:
        return format_error(":::cli requires a file path argument")

    # Try resolving as a package directory first (handles "." and package paths)
    pkg_dir = _resolve_package_dir(path, source_paths, base_dir)
    if pkg_dir is not None:
        # Read all non-test .go files in the package
        go_files = sorted(
            f
            for f in os.listdir(pkg_dir)
            if f.endswith(".go") and not f.endswith("_test.go")
        )
        sources = []
        for gf in go_files:
            content, _err = read_source(os.path.join(pkg_dir, gf))
            if content is not None:
                sources.append(content)
        source = "\n".join(sources)
    else:
        # Fall back to single file resolution
        full_path = _resolve_file_path(path, source_paths, base_dir)
        if full_path is None:
            return format_error(f"file '{path}' not found")

        source, err = read_source(full_path)
        if err:
            return format_error(f"cannot read '{path}': {err}")

    parts = []

    # Extract usage/help text constants
    usage_text = _extract_usage_constants(source)
    if usage_text:
        for name, text in usage_text:
            parts.append(f"**{name}:**")
            parts.append("")
            parts.append(f"```\n{text.strip()}\n```")

    # Extract flag definitions (stdlib flag package)
    flags = _extract_flag_calls(source)

    # Extract strictcli flag and command definitions
    strictcli_flags = _extract_strictcli_flags(source)
    flags.extend(strictcli_flags)

    if flags:
        parts.append("")
        parts.append("**Flags:**")
        parts.append("")
        flag_rows = []
        for flag in flags:
            flag_rows.append([
                f"`{flag['name']}`",
                flag["type"],
                flag["default"],
                flag["desc"],
            ])
        parts.append(render_markdown_table(
            ["Flag", "Type", "Default", "Description"],
            flag_rows,
        ))

    # Extract strictcli commands
    commands = _extract_strictcli_commands(source)
    if commands:
        parts.append("")
        parts.append("**Commands:**")
        parts.append("")
        cmd_rows = []
        for cmd in commands:
            cmd_rows.append([f"`{cmd['name']}`", cmd["desc"]])
        parts.append(render_markdown_table(
            ["Command", "Description"],
            cmd_rows,
        ))

    if not parts:
        return format_error(f"no CLI documentation found in '{path}'")

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


def _extract_strictcli_flags(source):
    """Extract strictcli flag definitions from Go source.

    Matches patterns like:
    - app.BoolFlag("name", "description")
    - app.StringFlag("name", "description")
    - cli.BoolFlag("name", "description")
    - <identifier>.BoolFlag("name", "description")

    Returns list of {name, type, default, desc}.
    """
    flags = []

    # Match <var>.BoolFlag("name", "help") and <var>.StringFlag("name", "help")
    flag_re = re.compile(
        r"\w+\.(Bool|String|Int|Float|Duration)Flag\s*\(\s*"
        r'"([^"]*?)"\s*,\s*'    # flag name
        r'"([^"]*?)"\s*\)',     # description
    )

    for match in flag_re.finditer(source):
        flag_type = match.group(1).lower()
        flags.append(
            {
                "name": match.group(2),
                "type": flag_type,
                "default": "",
                "desc": match.group(3),
            }
        )

    return flags


def _extract_strictcli_commands(source):
    """Extract strictcli command definitions from Go source.

    Matches patterns like:
    - app.Command("name", "description", ...)
    - cli.Command("name", "description", ...)

    Returns list of {name, desc}.
    """
    commands = []

    # Match <var>.Command("name", "help", ...)
    cmd_re = re.compile(
        r"\w+\.Command\s*\(\s*"
        r'"([^"]*?)"\s*,\s*'    # command name
        r'"([^"]*?)"\s*[,)]',   # description
    )

    for match in cmd_re.finditer(source):
        commands.append(
            {
                "name": match.group(1),
                "desc": match.group(2),
            }
        )

    return commands


# ---------------------------------------------------------------------------
# :::prose-desc
# ---------------------------------------------------------------------------


def _handle_prose_desc(path, target, body, source_paths, base_dir, attrs):
    """Extract only the package doc comment as prose markdown.

    Unlike :::module which also lists exported declarations, this directive
    returns just the package-level doc comment.
    """
    if not path:
        return format_error(":::prose-desc requires a package path argument")

    pkg_dir = _resolve_package_dir(path, source_paths, base_dir)
    if pkg_dir is None:
        return format_error(f"package '{path}' not found")

    # Collect all non-test .go files
    go_files = sorted(
        f
        for f in os.listdir(pkg_dir)
        if f.endswith(".go") and not f.endswith("_test.go")
    )

    if not go_files:
        return format_error(f"no .go files in '{path}'")

    file_contents = {}
    for gf in go_files:
        file_path = os.path.join(pkg_dir, gf)
        content, _err = read_source(file_path)
        file_contents[gf] = content if content is not None else ""

    _package_name, package_doc = _extract_package_doc(file_contents)

    if not package_doc:
        return format_error(f"no package doc comment found in '{path}'")

    return _format_docstring(package_doc)


GoExtractor._HANDLERS = {
    "ref": _handle_module,
    "code-test": _handle_test,
    "table-schema": _handle_schema,
    "code-help": _handle_cli,
    "table-config": handle_table_config,
    "prose-desc": _handle_prose_desc,
}
