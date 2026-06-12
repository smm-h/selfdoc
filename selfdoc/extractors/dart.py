"""Dart source extractor for selfdoc -- parses .dart files to extract public
declarations, doc comments, part files, and exports for documentation pages.

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
    _format_docstring,
    collect_comment_lines_above,
    format_error,
    handle_table_config,
    read_source,
)
from selfdoc.tables import render_markdown_table

# Generated file detection: matches .g.dart, .freezed.dart, etc.
_GENERATED_SUFFIX_RE = re.compile(r"\.\w+\.dart$")

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


def _resolve_dart_path(path_arg, source_paths, base_dir):
    """Resolve a path argument to a Dart source file or directory.

    Tries each source_path prefix, then the base_dir directly.
    Checks for both directories containing .dart files and direct .dart files.
    """
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

        return _extract_public_symbols(source)


# ---------------------------------------------------------------------------
# Directive handlers
# ---------------------------------------------------------------------------


def _handle_ref(arg, body, source_paths, base_dir, attrs):
    """Extract library doc and all public declarations with doc comments."""
    if not arg:
        return format_error(":::ref requires a file path argument")

    resolved = _resolve_dart_path(arg, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{arg}' not found")

    if os.path.isdir(resolved):
        dart_files = sorted(
            f for f in os.listdir(resolved)
            if f.endswith(".dart") and not _is_generated_file(f)
        )
        if not dart_files:
            return format_error(f"no .dart files in '{arg}'")
        file_contents = {}
        for df in dart_files:
            path = os.path.join(resolved, df)
            content, _err = read_source(path)
            file_contents[df] = content if content is not None else ""
    else:
        if _is_generated_file(resolved):
            return format_error(f"'{arg}' is a generated file")
        content, err = read_source(resolved)
        if err:
            return format_error(f"cannot read '{arg}': {err}")
        file_contents = {os.path.basename(resolved): content}

    parts = []
    parts.append(f"## {arg}")

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


def _handle_prose_desc(arg, body, source_paths, base_dir, attrs):
    """Extract only the library-level doc comments as prose markdown."""
    if not arg:
        return format_error(":::prose-desc requires a file path argument")

    resolved = _resolve_dart_path(arg, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{arg}' not found")

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
        return format_error(f"no library doc comment found in '{arg}'")
    else:
        content, err = read_source(resolved)
        if err:
            return format_error(f"cannot read '{arg}': {err}")
        doc = _extract_library_doc(content)
        if not doc:
            return format_error(f"no library doc comment found in '{arg}'")
        return _parse_dart_doc(doc)


def _handle_table_schema(arg, body, source_paths, base_dir, attrs):
    """Extract class fields as a markdown table."""
    if not arg:
        return format_error(":::table-schema requires a file path argument")

    parts_split = arg.split(None, 1)
    file_path = parts_split[0]
    type_name = parts_split[1] if len(parts_split) > 1 else None

    # JSON/TOML files are config files -- delegate
    if file_path.endswith((".json", ".toml")):
        return handle_table_config(file_path, body, source_paths, base_dir, attrs)

    full_path = _resolve_dart_path(file_path, source_paths, base_dir)
    if full_path is None or os.path.isdir(full_path):
        return format_error(f"file '{file_path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{file_path}': {err}")

    classes = _extract_class_fields(source)

    if not classes:
        return format_error(f"no classes with fields found in '{file_path}'")

    if type_name:
        target = next((c for c in classes if c["name"] == type_name), None)
        if target is None:
            return format_error(f"class '{type_name}' not found in '{file_path}'")
        return _format_class_table(target)

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
