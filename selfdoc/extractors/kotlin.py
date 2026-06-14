"""Kotlin source extractor for selfdoc -- parses .kt files to extract public declarations, KDoc comments, and data class schemas for documentation pages.

Uses regex-based parsing (no Kotlin toolchain required). Handles:
- :::ref         -- extract module doc, public declarations with KDoc comments
- :::prose-desc  -- extract module-level KDoc comments only
- :::table-schema -- extract data class fields as a table
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

# ---------------------------------------------------------------------------
# Regex patterns for Kotlin declarations
# ---------------------------------------------------------------------------

# Kotlin modifiers that can precede a declaration keyword but are NOT
# visibility modifiers. These are stripped before matching the declaration.
_KOTLIN_MODIFIERS = (
    r"(?:(?:actual|expect|external|inline|infix|operator|tailrec|suspend|"
    r"abstract|final|open|override|const|lateinit|sealed|data|inner|"
    r"annotation|value|enum|companion|crossinline|noinline|reified|vararg)\s+)*"
)

# Type declarations: class, object, interface
_KOTLIN_TYPE_RE = re.compile(
    _KOTLIN_MODIFIERS + r"(?:class|object|interface)\s+(\w+)"
)
# Function declarations
_KOTLIN_FUNC_RE = re.compile(
    _KOTLIN_MODIFIERS + r"fun\s+(?:<[^>]+>\s+)?(\w+)"
)
# Property declarations: val/var
_KOTLIN_PROP_RE = re.compile(
    _KOTLIN_MODIFIERS + r"(?:val|var)\s+(\w+)"
)
# Typealias declarations
_KOTLIN_TYPEALIAS_RE = re.compile(
    _KOTLIN_MODIFIERS + r"typealias\s+(\w+)"
)

# Visibility: private, internal, protected at the start of a line
_KOTLIN_PRIVATE_RE = re.compile(r"^(?:private|protected|internal)\s+")

# Square bracket links in KDoc: [ClassName] or [label][ClassName]
_KDOC_LABELED_LINK_RE = re.compile(r"\[([^\]]+)\]\[([^\]]+)\]")
_KDOC_SIMPLE_LINK_RE = re.compile(r"\[([^\]]+)\]")


class KotlinExtractor(BaseExtractor):
    """Kotlin language extractor implementing LanguageExtractor protocol."""

    @property
    def name(self) -> str:
        return "kotlin"

    def detect(self, dir_path: str) -> bool:
        return os.path.isfile(
            os.path.join(dir_path, "build.gradle.kts")
        ) or os.path.isfile(os.path.join(dir_path, "build.gradle"))

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None:
        return _resolve_kotlin_path(path_arg, source_paths, base_dir)

    def file_extensions(self) -> list[str]:
        return [".kt"]

    def public_symbols(self, file_path: str) -> list[str]:
        """Extract public symbols from a Kotlin source file.

        In Kotlin, declarations are public by default (no keyword needed).
        Excludes private, internal, and protected declarations.
        Special case: @PublishedApi internal is treated as public.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        lines = source.split("\n")
        symbols = []
        published_api = False

        for line in lines:
            stripped = line.strip()

            # Track @PublishedApi annotation
            if stripped == "@PublishedApi":
                published_api = True
                continue

            # Skip comment-only lines
            if (
                stripped.startswith("//")
                or stripped.startswith("/*")
                or stripped.startswith("*")
            ):
                continue

            # Skip blank lines (don't reset published_api)
            if not stripped:
                continue

            # Check visibility: private/internal/protected excludes
            is_restricted = bool(_KOTLIN_PRIVATE_RE.match(stripped))

            if is_restricted and not published_api:
                published_api = False
                continue

            # Strip visibility keyword for pattern matching
            work = stripped
            if published_api and work.startswith("internal "):
                work = work[len("internal ") :].strip()
            elif work.startswith("public "):
                work = work[len("public ") :].strip()

            published_api = False

            # Remove trailing inline comments for matching
            comment_idx = work.find("//")
            if comment_idx >= 0:
                work = work[:comment_idx].strip()

            for pattern in (
                _KOTLIN_TYPE_RE,
                _KOTLIN_FUNC_RE,
                _KOTLIN_TYPEALIAS_RE,
                _KOTLIN_PROP_RE,
            ):
                m = pattern.match(work)
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
        """Extract detailed parameter and return info for a symbol."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return None

        lines = source.split("\n")

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip restricted visibility
            if _KOTLIN_PRIVATE_RE.match(stripped):
                continue

            # Strip visibility keyword for pattern matching
            work = stripped
            if work.startswith("public "):
                work = work[len("public "):].strip()

            # Check for data class
            dc_match = re.match(
                r"^data\s+class\s+(\w+)\s*\(", work
            )
            if dc_match and dc_match.group(1) == symbol_name:
                return _data_class_symbol_details(lines, i, stripped)

            # Check for function
            func_match = _KOTLIN_FUNC_RE.match(work)
            if func_match and func_match.group(1) == symbol_name:
                return _func_symbol_details(lines, i)

        return None


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _resolve_kotlin_path(path_arg, source_paths, base_dir):
    """Resolve a path argument to a Kotlin source file or directory.

    Tries each source_path prefix, then the base_dir directly.
    Checks for directories containing .kt files and direct .kt files.
    """
    candidates = []
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, path_arg))
    candidates.append(os.path.join(base_dir, path_arg))

    for candidate in candidates:
        if os.path.isdir(candidate):
            if any(f.endswith(".kt") for f in os.listdir(candidate)):
                return candidate
        if os.path.isfile(candidate):
            return candidate
        kt_candidate = candidate + ".kt"
        if os.path.isfile(kt_candidate):
            return kt_candidate

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
# KDoc extraction helpers
# ---------------------------------------------------------------------------


def _extract_kdoc_block(lines, decl_line_idx):
    """Extract a KDoc block comment (/** ... */) above a declaration line.

    Walks upward from decl_line_idx - 1. Does NOT skip blank lines --
    Kotlin does not associate doc comments separated by blank lines.
    Returns the raw KDoc text with comment markers stripped, or empty string.
    """
    if decl_line_idx <= 0:
        return ""

    idx = decl_line_idx - 1

    # The line immediately above must be the end of a KDoc block or a
    # single-line KDoc. Blank lines break the association.
    stripped = lines[idx].strip()
    if not stripped:
        return ""

    # Single-line KDoc: /** some text */
    single_match = re.match(r"^/\*\*\s*(.*?)\s*\*/$", stripped)
    if single_match:
        return single_match.group(1)

    # Multi-line KDoc: must end with */
    if not stripped.endswith("*/"):
        return ""

    # Collect lines upward until we find /**
    doc_lines = []
    while idx >= 0:
        line = lines[idx].strip()
        if line.startswith("/**"):
            # First line of KDoc block -- strip /** prefix
            text = line[3:]
            if text.endswith("*/"):
                text = text[: -2]
            text = text.strip()
            if text:
                doc_lines.append(text)
            break
        else:
            # Middle or end line -- strip leading * and trailing */
            text = line
            if text.endswith("*/"):
                text = text[:-2]
            text = text.strip()
            if text.startswith("*"):
                text = text[1:]
                if text.startswith(" "):
                    text = text[1:]
            doc_lines.append(text)
        idx -= 1
    else:
        # Never found opening /** -- not a valid KDoc block
        return ""

    doc_lines.reverse()
    return "\n".join(doc_lines)


def _extract_module_doc(source):
    """Extract the module-level KDoc comment from Kotlin source.

    The module doc is the first /** ... */ block at the top of the file,
    appearing before any package, import, or declaration line.
    """
    lines = source.split("\n")
    doc_lines = []
    in_kdoc = False

    for line in lines:
        stripped = line.strip()

        if not in_kdoc:
            # Skip blank lines and regular comments before KDoc
            if not stripped or stripped.startswith("//"):
                continue

            # Single-line KDoc: /** text */
            single_match = re.match(r"^/\*\*\s*(.*?)\s*\*/$", stripped)
            if single_match:
                return single_match.group(1)

            # Start of multi-line KDoc
            if stripped.startswith("/**"):
                in_kdoc = True
                text = stripped[3:].strip()
                if text:
                    doc_lines.append(text)
                continue

            # Any non-comment, non-blank line before KDoc -- no module doc
            return ""
        else:
            # Inside KDoc block
            if stripped.endswith("*/"):
                text = stripped
                if text.startswith("*"):
                    text = text[1:]
                text = text[:-2].strip()
                if text:
                    doc_lines.append(text)
                return "\n".join(doc_lines)
            else:
                text = stripped
                if text.startswith("*"):
                    text = text[1:]
                    if text.startswith(" "):
                        text = text[1:]
                doc_lines.append(text)

    return ""


# ---------------------------------------------------------------------------
# symbol_details helpers
# ---------------------------------------------------------------------------


def _extract_kdoc_param_names(kdoc_text):
    """Extract the set of parameter names documented via @param or @property tags."""
    names = set()
    for m in re.finditer(r"@param\s*\[(\w+)\]|@param\s+(\w+)", kdoc_text):
        names.add(m.group(1) or m.group(2))
    for m in re.finditer(r"@property\s+(\w+)", kdoc_text):
        names.add(m.group(1))
    return names


def _has_return_doc(kdoc_text):
    """Check whether KDoc text contains a @return or @returns tag."""
    return bool(re.search(r"@returns?\s", kdoc_text))


def _extract_return_type(signature):
    """Extract the return type from a function signature string.

    Looks for `: ReturnType` after the closing `)` of the parameter list,
    before `{` or `=` (expression-body). Returns None if no return type.
    """
    # Find the last `)` that closes the parameter list
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
    if not after_params.startswith(":"):
        return None

    # Strip the leading `:`
    type_text = after_params[1:].strip()

    # Remove trailing `{` or `=` (expression body)
    type_text = re.sub(r"\s*[{=].*$", "", type_text).strip()

    return type_text if type_text else None


def _func_symbol_details(lines, decl_line_idx):
    """Build symbol_details for a function declaration."""
    sig = _extract_func_signature(lines, decl_line_idx)
    kdoc_text = _extract_kdoc_block(lines, decl_line_idx)

    # Extract params from signature
    # Find content between first `(` and matching `)`
    paren_start = sig.find("(")
    if paren_start < 0:
        return {
            "params": [],
            "return_type": _extract_return_type(sig),
            "return_documented": _has_return_doc(kdoc_text) if kdoc_text else False,
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

    documented_names = _extract_kdoc_param_names(kdoc_text) if kdoc_text else set()

    params = []
    for param_text in _split_constructor_params(inner):
        param_text = param_text.strip()
        if not param_text:
            continue
        parsed = _parse_constructor_param(param_text, {})
        if parsed:
            params.append({
                "name": parsed["name"],
                "type": parsed["type"] if parsed["type"] else None,
                "documented": parsed["name"] in documented_names,
            })

    return_type = _extract_return_type(sig)
    return_documented = _has_return_doc(kdoc_text) if kdoc_text else False

    return {
        "params": params,
        "return_type": return_type,
        "return_documented": return_documented,
    }


def _data_class_symbol_details(lines, decl_line_idx, stripped):
    """Build symbol_details for a data class declaration."""
    kdoc_text = _extract_kdoc_block(lines, decl_line_idx)

    # Collect constructor text spanning multiple lines
    constructor_text = stripped[stripped.index("("):]
    j = decl_line_idx
    paren_depth = 0
    for ch in constructor_text:
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
    while paren_depth > 0 and j + 1 < len(lines):
        j += 1
        constructor_text += " " + lines[j].strip()
        for ch in lines[j].strip():
            if ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth -= 1

    # Parse fields from constructor text
    inner = constructor_text[1:]
    close_idx = inner.rfind(")")
    if close_idx >= 0:
        inner = inner[:close_idx]

    documented_names = _extract_kdoc_param_names(kdoc_text) if kdoc_text else set()

    params = []
    for param_text in _split_constructor_params(inner):
        parsed = _parse_constructor_param(param_text.strip(), {})
        if parsed:
            params.append({
                "name": parsed["name"],
                "type": parsed["type"] if parsed["type"] else None,
                "documented": parsed["name"] in documented_names,
            })

    return {
        "params": params,
        "return_type": None,
        "return_documented": True,
    }


# ---------------------------------------------------------------------------
# KDoc comment processing
# ---------------------------------------------------------------------------


def _convert_bracket_links(text):
    """Convert KDoc square bracket links to inline code.

    [ClassName] -> `ClassName`
    [label][ClassName] -> label (`ClassName`)
    """
    text = _KDOC_LABELED_LINK_RE.sub(r"\1 (`\2`)", text)
    text = _KDOC_SIMPLE_LINK_RE.sub(r"`\1`", text)
    return text


def _parse_kdoc(text):
    """Process KDoc text into markdown.

    Handles KDoc-specific syntax:
    - @param name desc / @param[name] desc -> Parameters section
    - @return desc -> **Returns:** desc
    - @throws / @exception ExceptionClass desc -> **Throws:** desc
    - @property name desc -> Properties section
    - @constructor desc -> **Constructor:** desc
    - @receiver desc -> **Receiver:** desc
    - @sample qualified.name -> **Sample:** `qualified.name`
    - @see identifier -> **See:** `identifier`
    - @author text -> **Author:** text
    - @since text -> **Since:** text
    - @suppress -> ignored
    - [ClassName] -> `ClassName`
    - [label][ClassName] -> label (`ClassName`)
    """
    if not text:
        return ""

    lines = text.split("\n")
    out = []
    params = []
    properties = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # @param name desc or @param[name] desc
        param_match = re.match(
            r"^@param\s*\[(\w+)\]\s*(.*)", stripped
        ) or re.match(r"^@param\s+(\w+)\s*(.*)", stripped)
        if param_match:
            name = param_match.group(1)
            desc = param_match.group(2).strip()
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("@"):
                desc += " " + lines[i].strip()
                i += 1
            params.append((name, _convert_bracket_links(desc)))
            continue

        # @return desc
        return_match = re.match(r"^@returns?\s+(.*)", stripped)
        if return_match:
            if params:
                _flush_params(out, params)
                params = []
            if properties:
                _flush_properties(out, properties)
                properties = []
            desc = return_match.group(1).strip()
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("@"):
                desc += " " + lines[i].strip()
                i += 1
            out.append(f"**Returns:** {_convert_bracket_links(desc)}")
            continue

        # @throws / @exception ExceptionClass desc
        throws_match = re.match(
            r"^@(?:throws|exception)\s+(\S+)\s*(.*)", stripped
        )
        if throws_match:
            if params:
                _flush_params(out, params)
                params = []
            if properties:
                _flush_properties(out, properties)
                properties = []
            exc_class = throws_match.group(1)
            desc = throws_match.group(2).strip()
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("@"):
                desc += " " + lines[i].strip()
                i += 1
            if desc:
                out.append(f"**Throws:** `{exc_class}` {_convert_bracket_links(desc)}")
            else:
                out.append(f"**Throws:** `{exc_class}`")
            continue

        # @property name desc
        prop_match = re.match(r"^@property\s+(\w+)\s*(.*)", stripped)
        if prop_match:
            name = prop_match.group(1)
            desc = prop_match.group(2).strip()
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("@"):
                desc += " " + lines[i].strip()
                i += 1
            properties.append((name, _convert_bracket_links(desc)))
            continue

        # @constructor desc
        constructor_match = re.match(r"^@constructor\s+(.*)", stripped)
        if constructor_match:
            if params:
                _flush_params(out, params)
                params = []
            if properties:
                _flush_properties(out, properties)
                properties = []
            desc = constructor_match.group(1).strip()
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("@"):
                desc += " " + lines[i].strip()
                i += 1
            out.append(f"**Constructor:** {_convert_bracket_links(desc)}")
            continue

        # @receiver desc
        receiver_match = re.match(r"^@receiver\s+(.*)", stripped)
        if receiver_match:
            if params:
                _flush_params(out, params)
                params = []
            if properties:
                _flush_properties(out, properties)
                properties = []
            desc = receiver_match.group(1).strip()
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("@"):
                desc += " " + lines[i].strip()
                i += 1
            out.append(f"**Receiver:** {_convert_bracket_links(desc)}")
            continue

        # @sample qualified.name
        sample_match = re.match(r"^@sample\s+(\S+)", stripped)
        if sample_match:
            if params:
                _flush_params(out, params)
                params = []
            if properties:
                _flush_properties(out, properties)
                properties = []
            out.append(f"**Sample:** `{sample_match.group(1)}`")
            i += 1
            continue

        # @see identifier
        see_match = re.match(r"^@see\s+(\S+)", stripped)
        if see_match:
            if params:
                _flush_params(out, params)
                params = []
            if properties:
                _flush_properties(out, properties)
                properties = []
            out.append(f"**See:** `{see_match.group(1)}`")
            i += 1
            continue

        # @author text
        author_match = re.match(r"^@author\s+(.*)", stripped)
        if author_match:
            if params:
                _flush_params(out, params)
                params = []
            if properties:
                _flush_properties(out, properties)
                properties = []
            out.append(f"**Author:** {author_match.group(1).strip()}")
            i += 1
            continue

        # @since text
        since_match = re.match(r"^@since\s+(.*)", stripped)
        if since_match:
            if params:
                _flush_params(out, params)
                params = []
            if properties:
                _flush_properties(out, properties)
                properties = []
            out.append(f"**Since:** {since_match.group(1).strip()}")
            i += 1
            continue

        # @suppress -- silently skip
        if stripped.startswith("@suppress"):
            i += 1
            continue

        # Regular line -- convert bracket links
        if params:
            _flush_params(out, params)
            params = []
        if properties:
            _flush_properties(out, properties)
            properties = []
        out.append(_convert_bracket_links(line))
        i += 1

    # Flush remaining
    if params:
        _flush_params(out, params)
    if properties:
        _flush_properties(out, properties)

    return "\n".join(out)


def _flush_params(out, params):
    """Flush accumulated parameter entries as a formatted section."""
    if out and out[-1] != "":
        out.append("")
    out.append("**Parameters:**")
    out.append("")
    for name, desc in params:
        if desc:
            out.append(f"- `{name}`: {desc}")
        else:
            out.append(f"- `{name}`")
    out.append("")
    params.clear()


def _flush_properties(out, properties):
    """Flush accumulated property entries as a formatted section."""
    if out and out[-1] != "":
        out.append("")
    out.append("**Properties:**")
    out.append("")
    for name, desc in properties:
        if desc:
            out.append(f"- `{name}`: {desc}")
        else:
            out.append(f"- `{name}`")
    out.append("")
    properties.clear()


# ---------------------------------------------------------------------------
# Public declaration extraction
# ---------------------------------------------------------------------------


def _extract_pub_declarations(source):
    """Extract all public declarations from Kotlin source.

    In Kotlin, declarations without a visibility modifier are public.
    Excludes private, internal, and protected (unless @PublishedApi internal).

    Returns a list of dicts with keys: kind, name, signature, doc.
    kind is one of: "type", "func", "prop".
    """
    lines = source.split("\n")
    declarations = []
    seen_names = set()
    published_api = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track @PublishedApi annotation
        if stripped == "@PublishedApi":
            published_api = True
            continue

        # Skip comment-only lines
        if (
            stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
        ):
            continue

        # Skip blank lines
        if not stripped:
            continue

        # Skip package and import statements
        if stripped.startswith("package ") or stripped.startswith("import "):
            published_api = False
            continue

        # Check visibility
        is_restricted = bool(_KOTLIN_PRIVATE_RE.match(stripped))

        if is_restricted and not published_api:
            published_api = False
            continue

        # Strip visibility keyword for pattern matching
        work = stripped
        if published_api and work.startswith("internal "):
            work = work[len("internal ") :].strip()
        elif work.startswith("public "):
            work = work[len("public ") :].strip()

        published_api = False

        # Type declarations
        type_match = _KOTLIN_TYPE_RE.match(work)
        if type_match:
            type_name = type_match.group(1)
            sig = _clean_type_signature(stripped)
            doc_text = _extract_kdoc_block(lines, i)
            doc = _parse_kdoc(doc_text)

            if type_name not in seen_names:
                seen_names.add(type_name)
                declarations.append({
                    "kind": "type",
                    "name": type_name,
                    "signature": sig,
                    "doc": doc,
                })
            continue

        # Typealias
        alias_match = _KOTLIN_TYPEALIAS_RE.match(work)
        if alias_match:
            alias_name = alias_match.group(1)
            sig = stripped.rstrip()
            doc_text = _extract_kdoc_block(lines, i)
            doc = _parse_kdoc(doc_text)

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
        func_match = _KOTLIN_FUNC_RE.match(work)
        if func_match:
            func_name = func_match.group(1)
            sig = _extract_func_signature(lines, i)
            doc_text = _extract_kdoc_block(lines, i)
            doc = _parse_kdoc(doc_text)

            if func_name not in seen_names:
                seen_names.add(func_name)
                declarations.append({
                    "kind": "func",
                    "name": func_name,
                    "signature": sig,
                    "doc": doc,
                })
            continue

        # Property declarations
        prop_match = _KOTLIN_PROP_RE.match(work)
        if prop_match:
            prop_name = prop_match.group(1)
            sig = _clean_prop_signature(stripped)
            doc_text = _extract_kdoc_block(lines, i)
            doc = _parse_kdoc(doc_text)

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
        if i > start_idx and not line.endswith(",") and not line.endswith("("):
            break

    sig = " ".join(sig_parts)
    sig = re.sub(r"\s*\{.*$", "", sig)
    return sig.rstrip()


def _clean_type_signature(line):
    """Clean a type declaration line for display.

    Strips trailing body opener brace.
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
    """Extract module doc and all public declarations with their KDoc comments.

    path is a file path (e.g. "src/main/kotlin/Parser.kt") or a directory path.
    """
    if not path:
        return format_error(":::ref requires a file path argument")

    resolved = _resolve_kotlin_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    if os.path.isdir(resolved):
        kt_files = sorted(
            f for f in os.listdir(resolved) if f.endswith(".kt")
        )
        if not kt_files:
            return format_error(f"no .kt files in '{path}'")
        file_contents = {}
        for kf in kt_files:
            fpath = os.path.join(resolved, kf)
            content, _err = read_source(fpath)
            file_contents[kf] = content if content is not None else ""
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

    # Extract public declarations from all files
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
            parts.append(f"```kotlin\n{decl['signature']}\n```")
            if decl["doc"]:
                parts.append("")
                parts.append(decl["doc"])

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# :::prose-desc
# ---------------------------------------------------------------------------


def _handle_prose_desc(path, target, body, source_paths, base_dir, attrs):
    """Extract only the module-level KDoc comments as prose markdown."""
    if not path:
        return format_error(":::prose-desc requires a file path argument")

    resolved = _resolve_kotlin_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    if os.path.isdir(resolved):
        kt_files = sorted(
            f for f in os.listdir(resolved) if f.endswith(".kt")
        )
        for kf in kt_files:
            content, _err = read_source(os.path.join(resolved, kf))
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
    """Extract data class fields as a markdown table.

    path is the file path, target is the optional class name.
    """
    if not path:
        return format_error(":::table-schema requires a file path argument")

    # JSON/TOML files are config files, not Kotlin source -- delegate
    if path.endswith((".json", ".toml")):
        return handle_table_config(path, None, body, source_paths, base_dir, attrs)

    full_path = _resolve_file_path(path, source_paths, base_dir)
    if full_path is None:
        return format_error(f"file '{path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    data_classes = _extract_data_class_fields(source)

    if not data_classes:
        return format_error(f"no data class types found in '{path}'")

    if target:
        matched = next(
            (dc for dc in data_classes if dc["name"] == target), None
        )
        if matched is None:
            return format_error(
                f"data class '{target}' not found in '{path}'"
            )
        return _format_data_class_table(matched)

    # No type specified: format all data classes
    results = []
    for dc in data_classes:
        results.append(f"### {dc['name']}")
        results.append("")
        if dc["doc"]:
            results.append(dc["doc"])
            results.append("")
        results.append(_format_data_class_table(dc))
    return "\n".join(results)


# ---------------------------------------------------------------------------
# Data class field extraction
# ---------------------------------------------------------------------------


def _extract_data_class_fields(source):
    """Extract data class declarations and their primary constructor fields.

    Finds data class blocks and parses the primary constructor parameters.
    Looks for KDoc @property tags to get field descriptions.

    Returns a list of dicts: {name, doc, fields: [{name, type, default, comment}]}.
    """
    lines = source.split("\n")
    data_classes = []

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Skip restricted visibility
        if _KOTLIN_PRIVATE_RE.match(stripped):
            i += 1
            continue

        # Strip public keyword if present
        work = stripped
        if work.startswith("public "):
            work = work[len("public ") :].strip()

        # Match: data class Name(
        match = re.match(r"^data\s+class\s+(\w+)\s*\(", work)
        if match:
            name = match.group(1)

            # Extract KDoc above for @property descriptions
            doc_text = _extract_kdoc_block(lines, i)
            doc = _parse_kdoc(doc_text)

            # Collect property descriptions from KDoc @property tags
            prop_docs = {}
            if doc_text:
                for prop_match in re.finditer(
                    r"@property\s+(\w+)\s+(.*?)(?=@\w|\Z)",
                    doc_text,
                    re.DOTALL,
                ):
                    prop_name = prop_match.group(1)
                    prop_desc = prop_match.group(2).strip()
                    # Normalize whitespace
                    prop_desc = " ".join(prop_desc.split())
                    prop_docs[prop_name] = prop_desc

            # Collect constructor parameters spanning multiple lines
            constructor_text = stripped[stripped.index("(") :]
            j = i
            paren_depth = 0
            for ch in constructor_text:
                if ch == "(":
                    paren_depth += 1
                elif ch == ")":
                    paren_depth -= 1
            while paren_depth > 0 and j + 1 < len(lines):
                j += 1
                constructor_text += " " + lines[j].strip()
                for ch in lines[j].strip():
                    if ch == "(":
                        paren_depth += 1
                    elif ch == ")":
                        paren_depth -= 1

            # Parse fields from constructor text
            # Remove outer parens
            inner = constructor_text[1:]
            close_idx = inner.rfind(")")
            if close_idx >= 0:
                inner = inner[:close_idx]

            fields = []
            for param in _split_constructor_params(inner):
                field = _parse_constructor_param(param.strip(), prop_docs)
                if field:
                    fields.append(field)

            data_classes.append({
                "name": name,
                "doc": doc,
                "fields": fields,
            })

        i += 1

    return data_classes


def _split_constructor_params(text):
    """Split constructor parameter text by commas, respecting nested generics."""
    params = []
    depth = 0
    current = []

    for ch in text:
        if ch in ("<", "("):
            depth += 1
            current.append(ch)
        elif ch in (">", ")"):
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


def _parse_constructor_param(param_text, prop_docs):
    """Parse a single data class constructor parameter.

    Format: [val|var] name: Type [= default]
    Returns {name, type, default, comment} or None.
    """
    # Match: [val|var] name: Type [= default]
    match = re.match(
        r"^(?:(?:val|var)\s+)?"  # optional val/var
        r"(\w+)\s*:\s*"  # parameter name
        r"([^=]+?)"  # type
        r"(?:\s*=\s*(.*))?"  # optional default
        r"$",
        param_text.strip(),
    )
    if not match:
        return None

    name = match.group(1)
    field_type = match.group(2).strip()
    default = (match.group(3) or "").strip()
    comment = prop_docs.get(name, "")

    return {
        "name": name,
        "type": field_type,
        "default": default,
        "comment": comment,
    }


def _format_data_class_table(dc_info):
    """Format a data class's fields as a markdown table."""
    rows = []

    for field in dc_info["fields"]:
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

KotlinExtractor._HANDLERS = {
    "ref": _handle_ref,
    "prose-desc": _handle_prose_desc,
    "table-schema": _handle_table_schema,
    "table-config": handle_table_config,
}
