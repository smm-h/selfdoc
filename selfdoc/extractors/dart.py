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
# Handler stubs (filled in by later tasks)
# ---------------------------------------------------------------------------


def _handle_ref(arg, body, source_paths, base_dir, attrs):
    """Extract library doc and pub declarations with doc comments."""
    return format_error(":::ref not yet implemented for dart")


def _handle_prose_desc(arg, body, source_paths, base_dir, attrs):
    """Extract library-level doc comments only."""
    return format_error(":::prose-desc not yet implemented for dart")


def _handle_table_schema(arg, body, source_paths, base_dir, attrs):
    """Extract class fields as a table."""
    return format_error(":::table-schema not yet implemented for dart")


DartExtractor._HANDLERS = {
    "ref": _handle_ref,
    "prose-desc": _handle_prose_desc,
    "table-schema": _handle_table_schema,
    "table-config": handle_table_config,
}
