"""Dart source extractor for selfdoc -- parses .dart files to extract public declarations, doc comments, part files, and exports for documentation pages.

Uses regex-based parsing (no Dart toolchain required). Handles:
- :::ref        -- extract library doc, pub declarations with doc comments
- :::prose-desc -- extract library-level doc comments only
- :::table-schema -- extract class fields as a table
- :::table-config -- extract config file contents as tables (JSON/TOML)
"""

import os
import re

from selfdoc.extractors.base import (
    BaseExtractor,
    _extract_brace_block,
    _format_docstring,
    collect_comment_lines_above,
    format_error,
    handle_table_config,
    read_source,
)
from selfdoc.tables import render_markdown_table

# Generated file detection: matches .g.dart, .freezed.dart, etc.
_GENERATED_SUFFIX_RE = re.compile(r"\.\w+\.dart$")

# Part directive: part 'path/to/file.dart';
_DART_PART_RE = re.compile(r"^part\s+['\"]([^'\"]+)['\"];")

# Export directive: export 'path.dart'; or with show/hide combinators
# Also handles conditional exports: export 'a.dart' if (dart.library.io) 'b.dart';
_DART_EXPORT_RE = re.compile(
    r"^export\s+['\"]([^'\"]+)['\"]\s*"
    r"(?:if\s*\([^)]+\)\s*['\"]([^'\"]+)['\"]\s*)?"
    r"(?:(show|hide)\s+([\w\s,]+))?\s*;"
)

# ---------------------------------------------------------------------------
# Declaration patterns
# ---------------------------------------------------------------------------

# Class declarations: [abstract] [base|interface|final] [mixin] class Name
_DART_CLASS_RE = re.compile(
    r"^(?:abstract\s+)?(?:(?:base|interface|final)\s+)?(?:mixin\s+)?class\s+(\w+)"
)

# Sealed class: sealed class Name
_DART_SEALED_CLASS_RE = re.compile(r"^sealed\s+class\s+(\w+)")

# Pure mixin (NOT mixin class): [base] mixin Name
_DART_MIXIN_RE = re.compile(r"^(?:base\s+)?mixin\s+(\w+)")

# Enum: enum Name
_DART_ENUM_RE = re.compile(r"^enum\s+(\w+)")

# Extension type: extension type Name
_DART_EXTENSION_TYPE_RE = re.compile(r"^extension\s+type\s+(\w+)")

# Typedef: typedef Name
_DART_TYPEDEF_RE = re.compile(r"^typedef\s+(\w+)")

# Top-level const/final: const [Type] name = ...; or final [Type] name = ...;
_DART_CONST_RE = re.compile(r"^(?:const|final)\s+(?:\w[\w<>?,\s]*\s+)?(\w+)\s*[=;]")

# Top-level var: [Type] var name
_DART_VAR_RE = re.compile(r"^(?:(?:\w[\w<>?,\s]*\s+)?)?var\s+(\w+)")

# Top-level function: [ReturnType] name( or name<
_DART_FUNC_RE = re.compile(r"^(?:[\w<>\[\]?,.\s]+\s+)(\w+)\s*(?:<[^>]*>\s*)?\(")

# Keywords that should not be mistaken for function names
_DART_KEYWORDS = frozenset({
    "import", "export", "part", "library", "if", "for", "while", "do",
    "switch", "return", "throw", "assert", "await", "yield", "try",
    "catch", "finally", "new", "const", "final", "var", "void",
    "class", "enum", "mixin", "sealed", "abstract", "base", "interface",
    "extension", "typedef", "true", "false", "null", "super", "this",
})


def _is_generated_file(file_path):
    """Check if a Dart file is generated (e.g., .g.dart, .freezed.dart)."""
    basename = os.path.basename(file_path)
    # Must have at least two dots: name.generator.dart
    parts = basename.split(".")
    if len(parts) >= 3 and parts[-1] == "dart":
        return True
    return False


# ---------------------------------------------------------------------------
# Symbol extraction
# ---------------------------------------------------------------------------


def _extract_symbol_from_line(stripped, symbols):
    """Try to extract a public symbol name from a top-level declaration line."""
    # Try specific patterns first in priority order
    for pattern in (
        _DART_SEALED_CLASS_RE,  # Must come before class RE
        _DART_CLASS_RE,
        _DART_ENUM_RE,
        _DART_EXTENSION_TYPE_RE,
        _DART_TYPEDEF_RE,
    ):
        m = pattern.match(stripped)
        if m:
            name = m.group(1)
            if not name.startswith("_") and name not in symbols:
                symbols.append(name)
            return

    # Mixin: only if NOT followed by "class" (mixin class is handled by _DART_CLASS_RE)
    m = _DART_MIXIN_RE.match(stripped)
    if m:
        name = m.group(1)
        if name != "class" and not name.startswith("_") and name not in symbols:
            symbols.append(name)
        return

    # Const/final
    m = _DART_CONST_RE.match(stripped)
    if m:
        name = m.group(1)
        if not name.startswith("_") and name not in symbols:
            symbols.append(name)
        return

    # Var
    m = _DART_VAR_RE.match(stripped)
    if m:
        name = m.group(1)
        if not name.startswith("_") and name not in symbols:
            symbols.append(name)
        return

    # Function: fallback pattern
    m = _DART_FUNC_RE.match(stripped)
    if m:
        name = m.group(1)
        if (
            not name.startswith("_")
            and name not in _DART_KEYWORDS
            and name not in symbols
        ):
            symbols.append(name)
        return


def _extract_public_symbols(source):
    """Extract all public top-level symbols from Dart source code."""
    lines = source.split("\n")
    symbols = []
    in_block_comment = False
    brace_depth = 0

    for line in lines:
        stripped = line.strip()

        # Handle block comments
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
                idx = stripped.index("*/")
                stripped = stripped[idx + 2 :].strip()
                if not stripped:
                    continue
            else:
                continue

        if "/*" in stripped:
            if "*/" in stripped[stripped.index("/*") + 2 :]:
                stripped = re.sub(r"/\*.*?\*/", "", stripped).strip()
                if not stripped:
                    continue
            else:
                in_block_comment = True
                stripped = stripped[: stripped.index("/*")].strip()
                if not stripped:
                    continue

        # Skip comment-only lines
        if stripped.startswith("//"):
            continue

        # Only extract at top level (before this line opens any braces)
        if brace_depth == 0:
            _extract_symbol_from_line(stripped, symbols)

        # Track brace depth (after extraction, since the declaration line opens a brace)
        brace_depth += stripped.count("{") - stripped.count("}")
        # Clamp to 0 in case of imbalanced braces in strings
        if brace_depth < 0:
            brace_depth = 0

    return symbols


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _read_package_name(base_dir):
    """Read the package name from pubspec.yaml."""
    pubspec_path = os.path.join(base_dir, "pubspec.yaml")
    try:
        with open(pubspec_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("name:"):
                    return line[5:].strip().strip("'\"")
    except OSError:
        pass
    return None


def _resolve_package_path(path_arg, base_dir):
    """Resolve a package:name/path.dart import to a file path.

    package:pkg_name/foo.dart resolves to lib/foo.dart within the package.
    """
    rest = path_arg[len("package:"):]
    slash_idx = rest.find("/")
    if slash_idx < 0:
        return None
    pkg_name = rest[:slash_idx]
    file_path = rest[slash_idx + 1:]

    actual_name = _read_package_name(base_dir)
    if actual_name is None or actual_name != pkg_name:
        return None

    candidate = os.path.join(base_dir, "lib", file_path)
    if os.path.isfile(candidate):
        return candidate
    return None


def _resolve_dart_path(path_arg, source_paths, base_dir):
    """Resolve a path argument to a Dart source file or directory.

    Handles package: imports (e.g., package:pkg_name/foo.dart -> lib/foo.dart).
    Otherwise tries each source_path prefix, then the base_dir directly.
    Checks for both directories containing .dart files and direct .dart files.
    """
    # Handle package: imports
    if path_arg.startswith("package:"):
        return _resolve_package_path(path_arg, base_dir)

    candidates = []
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, path_arg))
    candidates.append(os.path.join(base_dir, path_arg))

    for candidate in candidates:
        if os.path.isdir(candidate):
            if any(f.endswith(".dart") for f in os.listdir(candidate)):
                return candidate
        if os.path.isfile(candidate):
            return candidate
        dart_candidate = candidate + ".dart"
        if os.path.isfile(dart_candidate):
            return dart_candidate

    return None


def _find_project_root(file_path):
    """Find the project root by walking up to find pubspec.yaml."""
    current = os.path.dirname(os.path.abspath(file_path))
    for _ in range(20):  # Safety limit
        if os.path.isfile(os.path.join(current, "pubspec.yaml")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


# ---------------------------------------------------------------------------
# Part file following
# ---------------------------------------------------------------------------


def _follow_parts(file_path, source):
    """Follow part directives and collect symbols from part files.

    Scans source for `part 'xxx.dart';` directives. For each part,
    resolves the path relative to the library file's directory and
    extracts public symbols. Skips generated part files.

    Returns a list of public symbol names from all part files.
    """
    lib_dir = os.path.dirname(file_path)
    symbols = []

    for line in source.split("\n"):
        stripped = line.strip()
        m = _DART_PART_RE.match(stripped)
        if m:
            part_path = m.group(1)
            full_part_path = os.path.join(lib_dir, part_path)
            full_part_path = os.path.normpath(full_part_path)

            # Skip generated part files
            if _is_generated_file(full_part_path):
                continue

            part_source, err = read_source(full_part_path)
            if err or part_source is None:
                continue

            # Extract symbols from the part file
            part_symbols = _extract_public_symbols(part_source)
            for sym in part_symbols:
                if sym not in symbols:
                    symbols.append(sym)

    return symbols


def _follow_parts_declarations(file_path, source):
    """Follow part directives and collect declarations from part files.

    Like _follow_parts but returns full declaration dicts instead of just names.
    """
    lib_dir = os.path.dirname(file_path)
    declarations = []

    for line in source.split("\n"):
        stripped = line.strip()
        m = _DART_PART_RE.match(stripped)
        if m:
            part_path = m.group(1)
            full_part_path = os.path.join(lib_dir, part_path)
            full_part_path = os.path.normpath(full_part_path)

            if _is_generated_file(full_part_path):
                continue

            part_source, err = read_source(full_part_path)
            if err or part_source is None:
                continue

            part_decls = _extract_declarations(part_source)
            declarations.extend(part_decls)

    return declarations


# ---------------------------------------------------------------------------
# Export following
# ---------------------------------------------------------------------------


def _follow_exports(file_path, source, base_dir, visited=None):
    """Follow export directives and collect re-exported symbols.

    Scans source for `export 'path.dart'` directives. For each export:
    1. Resolves the path relative to the current file's directory
    2. Recursively follows exports in the target (transitive)
    3. Applies show/hide combinators
    4. Handles conditional exports (includes all variants)

    Uses a visited set to prevent infinite loops from circular exports.
    Returns a list of public symbol names.
    """
    if visited is None:
        visited = set()

    abs_path = os.path.abspath(file_path)
    if abs_path in visited:
        return []
    visited.add(abs_path)

    file_dir = os.path.dirname(file_path)
    symbols = []

    for line in source.split("\n"):
        stripped = line.strip()
        m = _DART_EXPORT_RE.match(stripped)
        if not m:
            continue

        primary_path = m.group(1)
        conditional_path = m.group(2)  # from if (...) 'alt.dart'
        combinator = m.group(3)  # "show" or "hide" or None
        names_str = m.group(4)  # "A, B, C" or None

        # Collect paths to process (primary + conditional variant)
        paths_to_process = [primary_path]
        if conditional_path:
            paths_to_process.append(conditional_path)

        # Parse combinator names
        combinator_names = set()
        if combinator and names_str:
            combinator_names = {n.strip() for n in names_str.split(",")}

        for export_path in paths_to_process:
            exported_symbols = _resolve_and_extract_exports(
                export_path, file_dir, base_dir, visited
            )

            # Apply show/hide filtering
            if combinator == "show":
                exported_symbols = [s for s in exported_symbols if s in combinator_names]
            elif combinator == "hide":
                exported_symbols = [s for s in exported_symbols if s not in combinator_names]

            for sym in exported_symbols:
                if sym not in symbols:
                    symbols.append(sym)

    return symbols


def _resolve_and_extract_exports(export_path, file_dir, base_dir, visited):
    """Resolve an export path and extract symbols from the target file.

    Handles both relative paths and package: paths.
    Recursively follows exports in the target file (transitive exports).
    """
    if export_path.startswith("package:"):
        full_path = _resolve_package_path(export_path, base_dir)
    else:
        full_path = os.path.normpath(os.path.join(file_dir, export_path))

    if full_path is None or not os.path.isfile(full_path):
        return []

    # Skip generated files
    if _is_generated_file(full_path):
        return []

    target_source, err = read_source(full_path)
    if err or target_source is None:
        return []

    # Get symbols defined directly in the target file
    direct_symbols = _extract_public_symbols(target_source)

    # Get symbols from the target's part files
    part_symbols = _follow_parts(full_path, target_source)
    for sym in part_symbols:
        if sym not in direct_symbols:
            direct_symbols.append(sym)

    # Recursively follow exports in the target file (transitive)
    transitive_symbols = _follow_exports(full_path, target_source, base_dir, visited)
    for sym in transitive_symbols:
        if sym not in direct_symbols:
            direct_symbols.append(sym)

    return direct_symbols


def _follow_exports_declarations(file_path, source, base_dir, visited=None):
    """Follow export directives and collect re-exported declarations.

    Like _follow_exports but returns full declaration dicts.
    """
    if visited is None:
        visited = set()

    abs_path = os.path.abspath(file_path)
    if abs_path in visited:
        return []
    visited.add(abs_path)

    file_dir = os.path.dirname(file_path)
    declarations = []
    seen_names = set()

    for line in source.split("\n"):
        stripped = line.strip()
        m = _DART_EXPORT_RE.match(stripped)
        if not m:
            continue

        primary_path = m.group(1)
        conditional_path = m.group(2)
        combinator = m.group(3)
        names_str = m.group(4)

        paths_to_process = [primary_path]
        if conditional_path:
            paths_to_process.append(conditional_path)

        combinator_names = set()
        if combinator and names_str:
            combinator_names = {n.strip() for n in names_str.split(",")}

        for export_path in paths_to_process:
            decls = _resolve_and_extract_export_declarations(
                export_path, file_dir, base_dir, visited
            )

            # Apply show/hide filtering
            if combinator == "show":
                decls = [d for d in decls if d["name"] in combinator_names]
            elif combinator == "hide":
                decls = [d for d in decls if d["name"] not in combinator_names]

            for d in decls:
                if d["name"] not in seen_names:
                    seen_names.add(d["name"])
                    declarations.append(d)

    return declarations


def _resolve_and_extract_export_declarations(export_path, file_dir, base_dir, visited):
    """Resolve an export path and extract declarations from the target file."""
    if export_path.startswith("package:"):
        full_path = _resolve_package_path(export_path, base_dir)
    else:
        full_path = os.path.normpath(os.path.join(file_dir, export_path))

    if full_path is None or not os.path.isfile(full_path):
        return []

    # Skip generated files
    if _is_generated_file(full_path):
        return []

    target_source, err = read_source(full_path)
    if err or target_source is None:
        return []

    decls = _extract_declarations(target_source)

    # Include part file declarations
    part_decls = _follow_parts_declarations(full_path, target_source)
    decls.extend(part_decls)

    # Recursively follow exports (transitive)
    transitive_decls = _follow_exports_declarations(full_path, target_source, base_dir, visited)
    decls.extend(transitive_decls)

    return decls


# ---------------------------------------------------------------------------
# Doc comment parsing and declaration extraction
# ---------------------------------------------------------------------------


def _parse_dart_doc(text):
    """Process Dart-specific doc comment features.

    Converts [ClassName] cross-references to inline code.
    Passes {@macro}, {@template}, {@example} tags through.
    """
    # Convert [Name] cross-references to `Name` inline code.
    # Don't convert markdown links: [text](url)
    text = re.sub(r"\[(\w+)\](?!\()", r"`\1`", text)
    return _format_docstring(text)


def _extract_library_doc(source):
    """Extract library-level doc comment from the top of a Dart source file.

    Collects leading /// comment lines, stopping at the first non-comment,
    non-blank, non-library/import/export/part line.
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
        elif stripped.startswith("//"):
            # Regular comment, skip but continue looking
            continue
        elif stripped == "":
            if doc_lines:
                doc_lines.append("")
            continue
        elif stripped.startswith(("library ", "import ", "export ", "part ")):
            continue
        else:
            break

    while doc_lines and doc_lines[-1] == "":
        doc_lines.pop()

    return "\n".join(doc_lines) if doc_lines else ""


def _extract_declarations(source):
    """Extract all public top-level declarations from Dart source.

    Returns a list of dicts with keys: kind, name, signature, doc.
    """
    lines = source.split("\n")
    declarations = []
    seen_names = set()
    in_block_comment = False
    brace_depth = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Handle block comments
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

        # Skip comments
        if stripped.startswith("//"):
            continue

        # Only process at top level
        if brace_depth == 0:
            decl = _try_parse_declaration(stripped, lines, i, seen_names)
            if decl:
                declarations.append(decl)

        # Track brace depth
        brace_depth += stripped.count("{") - stripped.count("}")
        if brace_depth < 0:
            brace_depth = 0

    return declarations


def _try_parse_declaration(stripped, lines, line_idx, seen_names):
    """Try to parse a top-level declaration from a line.

    Returns a dict {kind, name, signature, doc} or None.
    """
    # Sealed class
    m = _DART_SEALED_CLASS_RE.match(stripped)
    if m:
        return _make_decl(m.group(1), "class", stripped, lines, line_idx, seen_names)

    # Class (covers abstract, base, interface, final, mixin class)
    m = _DART_CLASS_RE.match(stripped)
    if m:
        return _make_decl(m.group(1), "class", stripped, lines, line_idx, seen_names)

    # Enum
    m = _DART_ENUM_RE.match(stripped)
    if m:
        return _make_decl(m.group(1), "enum", stripped, lines, line_idx, seen_names)

    # Extension type
    m = _DART_EXTENSION_TYPE_RE.match(stripped)
    if m:
        return _make_decl(m.group(1), "extension_type", stripped, lines, line_idx, seen_names)

    # Typedef
    m = _DART_TYPEDEF_RE.match(stripped)
    if m:
        return _make_decl(m.group(1), "typedef", stripped, lines, line_idx, seen_names)

    # Pure mixin
    m = _DART_MIXIN_RE.match(stripped)
    if m and m.group(1) != "class":
        return _make_decl(m.group(1), "mixin", stripped, lines, line_idx, seen_names)

    # Const/final
    m = _DART_CONST_RE.match(stripped)
    if m:
        return _make_decl(m.group(1), "const", stripped, lines, line_idx, seen_names)

    # Var
    m = _DART_VAR_RE.match(stripped)
    if m:
        return _make_decl(m.group(1), "var", stripped, lines, line_idx, seen_names)

    # Function
    m = _DART_FUNC_RE.match(stripped)
    if m and m.group(1) not in _DART_KEYWORDS:
        return _make_decl(m.group(1), "function", stripped, lines, line_idx, seen_names)

    return None


def _make_decl(name, kind, stripped, lines, line_idx, seen_names):
    """Create a declaration dict if the name is public and not seen before."""
    if name.startswith("_") or name in seen_names:
        return None
    seen_names.add(name)

    doc = collect_comment_lines_above(lines, line_idx, "///", skip_blank_lines=True)
    sig = _clean_dart_signature(stripped)

    return {"kind": kind, "name": name, "signature": sig, "doc": doc}


def _clean_dart_signature(line):
    """Clean a declaration line for display as a signature.

    Strips the body opener ({) and trailing content.
    """
    line = re.sub(r"\s*\{.*$", "", line)
    line = line.rstrip(";").rstrip()
    return line


def _extract_class_fields(source):
    """Extract class declarations and their fields from Dart source.

    Returns a list of dicts: {name, doc, fields: [{name, type, default, comment}]}.
    """
    lines = source.split("\n")
    classes = []

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Match class-like declarations
        m = _DART_SEALED_CLASS_RE.match(stripped) or _DART_CLASS_RE.match(stripped)
        if m and "{" in stripped:
            class_name = m.group(1)
            if class_name.startswith("_"):
                i += 1
                continue
            doc = collect_comment_lines_above(lines, i, "///", skip_blank_lines=True)

            # Parse fields until closing brace
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

                if brace_depth == 1:
                    field = _parse_class_field(field_line, lines, j)
                    if field:
                        fields.append(field)
                j += 1

            if fields:
                classes.append({"name": class_name, "doc": doc, "fields": fields})

        i += 1

    return classes


def _parse_class_field(field_line, lines, line_idx):
    """Parse a Dart class field declaration.

    Dart fields look like:
        final String name;
        int count = 0;
        late final Database db;
        String? nullableField;

    Returns {name, type, default, comment} or None.
    """
    if not field_line or field_line.startswith("//") or field_line.startswith("@"):
        return None

    # Skip method declarations (has parens for param list)
    if "(" in field_line and ")" in field_line:
        return None

    # Match field: [late] [final|const|var|static] [Type] name [= default];
    m = re.match(
        r"^(?:late\s+)?(?:(?:final|const|var|static)\s+)?"
        r"([\w<>?,\s]+?)\s+"
        r"(\w+)\s*"
        r"(?:=\s*([^;]+?))?\s*;\s*"
        r"(?://\s*(.*))?"
        r"$",
        field_line,
    )
    if not m:
        return None

    field_type = m.group(1).strip()
    name = m.group(2)
    default = (m.group(3) or "").strip()
    inline_comment = (m.group(4) or "").strip()

    # Skip private fields
    if name.startswith("_"):
        return None

    # Check for doc comment above
    doc_above = collect_comment_lines_above(lines, line_idx, "///", skip_blank_lines=False)
    description = inline_comment or doc_above

    return {
        "name": name,
        "type": field_type,
        "default": default,
        "comment": description,
    }


def _format_class_table(class_info):
    """Format a class's fields as a markdown table."""
    rows = []
    for field in class_info["fields"]:
        default_display = f"`{field['default']}`" if field["default"] else ""
        rows.append([
            f"`{field['name']}`",
            f"`{field['type']}`",
            default_display,
            field["comment"],
        ])
    return render_markdown_table(["Field", "Type", "Default", "Description"], rows)


# ---------------------------------------------------------------------------
# symbol_details helpers
# ---------------------------------------------------------------------------


def _extract_func_signature(lines, start_idx):
    """Extract a multi-line function signature from the declaration line.

    Collects lines until parentheses are balanced and we've seen at least
    one '('. Stops after 20 lines. Then strips the body opener (everything
    after the closing paren) and async/sync modifiers.
    """
    sig_parts = []
    paren_depth = 0
    seen_paren = False

    for i in range(start_idx, min(start_idx + 20, len(lines))):
        line = lines[i].strip()
        sig_parts.append(line)

        for ch in line:
            if ch == "(":
                paren_depth += 1
                seen_paren = True
            elif ch == ")":
                paren_depth -= 1

        if seen_paren and paren_depth == 0:
            break

    sig = " ".join(sig_parts)

    # Find the position of the closing paren that balances the first '('
    # and strip everything after it (body opener, async/sync modifiers)
    depth = 0
    close_pos = -1
    for idx, ch in enumerate(sig):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                close_pos = idx
                # Don't break — we want the LAST balanced close at depth 0
                # from the first open. Actually, this IS the matching close.
                break

    if close_pos >= 0:
        sig = sig[:close_pos + 1]

    return sig.rstrip()


def _split_params(text):
    """Split parameter text by commas, respecting nested delimiters."""
    params = []
    depth = 0
    current = []

    for ch in text:
        if ch in ("<", "(", "[", "{"):
            depth += 1
            current.append(ch)
        elif ch in (">", ")", "]", "}"):
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            params.append("".join(current))
            current = []
        else:
            current.append(ch)

    if current:
        remaining = "".join(current).strip()
        if remaining:
            params.append(remaining)

    return params


def _parse_dart_param(param_text):
    """Parse a single Dart parameter. Returns {"name": str, "type": str|None} or None.

    Handles positional, named (required), nullable, default values,
    covariant, and function-type params. Skips this.x and super.x.
    """
    text = param_text.strip()
    if not text:
        return None

    # Remove default value: find last '=' at depth 0
    depth = 0
    last_eq = -1
    for idx, ch in enumerate(text):
        if ch in ("<", "(", "[", "{"):
            depth += 1
        elif ch in (">", ")", "]", "}"):
            depth -= 1
        elif ch == "=" and depth == 0:
            last_eq = idx
    if last_eq >= 0:
        text = text[:last_eq].strip()

    # Strip leading 'required' keyword
    if text.startswith("required "):
        text = text[len("required "):].strip()

    # Strip leading 'covariant' keyword
    if text.startswith("covariant "):
        text = text[len("covariant "):].strip()

    # Skip constructor shorthands
    if text.startswith("this.") or text.startswith("super."):
        return None

    # The name is the last identifier
    m = re.search(r"(\w+)\s*$", text)
    if not m:
        return None

    name = m.group(1)
    param_type = text[:m.start()].strip()
    if not param_type:
        param_type = None

    return {"name": name, "type": param_type}


def _extract_dart_return_type(signature, func_name):
    """Extract return type from a Dart function signature.

    In Dart, the return type precedes the function name:
      Future<List<Item>> fetchItems(...) -> "Future<List<Item>>"
      void greet(...) -> "void"
    """
    # Find func_name followed by '(' or '<' (for generic functions)
    pattern = r"\b" + re.escape(func_name) + r"\s*(?:<[^>]*>\s*)?\("
    m = re.search(pattern, signature)
    if not m:
        return None

    before = signature[:m.start()].strip()
    if not before:
        return None

    # Strip modifiers
    for modifier in ("static", "external", "abstract"):
        before = re.sub(r"\b" + modifier + r"\b", "", before).strip()

    return before if before else None


def _is_param_documented(param_name, doc_text):
    """Check if a parameter is documented in Dart /// doc comments.

    Dart convention is [paramName] brackets (not followed by '(' which
    would be a markdown link).
    """
    if not doc_text:
        return False
    pattern = r"\[" + re.escape(param_name) + r"\](?!\()"
    return bool(re.search(pattern, doc_text))


def _has_dart_return_doc(doc_text):
    """Check if a return value is documented (looks for 'Returns' keyword)."""
    if not doc_text:
        return False
    return bool(re.search(r"\bReturns?\b", doc_text))


def _strip_section_brackets(inner):
    """Remove Dart named-param {} and optional-positional [] section markers.

    Dart uses { } to mark named parameters and [ ] to mark optional
    positional parameters. These are section markers, not nesting
    delimiters — they need to be removed before comma-splitting so
    params inside them are split correctly.

    Examples:
      "String a, {required String b, int c}" -> "String a, required String b, int c"
      "String a, [int b = 0, String? c]"     -> "String a, int b = 0, String? c"
    """
    result = []
    for ch in inner:
        if ch in ("{", "}", "[", "]"):
            continue
        result.append(ch)
    return "".join(result)


def _dart_symbol_details(lines, decl_line_idx, func_name):
    """Build the symbol_details dict for a Dart function declaration."""
    sig = _extract_func_signature(lines, decl_line_idx)
    doc_text = collect_comment_lines_above(
        lines, decl_line_idx, "///", skip_blank_lines=True
    )

    # Extract params from signature
    paren_start = sig.find("(")
    if paren_start < 0:
        return {
            "params": [],
            "return_type": _extract_dart_return_type(sig, func_name),
            "return_documented": _has_dart_return_doc(doc_text),
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

    # Strip section markers before splitting — { } for named params,
    # [ ] for optional positional params
    inner = _strip_section_brackets(inner.strip())

    params = []
    for param_text in _split_params(inner):
        param_text = param_text.strip()
        if not param_text:
            continue
        parsed = _parse_dart_param(param_text)
        if parsed:
            documented = _is_param_documented(parsed["name"], doc_text)
            params.append({
                "name": parsed["name"],
                "type": parsed["type"],
                "documented": documented,
            })

    return {
        "params": params,
        "return_type": _extract_dart_return_type(sig, func_name),
        "return_documented": _has_dart_return_doc(doc_text),
    }


def _dotted_symbol_details(source, symbol_name):
    """Resolve a dotted symbol like ``UserRepository.findById`` to method details.

    Finds the class, abstract class, or mixin declaration for the type part,
    extracts its brace-delimited body, then searches within for a method
    matching the member name.
    """
    type_name, member_name = symbol_name.rsplit(".", 1)

    # Find class or mixin declaration:
    #   [abstract] [base|interface|final] [mixin] class TypeName
    #   [base] mixin TypeName
    type_re = re.compile(
        r"(?:abstract\s+)?(?:(?:base|interface|final|sealed)\s+)?"
        r"(?:mixin\s+)?(?:class|mixin)\s+"
        + re.escape(type_name)
        + r"(?:\s|[<{])",
    )
    type_match = type_re.search(source)
    if type_match is None:
        return None

    # Find the opening brace of the type body
    brace_pos = source.find("{", type_match.start())
    if brace_pos == -1:
        return None

    body = _extract_brace_block(source, brace_pos)
    if body is None:
        return None

    # Search within the body for a function declaration matching member_name.
    # Dart methods look like: ReturnType methodName( or just methodName(
    body_lines = body.split("\n")
    for i, line in enumerate(body_lines):
        stripped = line.strip()

        # Skip comments
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue

        m = _DART_FUNC_RE.match(stripped)
        if m and m.group(1) == member_name and m.group(1) not in _DART_KEYWORDS:
            return _dart_symbol_details(body_lines, i, member_name)

    return None


# ---------------------------------------------------------------------------
# Extractor class
# ---------------------------------------------------------------------------


class DartExtractor(BaseExtractor):
    """Dart language extractor implementing LanguageExtractor protocol."""

    @property
    def name(self) -> str:
        return "dart"

    def detect(self, dir_path: str) -> bool:
        return os.path.isfile(os.path.join(dir_path, "pubspec.yaml"))

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None:
        return _resolve_dart_path(path_arg, source_paths, base_dir)

    def file_extensions(self) -> list[str]:
        return [".dart"]

    def public_symbols(self, file_path: str) -> list[str]:
        """Extract public symbols from a Dart source file.

        Handles classes (all 15 modifier combinations), mixins, enums,
        extension types, typedefs, top-level functions, and top-level
        const/final/var declarations. Skips private symbols (names
        starting with _) and generated files (.g.dart, .freezed.dart).
        """
        if _is_generated_file(file_path):
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        symbols = _extract_public_symbols(source)

        # Include symbols from part files
        part_symbols = _follow_parts(file_path, source)
        for sym in part_symbols:
            if sym not in symbols:
                symbols.append(sym)

        # Include symbols from export directives
        base_dir = _find_project_root(file_path)
        if base_dir:
            export_symbols = _follow_exports(file_path, source, base_dir)
            for sym in export_symbols:
                if sym not in symbols:
                    symbols.append(sym)

        return symbols

    def module_docstring(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return ""
        return _extract_library_doc(source)

    def symbol_details(self, file_path: str, symbol_name: str) -> dict | None:
        """Extract detailed parameter and return info for a symbol.

        Supports dotted names like ``UserRepository.findById`` to target
        a specific method within a class, abstract class, or mixin.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return None

        # Dotted name: resolve as TypeName.member
        if "." in symbol_name:
            return _dotted_symbol_details(source, symbol_name)

        lines = source.split("\n")

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip comments
            if stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # Check for function declaration matching symbol_name
            m = _DART_FUNC_RE.match(stripped)
            if m and m.group(1) == symbol_name and m.group(1) not in _DART_KEYWORDS:
                return _dart_symbol_details(lines, i, symbol_name)

        return None


# ---------------------------------------------------------------------------
# Directive handlers
# ---------------------------------------------------------------------------


def _handle_ref(path, target, body, source_paths, base_dir, attrs):
    """Extract library doc and all public declarations with doc comments."""
    if not path:
        return format_error(":::ref requires a file path argument")

    resolved = _resolve_dart_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    if os.path.isdir(resolved):
        dart_files = sorted(
            f for f in os.listdir(resolved)
            if f.endswith(".dart") and not _is_generated_file(f)
        )
        if not dart_files:
            return format_error(f"no .dart files in '{path}'")
        file_contents = {}
        for df in dart_files:
            fpath = os.path.join(resolved, df)
            content, _err = read_source(fpath)
            file_contents[df] = content if content is not None else ""
    else:
        if _is_generated_file(resolved):
            return format_error(f"'{path}' is a generated file")
        content, err = read_source(resolved)
        if err:
            return format_error(f"cannot read '{path}': {err}")
        file_contents = {os.path.basename(resolved): content}

    parts = []
    parts.append(f"## {path}")

    # Extract library doc from the first file that has one
    for _filename, source in file_contents.items():
        lib_doc = _extract_library_doc(source)
        if lib_doc:
            parts.append("")
            parts.append(_parse_dart_doc(lib_doc))
            break

    # Extract declarations from all files
    declarations = []
    for _filename in sorted(file_contents.keys()):
        source = file_contents[_filename]
        declarations.extend(_extract_declarations(source))

    # Follow part directives for single-file mode
    if not os.path.isdir(resolved):
        part_decls = _follow_parts_declarations(resolved, list(file_contents.values())[0])
        declarations.extend(part_decls)

        # Follow export directives
        base_dir_ref = _find_project_root(resolved)
        if base_dir_ref:
            export_decls = _follow_exports_declarations(
                resolved, list(file_contents.values())[0], base_dir_ref
            )
            # Local declarations shadow re-exported names
            local_names = {d["name"] for d in declarations}
            for d in export_decls:
                if d["name"] not in local_names:
                    declarations.append(d)

    if target:
        matched = [d for d in declarations if d["name"] == target]
        if not matched:
            return format_error(f"symbol '{target}' not found in '{path}'")
        decl = matched[0]
        parts_t = []
        parts_t.append(f"### {decl['name']}")
        parts_t.append("")
        parts_t.append(f"```dart\n{decl['signature']}\n```")
        if decl["doc"]:
            parts_t.append("")
            parts_t.append(_parse_dart_doc(decl["doc"]))
        return "\n".join(parts_t)

    # Group by kind
    kind_order = ["class", "mixin", "enum", "extension_type", "typedef", "const", "var", "function"]
    for kind in kind_order:
        kind_decls = [d for d in declarations if d["kind"] == kind]
        for decl in kind_decls:
            parts.append("")
            parts.append(f"### {decl['name']}")
            parts.append("")
            parts.append(f"```dart\n{decl['signature']}\n```")
            if decl["doc"]:
                parts.append("")
                parts.append(_parse_dart_doc(decl["doc"]))

    return "\n".join(parts)


def _handle_prose_desc(path, target, body, source_paths, base_dir, attrs):
    """Extract only the library-level doc comments as prose markdown."""
    if not path:
        return format_error(":::prose-desc requires a file path argument")

    resolved = _resolve_dart_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    if os.path.isdir(resolved):
        dart_files = sorted(
            f for f in os.listdir(resolved)
            if f.endswith(".dart") and not _is_generated_file(f)
        )
        for df in dart_files:
            content, _err = read_source(os.path.join(resolved, df))
            if content:
                doc = _extract_library_doc(content)
                if doc:
                    return _parse_dart_doc(doc)
        return format_error(f"no library doc comment found in '{path}'")
    else:
        content, err = read_source(resolved)
        if err:
            return format_error(f"cannot read '{path}': {err}")
        doc = _extract_library_doc(content)
        if not doc:
            return format_error(f"no library doc comment found in '{path}'")
        return _parse_dart_doc(doc)


def _handle_table_schema(path, target, body, source_paths, base_dir, attrs):
    """Extract class fields as a markdown table."""
    if not path:
        return format_error(":::table-schema requires a file path argument")

    # JSON/TOML files are config files -- delegate
    if path.endswith((".json", ".toml")):
        return handle_table_config(path, None, body, source_paths, base_dir, attrs)

    full_path = _resolve_dart_path(path, source_paths, base_dir)
    if full_path is None or os.path.isdir(full_path):
        return format_error(f"file '{path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    classes = _extract_class_fields(source)

    if not classes:
        return format_error(f"no classes with fields found in '{path}'")

    if target:
        matched = next((c for c in classes if c["name"] == target), None)
        if matched is None:
            return format_error(f"class '{target}' not found in '{path}'")
        return _format_class_table(matched)

    results = []
    for c in classes:
        results.append(f"### {c['name']}")
        results.append("")
        if c["doc"]:
            results.append(c["doc"])
            results.append("")
        results.append(_format_class_table(c))
    return "\n".join(results)


DartExtractor._HANDLERS = {
    "ref": _handle_ref,
    "prose-desc": _handle_prose_desc,
    "table-schema": _handle_table_schema,
    "table-config": handle_table_config,
}
