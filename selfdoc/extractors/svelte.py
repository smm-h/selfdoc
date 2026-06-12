"""Svelte source extractor for selfdoc -- parses .svelte files to extract component props, exports, and documentation.

Uses regex-based parsing (no Svelte compiler required). Handles:
- :::ref         -- extract component props, instance exports, module exports
- :::prose-desc  -- extract component-level doc comments only
- :::table-schema -- extract props as a table
- :::table-config -- extract config file contents as tables (JSON/TOML)
"""

import os
import re

from selfdoc.extractors.base import (
    BaseExtractor,
    format_error,
    handle_table_config,
    read_source,
)
from selfdoc.extractors.typescript import _parse_jsdoc_text
from selfdoc.tables import render_markdown_table

# ---------------------------------------------------------------------------
# Script block extraction
# ---------------------------------------------------------------------------

# Module script: has context="module" or module attribute
_MODULE_SCRIPT_RE = re.compile(
    r"<script\b[^>]*(?:context=[\"']module[\"']|\bmodule\b)[^>]*>(.*?)</script>",
    re.DOTALL,
)

# Any script block (used after stripping module scripts)
_INSTANCE_SCRIPT_RE = re.compile(
    r"<script\b(?:\s+(?:lang=[\"'](?:ts|js)[\"']))*\s*>(.*?)</script>",
    re.DOTALL,
)

# General script tag (any attributes)
_ANY_SCRIPT_RE = re.compile(
    r"<script\b[^>]*>(.*?)</script>",
    re.DOTALL,
)


def _extract_script_blocks(source):
    """Extract instance and module script block contents from a .svelte file.

    Returns a dict with:
      "instance": content of the instance (default) script block
      "module": content of the module script block
    """
    module_content = ""
    instance_content = ""

    # Find module script first
    module_match = _MODULE_SCRIPT_RE.search(source)
    if module_match:
        module_content = module_match.group(1)

    # Find all script blocks, pick the instance one (not module)
    for match in _ANY_SCRIPT_RE.finditer(source):
        tag = match.group(0)
        # Skip if this is the module script
        if 'context="module"' in tag or "context='module'" in tag or re.search(r"\bmodule\b", tag.split(">")[0]):
            continue
        instance_content = match.group(1)
        break

    return {"instance": instance_content, "module": module_content}


# ---------------------------------------------------------------------------
# Props extraction ($props() rune pattern -- Svelte 5)
# ---------------------------------------------------------------------------

_PROPS_CALL_RE = re.compile(
    r"(?:let|const)\s+\{([^}]*)\}(?:\s*:\s*(.+?))?\s*=\s*\$props\(\)",
    re.DOTALL,
)

_BINDABLE_RE = re.compile(r"^\$bindable\((.*)\)$")


def _extract_props(script_content):
    """Extract props from $props() destructuring in a Svelte 5 component.

    Returns a list of dicts: {name, type, default, bindable}.
    """
    match = _PROPS_CALL_RE.search(script_content)
    if not match:
        return []

    destructure_content = match.group(1)
    type_annotation = match.group(2).strip() if match.group(2) else ""

    # Parse individual prop types from inline type annotation
    # e.g. { name: string; count: number }
    prop_types = {}
    interface_name = ""
    if type_annotation:
        type_stripped = type_annotation.strip()
        if type_stripped.startswith("{") and type_stripped.endswith("}"):
            # Inline type: { name: string; count: number }
            inner = type_stripped[1:-1]
            for part in re.split(r"[;,]", inner):
                part = part.strip()
                if not part:
                    continue
                colon_idx = part.find(":")
                if colon_idx > 0:
                    pname = part[:colon_idx].strip().lstrip("?")
                    ptype = part[colon_idx + 1:].strip()
                    prop_types[pname] = ptype
        else:
            # Single type name (e.g. Props)
            interface_name = type_stripped

    # Parse the destructuring content into individual props
    props = []
    items = _split_destructure(destructure_content)

    for item in items:
        item = item.strip()
        if not item:
            continue

        # Rest element: ...rest
        if item.startswith("..."):
            rest_name = item[3:].strip()
            props.append({
                "name": rest_name,
                "type": "",
                "default": "...rest",
                "bindable": False,
            })
            continue

        # Split on = for default value
        name, default, bindable = _parse_prop_item(item)

        # Determine type
        prop_type = prop_types.get(name, "")
        if not prop_type and interface_name:
            prop_type = interface_name

        props.append({
            "name": name,
            "type": prop_type,
            "default": default,
            "bindable": bindable,
        })

    return props


def _split_destructure(content):
    """Split destructuring content by commas, respecting nested parens and braces.

    Handles cases like: name, count = $bindable(defaultVal), other
    """
    items = []
    depth = 0
    current = []

    for ch in content:
        if ch in ("(", "{", "["):
            depth += 1
            current.append(ch)
        elif ch in (")", "}", "]"):
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)

    if current:
        items.append("".join(current))

    return items


def _parse_prop_item(item):
    """Parse a single destructured prop item.

    Returns (name, default, bindable).
    """
    # Find the first = not inside parens
    eq_idx = -1
    depth = 0
    for i, ch in enumerate(item):
        if ch in ("(", "{", "["):
            depth += 1
        elif ch in (")", "}", "]"):
            depth -= 1
        elif ch == "=" and depth == 0:
            eq_idx = i
            break

    if eq_idx < 0:
        # No default value
        name = item.strip()
        return name, "", False

    name = item[:eq_idx].strip()
    default_raw = item[eq_idx + 1:].strip()

    # Check for $bindable()
    bindable_match = _BINDABLE_RE.match(default_raw)
    if bindable_match:
        inner = bindable_match.group(1).strip()
        return name, inner, True

    return name, default_raw, False


# ---------------------------------------------------------------------------
# Legacy props extraction (export let -- Svelte 3/4)
# ---------------------------------------------------------------------------

_LEGACY_PROP_RE = re.compile(
    r"export\s+let\s+(\w+)(?:\s*:\s*([^=;]+?))?(?:\s*=\s*([^;]+?))?\s*;",
)


def _extract_legacy_props(script_content):
    """Extract props from export let declarations (Svelte 3/4 pattern).

    Returns a list of dicts: {name, type, default, bindable}.
    """
    props = []
    for match in _LEGACY_PROP_RE.finditer(script_content):
        name = match.group(1)
        prop_type = match.group(2).strip() if match.group(2) else ""
        default = match.group(3).strip() if match.group(3) else ""
        props.append({
            "name": name,
            "type": prop_type,
            "default": default,
            "bindable": False,
        })
    return props


# ---------------------------------------------------------------------------
# Instance and module exports extraction
# ---------------------------------------------------------------------------

_EXPORT_FUNC_RE = re.compile(
    r"export\s+(?:async\s+)?function\s+(\w+)\s*(\([^)]*\)(?:\s*:\s*[^{;]+)?)",
)
_EXPORT_CONST_RE = re.compile(
    r"export\s+const\s+(\w+)(?:\s*:\s*([^=]+?))?\s*=\s*([^;]+);",
)


def _extract_exports(script_content):
    """Extract exported functions and constants from a script block.

    Returns a list of dicts: {name, kind, signature}.
    """
    exports = []

    for match in _EXPORT_FUNC_RE.finditer(script_content):
        name = match.group(1)
        params = match.group(2).strip()
        sig = f"export function {name}{params}"
        exports.append({"name": name, "kind": "function", "signature": sig})

    for match in _EXPORT_CONST_RE.finditer(script_content):
        name = match.group(1)
        type_ann = match.group(2).strip() if match.group(2) else ""
        value = match.group(3).strip()
        if type_ann:
            sig = f"export const {name}: {type_ann} = {value}"
        else:
            sig = f"export const {name} = {value}"
        exports.append({"name": name, "kind": "const", "signature": sig})

    return exports


def _extract_instance_exports(script_content):
    """Extract exported functions and constants from the instance script."""
    return _extract_exports(script_content)


def _extract_module_exports(script_content):
    """Extract exported functions and constants from the module script."""
    return _extract_exports(script_content)


# ---------------------------------------------------------------------------
# Component doc extraction (JSDoc at start of instance script)
# ---------------------------------------------------------------------------

_JSDOC_RE = re.compile(r"^\s*/\*\*\s*\n(.*?)\*/", re.DOTALL)


def _extract_component_doc(source):
    """Extract the component-level JSDoc from the instance script block.

    Looks for a JSDoc comment (/** ... */) at the very beginning of the
    instance script block (before any code).

    Returns the description text, or empty string if none found.
    """
    blocks = _extract_script_blocks(source)
    instance = blocks["instance"]
    if not instance:
        return ""

    match = _JSDOC_RE.match(instance)
    if not match:
        return ""

    parsed = _parse_jsdoc_text(match.group(1))
    return parsed["description"]


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _resolve_svelte_path(path_arg, source_paths, base_dir):
    """Resolve a path argument to a .svelte file on disk.

    Tries path as-is, then with source_paths, then with .svelte extension appended.
    """
    candidates = []

    candidates.append(os.path.join(base_dir, path_arg))
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, path_arg))

    # If no .svelte extension, try appending it
    _, ext = os.path.splitext(path_arg)
    if ext != ".svelte":
        candidates.append(os.path.join(base_dir, path_arg + ".svelte"))
        for sp in source_paths:
            candidates.append(os.path.join(base_dir, sp, path_arg + ".svelte"))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return None


# ---------------------------------------------------------------------------
# Extractor class
# ---------------------------------------------------------------------------


class SvelteExtractor(BaseExtractor):
    """Svelte language extractor implementing LanguageExtractor protocol."""

    @property
    def name(self) -> str:
        return "svelte"

    def detect(self, dir_path: str) -> bool:
        return os.path.isfile(
            os.path.join(dir_path, "svelte.config.js")
        ) or os.path.isfile(os.path.join(dir_path, "svelte.config.ts"))

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None:
        return _resolve_svelte_path(path_arg, source_paths, base_dir)

    def file_extensions(self) -> list[str]:
        return [".svelte"]

    def public_symbols(self, file_path: str) -> list[str]:
        """Extract public symbols from a .svelte file.

        Returns: component name (from filename), prop names, instance export
        names, module export names. All as a flat list.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        # Component name from filename
        basename = os.path.basename(file_path)
        component_name = os.path.splitext(basename)[0]
        symbols = [component_name]

        blocks = _extract_script_blocks(source)

        # Props (try Svelte 5 first, fall back to legacy)
        props = _extract_props(blocks["instance"])
        if not props:
            props = _extract_legacy_props(blocks["instance"])
        for prop in props:
            if prop["name"] not in symbols:
                symbols.append(prop["name"])

        # Instance exports
        for exp in _extract_instance_exports(blocks["instance"]):
            if exp["name"] not in symbols:
                symbols.append(exp["name"])

        # Module exports
        for exp in _extract_module_exports(blocks["module"]):
            if exp["name"] not in symbols:
                symbols.append(exp["name"])

        return symbols


# ---------------------------------------------------------------------------
# :::ref handler
# ---------------------------------------------------------------------------


def _handle_ref(arg, body, source_paths, base_dir, attrs):
    """Extract component reference documentation from a .svelte file.

    Shows component name, component-level JSDoc, props table, instance
    exports, and module exports.
    """
    if not arg:
        return format_error("ref requires a file path argument")

    filepath = _resolve_svelte_path(arg, source_paths, base_dir)
    if filepath is None:
        return format_error(f"component '{arg}' not found")

    source, err = read_source(filepath)
    if err:
        return format_error(f"cannot read '{arg}': {err}")

    # Component name from filename
    basename = os.path.basename(filepath)
    component_name = os.path.splitext(basename)[0]

    blocks = _extract_script_blocks(source)

    parts = []
    parts.append(f"## {component_name}")

    # Component-level doc
    comp_doc = _extract_component_doc(source)
    if comp_doc:
        parts.append("")
        parts.append(comp_doc)

    # Props (try Svelte 5 first, fall back to legacy)
    props = _extract_props(blocks["instance"])
    if not props:
        props = _extract_legacy_props(blocks["instance"])

    if props:
        parts.append("")
        parts.append("### Props")
        parts.append("")
        rows = []
        for prop in props:
            bindable_str = "Yes" if prop["bindable"] else "No"
            rows.append([
                f"`{prop['name']}`",
                f"`{prop['type']}`" if prop["type"] else "",
                f"`{prop['default']}`" if prop["default"] else "",
                bindable_str,
            ])
        parts.append(render_markdown_table(
            ["Prop", "Type", "Default", "Bindable"], rows
        ))

    # Instance exports
    inst_exports = _extract_instance_exports(blocks["instance"])
    if inst_exports:
        parts.append("")
        parts.append("### Instance Exports")
        for exp in inst_exports:
            parts.append("")
            parts.append(f"#### {exp['name']}")
            parts.append("")
            parts.append(f"```typescript\n{exp['signature']}\n```")

    # Module exports
    mod_exports = _extract_module_exports(blocks["module"])
    if mod_exports:
        parts.append("")
        parts.append("### Module Exports")
        for exp in mod_exports:
            parts.append("")
            parts.append(f"#### {exp['name']}")
            parts.append("")
            parts.append(f"```typescript\n{exp['signature']}\n```")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# :::prose-desc handler
# ---------------------------------------------------------------------------


def _handle_prose_desc(arg, body, source_paths, base_dir, attrs):
    """Extract only the component-level JSDoc as prose markdown."""
    if not arg:
        return format_error("prose-desc requires a file path argument")

    filepath = _resolve_svelte_path(arg, source_paths, base_dir)
    if filepath is None:
        return format_error(f"component '{arg}' not found")

    source, err = read_source(filepath)
    if err:
        return format_error(f"cannot read '{arg}': {err}")

    doc = _extract_component_doc(source)
    if not doc:
        return format_error(f"no component-level JSDoc found in '{arg}'")

    return doc


# ---------------------------------------------------------------------------
# :::table-schema handler
# ---------------------------------------------------------------------------


def _handle_table_schema(arg, body, source_paths, base_dir, attrs):
    """Extract props as a markdown table.

    For .svelte files, extracts the props table.
    For JSON/TOML files, delegates to handle_table_config.
    """
    if not arg:
        return format_error("table-schema requires a file path argument")

    # Check if it's a config file (JSON/TOML)
    _, ext = os.path.splitext(arg)
    if ext.lower() in (".json", ".toml"):
        return handle_table_config(arg, body, source_paths, base_dir, attrs)

    filepath = _resolve_svelte_path(arg, source_paths, base_dir)
    if filepath is None:
        return format_error(f"component '{arg}' not found")

    source, err = read_source(filepath)
    if err:
        return format_error(f"cannot read '{arg}': {err}")

    blocks = _extract_script_blocks(source)

    # Props (try Svelte 5 first, fall back to legacy)
    props = _extract_props(blocks["instance"])
    if not props:
        props = _extract_legacy_props(blocks["instance"])

    if not props:
        return format_error(f"no props found in '{arg}'")

    rows = []
    for prop in props:
        bindable_str = "Yes" if prop["bindable"] else "No"
        rows.append([
            f"`{prop['name']}`",
            f"`{prop['type']}`" if prop["type"] else "",
            f"`{prop['default']}`" if prop["default"] else "",
            bindable_str,
        ])

    return render_markdown_table(["Prop", "Type", "Default", "Bindable"], rows)


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------

SvelteExtractor._HANDLERS = {
    "ref": _handle_ref,
    "prose-desc": _handle_prose_desc,
    "table-schema": _handle_table_schema,
    "table-config": handle_table_config,
}
