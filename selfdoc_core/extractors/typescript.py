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

from selfdoc_core.extractors.base import (
    BaseExtractor,
    _config_from_json,
    _extract_brace_block,
    _json_type_name,
    _json_value_repr,
    apply_exclude_keys,
    format_error,
    handle_table_config,
    parse_comma_set,
    read_source,
)
from selfdoc_core.tables import render_markdown_table

# Patterns for exported TS/JS symbols (used by TypeScriptExtractor.public_symbols)
_TS_NAMED_FUNC_RE = re.compile(
    r"^export\s+(?:async\s+)?function\s+(\w+)"
)
_TS_CLASS_RE = re.compile(r"^export\s+class\s+(\w+)")
_TS_VAR_RE = re.compile(r"^export\s+(?:const|let|var)\s+(\w+)")
_TS_TYPE_RE = re.compile(r"^export\s+(?:interface|type|enum)\s+(\w+)")
_TS_DEFAULT_RE = re.compile(
    r"^export\s+default\s+(?:function|class)\s+(\w+)"
)
_TS_REEXPORT_RE = re.compile(r"^export\s*\{([^}]+)\}")


class TypeScriptExtractor(BaseExtractor):
    """TypeScript/JavaScript language extractor implementing LanguageExtractor protocol."""

    @property
    def name(self) -> str:
        return "typescript"

    def detect(self, dir_path: str) -> bool:
        return os.path.isfile(os.path.join(dir_path, "tsconfig.json"))

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None:
        return _resolve_file_path(path_arg, source_paths, base_dir)

    def file_extensions(self) -> list[str]:
        return [".ts", ".tsx", ".js", ".jsx"]

    def public_symbols(self, file_path: str) -> list[str]:
        """Extract exported symbols from a TypeScript/JavaScript file.

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

            # Check re-export pattern first: export { A, B, C }
            m = _TS_REEXPORT_RE.match(stripped)
            if m:
                names_str = m.group(1)
                for name_part in names_str.split(","):
                    name_part = name_part.strip()
                    if " as " in name_part:
                        name_part = name_part.split(" as ")[-1].strip()
                    if name_part and name_part not in symbols:
                        symbols.append(name_part)
                continue

            # Check default export before other patterns
            m = _TS_DEFAULT_RE.match(stripped)
            if m:
                sym_name = m.group(1)
                if sym_name not in symbols:
                    symbols.append(sym_name)
                continue

            for pattern in (
                _TS_NAMED_FUNC_RE,
                _TS_CLASS_RE,
                _TS_VAR_RE,
                _TS_TYPE_RE,
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
        result = _extract_module_jsdoc(source)
        if result is None:
            return ""
        return result.get("description", "")

    def symbol_details(self, file_path: str, symbol_name: str) -> dict | None:
        """Extract detailed parameter and return info for a symbol.

        Supports dotted names like ``Router.handle`` to target a specific
        method within a class or interface.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return None

        # Dotted name: resolve as TypeName.member
        if "." in symbol_name:
            return _dotted_symbol_details(source, symbol_name)

        # Try exported functions first, then non-exported
        func_re = re.compile(
            r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+"
            + re.escape(symbol_name)
            + r"\s*\(",
        )
        match = func_re.search(source)
        if match is None:
            return None

        return _ts_symbol_details(source, match)


# ---------------------------------------------------------------------------
# symbol_details helpers
# ---------------------------------------------------------------------------


def _dotted_symbol_details(source, symbol_name):
    """Resolve a dotted symbol like ``Router.handle`` to method details.

    Finds the class or interface declaration for the type part, extracts
    its brace-delimited body, then searches within for the method.
    """
    type_name, member_name = symbol_name.rsplit(".", 1)

    # Find class or interface declaration
    type_re = re.compile(
        r"(?:export\s+)?(?:abstract\s+)?(?:class|interface)\s+"
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

    # Search for the method declaration within the body.
    # Matches: [public/private/protected] [static] [async] memberName(
    method_re = re.compile(
        r"(?:(?:public|private|protected)\s+)?"
        r"(?:static\s+)?"
        r"(?:async\s+)?"
        + re.escape(member_name)
        + r"\s*\(",
    )
    method_match = method_re.search(body)
    if method_match is None:
        return None

    # Compute the absolute offset so _find_jsdoc_before works on full source
    body_offset = brace_pos + 1
    abs_start = body_offset + method_match.start()

    # Build a match-like object pointing into the full source
    abs_re = re.compile(
        r"(?:(?:public|private|protected)\s+)?"
        r"(?:static\s+)?"
        r"(?:async\s+)?"
        + re.escape(member_name)
        + r"\s*\(",
    )
    abs_match = abs_re.search(source, abs_start)
    if abs_match is None:
        return None

    return _ts_symbol_details(source, abs_match)


def _ts_symbol_details(source, decl_match):
    """Build a symbol_details dict from a function declaration match.

    decl_match should point to the start of the function declaration.
    Extracts parameters, return type, and JSDoc documentation status.
    """
    # Find the opening paren
    paren_start = source.index("(", decl_match.start())
    # Extract everything from ( to the matching )
    paren_end = _find_matching_paren(source, paren_start)
    if paren_end is None:
        return None

    params_str = source[paren_start + 1 : paren_end]
    params = _parse_ts_params(params_str)

    # Extract return type from after ) up to { or newline
    return_type = _extract_ts_return_type(source[paren_end:])

    # Find JSDoc above the declaration
    jsdoc = _find_jsdoc_before(source, decl_match.start())
    documented_param_names = set()
    return_documented = False
    if jsdoc:
        documented_param_names = {p["name"] for p in jsdoc["params"]}
        return_documented = jsdoc["returns"] is not None

    param_dicts = []
    for p in params:
        param_dicts.append({
            "name": p["name"],
            "type": p["type"],
            "documented": p["name"].lstrip("...") in documented_param_names,
        })

    return {
        "params": param_dicts,
        "return_type": return_type,
        "return_documented": return_documented,
    }


def _find_matching_paren(source, open_pos):
    """Find the closing ) that matches the ( at open_pos."""
    depth = 0
    i = open_pos
    while i < len(source):
        ch = source[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        elif ch in ("'", '"', "`"):
            # Skip string literals
            quote = ch
            i += 1
            while i < len(source):
                if source[i] == "\\":
                    i += 2
                    continue
                if source[i] == quote:
                    break
                i += 1
        i += 1
    return None


def _parse_ts_params(param_str):
    """Parse content between ( and ) into a list of {"name": str, "type": str|None}.

    Handles: name, name: Type, name?: Type, name: Type = default, ...rest: Type[]
    """
    param_str = param_str.strip()
    if not param_str:
        return []

    parts = _split_ts_params(param_str)
    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Strip default value (everything after = at depth 0)
        eq_idx = _find_top_level_eq(part)
        if eq_idx >= 0:
            part = part[:eq_idx].strip()

        # Handle rest params: ...name: Type
        rest_prefix = ""
        if part.startswith("..."):
            rest_prefix = "..."
            part = part[3:]

        # Split name and type on the first colon at depth 0
        colon_idx = _find_top_level_colon(part)
        if colon_idx > 0:
            name = rest_prefix + part[:colon_idx].strip().rstrip("?")
            ptype = part[colon_idx + 1 :].strip()
            result.append({"name": name, "type": ptype if ptype else None})
        else:
            name = rest_prefix + part.strip().rstrip("?")
            result.append({"name": name, "type": None})

    return result


def _split_ts_params(s):
    """Split parameter string by commas, respecting nested brackets/parens."""
    parts = []
    depth = 0
    current = []
    for ch in s:
        if ch in ("(", "<", "[", "{"):
            depth += 1
            current.append(ch)
        elif ch in (")", ">", "]", "}"):
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


def _find_top_level_eq(s):
    """Find the first '=' at depth 0 that is not part of => or ==."""
    depth = 0
    for i, ch in enumerate(s):
        if ch in ("(", "<", "[", "{"):
            depth += 1
        elif ch in (")", ">", "]", "}"):
            depth -= 1
        elif ch == "=" and depth == 0:
            # Skip => (arrow) and == / === (equality)
            if i + 1 < len(s) and s[i + 1] in ("=", ">"):
                continue
            return i
    return -1


def _find_top_level_colon(s):
    """Find the first ':' at depth 0 in a string. Returns index or -1."""
    depth = 0
    for i, ch in enumerate(s):
        if ch in ("(", "<", "[", "{"):
            depth += 1
        elif ch in (")", ">", "]", "}"):
            depth -= 1
        elif ch == ":" and depth == 0:
            return i
    return -1


def _extract_ts_return_type(after_paren):
    """Extract return type from the text after the closing ')'.

    Looks for ': ReturnType' before '{' or newline.
    """
    # after_paren starts with ')'
    text = after_paren.lstrip(")")
    text = text.lstrip()
    if not text.startswith(":"):
        return None
    text = text[1:].lstrip()

    # Collect until { or newline, respecting nested brackets
    depth = 0
    result = []
    for ch in text:
        if ch in ("{",) and depth == 0:
            break
        if ch == "\n" and depth == 0:
            break
        if ch in ("(", "<", "["):
            depth += 1
        elif ch in (")", ">", "]"):
            depth -= 1
        result.append(ch)

    return_type = "".join(result).strip()
    return return_type if return_type else None


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


def _handle_module(path, target, body, source_paths, base_dir, attrs):
    """Extract module-level JSDoc and exported declarations from a TS/JS file."""
    if not path:
        return format_error(":::module requires a file path argument")

    filepath = _resolve_file_path(path, source_paths, base_dir)
    if filepath is None:
        return format_error(f"module '{path}' not found")

    source, err = read_source(filepath)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    # Display name: strip extension, use forward slashes
    display_name = path.replace("\\", "/")
    for ext in _TS_JS_EXTENSIONS:
        if display_name.endswith(ext):
            display_name = display_name[: -len(ext)]
            break

    parts = []
    parts.append(f"## {display_name}")

    # Module-level JSDoc: the first /** */ block before any declaration
    module_jsdoc = _extract_module_jsdoc(source)
    if module_jsdoc:
        parts.append("")
        parts.append(module_jsdoc["description"])

    # Extract all exported declarations with their JSDoc
    exports = _extract_exports(source)

    if target:
        matched = [e for e in exports if e["name"] == target]
        if not matched:
            return format_error(f"symbol '{target}' not found in '{path}'")
        export = matched[0]
        parts_t = []
        parts_t.append(f"### {export['name']}")
        parts_t.append("")
        lang = "typescript" if filepath.endswith((".ts", ".tsx")) else "javascript"
        parts_t.append(f"```{lang}\n{export['signature']}\n```")
        if export["jsdoc"]:
            parts_t.append("")
            parts_t.append(_format_jsdoc_as_markdown(export["jsdoc"]))
        return "\n".join(parts_t)

    for export in exports:
        parts.append("")
        parts.append(f"### {export['name']}")
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

    # If followed by an export, distinguish module-level from function-attached JSDoc
    if re.match(r"export\s", after_text):
        parsed = _parse_jsdoc_text(match.group(1))
        # @module tag -- always module-level
        if any(t["tag"] == "module" for t in parsed.get("tags", [])):
            return parsed
        # @param or @returns/@return tags -- function doc, not module-level
        if parsed.get("params") or parsed.get("returns"):
            return None
        # Check for blank line between JSDoc end and export
        gap = source[after_pos:][: len(source[after_pos:]) - len(source[after_pos:].lstrip())]
        if gap.count("\n") >= 2:
            return parsed
        # No blank line -- attached to the export, not module-level
        return None

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

    # Second pass: scan for re-export patterns like export { X } and
    # export { X } from './other'. These are handled by public_symbols
    # but were missing from ref output.
    # Use MULTILINE so ^ matches each line start in the full source.
    reexport_pattern = re.compile(r"^export\s*\{([^}]+)\}", re.MULTILINE)
    seen_names = {r["name"] for r in results}
    for match in reexport_pattern.finditer(source):
        # Extract the full line to check for a from clause
        line_start = match.start()
        line_end = source.find("\n", line_start)
        if line_end == -1:
            line_end = len(source)
        full_line = source[line_start:line_end].strip()

        # Parse the from clause if present
        from_match = re.search(r"""from\s+['"]([^'"]+)['"]""", full_line)
        from_module = from_match.group(1) if from_match else None

        names_str = match.group(1)
        for name_part in names_str.split(","):
            name_part = name_part.strip()
            if not name_part:
                continue

            # Handle aliases: export { Foo as Bar }
            if " as " in name_part:
                original, alias = name_part.split(" as ", 1)
                original = original.strip()
                exported_name = alias.strip()
            else:
                original = name_part
                exported_name = name_part

            if exported_name in seen_names:
                continue
            seen_names.add(exported_name)

            # Try to find a local declaration for the original name
            local = _find_local_declaration(source, original)
            if local:
                signature = local["signature"]
                jsdoc = local["jsdoc"]
            elif from_module:
                signature = f"export {{ {name_part} }} from '{from_module}'"
                jsdoc = None
            else:
                signature = f"export {{ {name_part} }}"
                jsdoc = None

            results.append(
                {"name": exported_name, "signature": signature, "jsdoc": jsdoc}
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


def _find_local_declaration(source, name):
    """Find a local (non-exported or exported) declaration for a symbol name.

    Searches for class, function, interface, type, const/let/var, and enum
    declarations. Returns {"signature": str, "jsdoc": parsed|None} or None.
    """
    # Pattern matches both exported and non-exported declarations
    decl_pattern = re.compile(
        r"^((?:export\s+)?(?:default\s+)?(?:async\s+)?"
        r"(?:function\s*\*?\s*|class\s+|interface\s+|type\s+|const\s+|let\s+|var\s+|enum\s+)"
        + re.escape(name)
        + r"[^\n{;]*(?:[{;]|\([^)]*\)[^{;]*[{;])?)",
        re.MULTILINE,
    )
    match = decl_pattern.search(source)
    if match is None:
        return None

    sig_raw = match.group(1).strip()
    signature = re.sub(r"\s*[{;]\s*$", "", sig_raw).strip()
    jsdoc = _find_jsdoc_before(source, match.start())
    return {"signature": signature, "jsdoc": jsdoc}


# ---------------------------------------------------------------------------
# :::test
# ---------------------------------------------------------------------------


def _handle_test(path, target, body, source_paths, base_dir, attrs):
    """Extract test source code from a test file.

    path: file path to the test file
    target: optional test name (describe/it/test block name)

    For TS/JS test files, looks for describe("TestName", ...),
    it("TestName", ...), or test("TestName", ...) blocks.
    """
    if not path:
        return format_error(":::test requires a file path argument")

    # Resolve the file
    full_path = os.path.join(base_dir, path)
    if not os.path.isfile(full_path):
        # Try with source paths
        full_path = _resolve_file_path(path, source_paths, base_dir)
        if full_path is None:
            return format_error(f"test file '{path}' not found")

    source, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    lang = "typescript" if full_path.endswith((".ts", ".tsx")) else "javascript"

    if target is None:
        return f"```{lang}\n{source.rstrip()}\n```"

    # Find the target test block by name
    block = _extract_test_block(source, target)
    if block is None:
        return format_error(f"'{target}' not found in '{path}'")

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


def _handle_schema(path, target, body, source_paths, base_dir, attrs):
    """Extract interface or type definition fields as a markdown table.

    path: file path (JSON or TS/JS)
    target: optional type name for TS/JS files

    Modes:
      - path/to/file.json  -> render JSON keys as table
      - path/to/file.ts TypeName -> extract interface/type fields
      - path/to/file.ts -> if only one interface, extract it
    """
    if not path:
        return format_error(":::schema requires an argument")

    # Check if it's a JSON file
    if path.endswith(".json"):
        full_path = os.path.join(base_dir, path)
        if not os.path.isfile(full_path):
            return format_error(f"JSON file '{path}' not found")
        exclude_keys = parse_comma_set(attrs["exclude"]) if attrs.get("exclude") else None
        return _config_from_json(full_path, path, exclude_keys=exclude_keys)

    # TS/JS file with optional type name
    filepath = _resolve_file_path(path, source_paths, base_dir)
    if filepath is None:
        return format_error(f"file '{path}' not found")

    source, err = read_source(filepath)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    return _schema_from_ts(source, target, path)



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
            return format_error(
                f"type '{type_name}' not found in '{display_path}'"
            )
        return format_error(f"no interfaces or types found in '{display_path}'")

    # If type_name specified, use the first match; otherwise use first found
    kind, name, match = targets[0]

    # Extract the body of the interface/type (track brace depth)
    body_start = match.end()  # position right after the opening {
    body_text = _extract_brace_block(source, body_start - 1)
    if body_text is None:
        return format_error(f"could not parse body of '{name}'")

    # Parse fields from the body
    fields = _parse_interface_fields(body_text)

    if not fields:
        return format_error(f"no fields found in '{name}'")

    rows = []
    for field in fields:
        desc = field.get("description", "")
        rows.append([f"`{field['name']}`", f"`{field['type']}`", desc])

    return render_markdown_table(["Field", "Type", "Description"], rows)


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


def _handle_cli(path, target, body, source_paths, base_dir, attrs):
    """Extract CLI help/usage information from a TS/JS file.

    Looks for:
    - Module-level JSDoc comment
    - const help = "..." or const usage = "..." string constants
    - yargs/commander setup patterns
    """
    if not path:
        return format_error(":::cli requires a file path argument")

    filepath = _resolve_file_path(path, source_paths, base_dir)
    if filepath is None:
        return format_error(f"module '{path}' not found")

    source, err = read_source(filepath)
    if err:
        return format_error(f"cannot read '{path}': {err}")

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
        return format_error(f"no CLI documentation found in '{path}'")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# :::config
# ---------------------------------------------------------------------------


def _handle_config(path, target, body, source_paths, base_dir, attrs):
    """TypeScript config handler -- adds JSONC support to the base handler."""
    if path:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".jsonc":
            full_path = os.path.join(base_dir, path)
            if not os.path.isfile(full_path):
                return format_error(f"config file '{path}' not found")
            exclude_keys = parse_comma_set(attrs["exclude"]) if attrs.get("exclude") else None
            return _config_from_jsonc(full_path, path, exclude_keys=exclude_keys)
    return handle_table_config(path, None, body, source_paths, base_dir, attrs)


def _config_from_jsonc(full_path, display_path, exclude_keys: set[str] | None = None):
    """Parse JSONC config (strip comments) and render as a key-value table."""
    raw, err = read_source(full_path)
    if err:
        return format_error(f"cannot read '{display_path}': {err}")

    stripped = _strip_jsonc_comments(raw)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return format_error(f"cannot parse '{display_path}': {exc}")

    if not isinstance(data, dict):
        return f"```json\n{json.dumps(data, indent=2)}\n```"

    result = apply_exclude_keys(data, exclude_keys, display_path)
    if isinstance(result, str):
        return result
    data = result

    rows = []
    for key, value in data.items():
        type_name = _json_type_name(value)
        value_repr = _json_value_repr(value)
        rows.append([f"`{key}`", type_name, value_repr])

    return render_markdown_table(["Key", "Type", "Value"], rows)


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


# ---------------------------------------------------------------------------
# :::prose-desc
# ---------------------------------------------------------------------------


def _handle_prose_desc(path, target, body, source_paths, base_dir, attrs):
    """Extract only the module-level JSDoc as prose markdown.

    Unlike :::module which also lists exported declarations, this directive
    returns just the module-level JSDoc description.
    """
    if not path:
        return format_error(":::prose-desc requires a file path argument")

    filepath = _resolve_file_path(path, source_paths, base_dir)
    if filepath is None:
        return format_error(f"module '{path}' not found")

    source, err = read_source(filepath)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    module_jsdoc = _extract_module_jsdoc(source)
    if not module_jsdoc or not module_jsdoc["description"]:
        return format_error(f"no module-level JSDoc found in '{path}'")

    return module_jsdoc["description"]


TypeScriptExtractor._HANDLERS = {
    "ref": _handle_module,
    "code-test": _handle_test,
    "table-schema": _handle_schema,
    "code-help": _handle_cli,
    "table-config": _handle_config,
    "prose-desc": _handle_prose_desc,
}
