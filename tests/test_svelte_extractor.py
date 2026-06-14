"""Tests for the Svelte source extractor (selfdoc.extractors.svelte)."""

import os

import pytest

from selfdoc.extractors.svelte import (
    SvelteExtractor,
    _extract_component_doc,
    _extract_exports,
    _extract_legacy_props,
    _extract_props,
    _extract_script_blocks,
)


@pytest.fixture()
def svelte_project(tmp_path):
    """Create a sample Svelte project structure for testing."""
    src_dir = os.path.join(tmp_path, "src", "lib")
    os.makedirs(src_dir)

    # Main component with props, instance exports, module exports, and JSDoc
    counter_svelte = os.path.join(src_dir, "Counter.svelte")
    with open(counter_svelte, "w", encoding="utf-8") as f:
        f.write("""\
<script lang="ts">
/**
 * A counter component with increment and reset functionality.
 */
let { count = 0, label, value = $bindable(), onchange }: { count: number; label: string; value: number; onchange: () => void } = $props();

export function reset() {
    count = 0;
}

export const defaultCount = 10;
</script>

<button on:click={() => count++}>{label}: {count}</button>
""")

    # Component with module script
    utils_svelte = os.path.join(src_dir, "Utils.svelte")
    with open(utils_svelte, "w", encoding="utf-8") as f:
        f.write("""\
<script module>
export function pauseAll() {
    // pause all instances
}

export const VERSION = '1.0';
</script>

<script lang="ts">
let { name, size = 'medium' } = $props();

export function refresh() {
    // refresh this instance
}
</script>

<div>{name}</div>
""")

    # Component with legacy props
    legacy_svelte = os.path.join(src_dir, "Legacy.svelte")
    with open(legacy_svelte, "w", encoding="utf-8") as f:
        f.write("""\
<script>
export let name = 'world';
export let count;
export let size: string = 'medium';
</script>

<p>Hello {name}!</p>
""")

    # Component with rest props
    rest_svelte = os.path.join(src_dir, "WithRest.svelte")
    with open(rest_svelte, "w", encoding="utf-8") as f:
        f.write("""\
<script lang="ts">
let { name, ...rest } = $props();
</script>

<div {...rest}>{name}</div>
""")

    # Component with interface-typed props
    typed_svelte = os.path.join(src_dir, "Typed.svelte")
    with open(typed_svelte, "w", encoding="utf-8") as f:
        f.write("""\
<script lang="ts">
let { name, count }: Props = $props();
</script>

<span>{name}: {count}</span>
""")

    # Blank component (no script block)
    blank_svelte = os.path.join(src_dir, "Blank.svelte")
    with open(blank_svelte, "w", encoding="utf-8") as f:
        f.write("<p>Static content</p>\n")

    # Component with empty script block
    empty_script_svelte = os.path.join(src_dir, "EmptyScript.svelte")
    with open(empty_script_svelte, "w", encoding="utf-8") as f:
        f.write("""\
<script>
</script>

<p>Content</p>
""")

    # Component with context="module" syntax
    context_module_svelte = os.path.join(src_dir, "ContextModule.svelte")
    with open(context_module_svelte, "w", encoding="utf-8") as f:
        f.write("""\
<script context="module">
export const SHARED = 'shared';
</script>

<script>
let { title } = $props();
</script>

<h1>{title}</h1>
""")

    # Component with $bindable() having a default value
    bindable_default_svelte = os.path.join(src_dir, "BindableDefault.svelte")
    with open(bindable_default_svelte, "w", encoding="utf-8") as f:
        f.write("""\
<script lang="ts">
let { value = $bindable(42) } = $props();
</script>

<input bind:value />
""")

    # Marker file
    config_js = os.path.join(tmp_path, "svelte.config.js")
    with open(config_js, "w", encoding="utf-8") as f:
        f.write("export default {};\n")

    return tmp_path


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class TestDetection:
    def test_detect_with_svelte_config_js(self, svelte_project):
        ext = SvelteExtractor()
        assert ext.detect(str(svelte_project)) is True

    def test_detect_with_svelte_config_ts(self, tmp_path):
        config_ts = os.path.join(tmp_path, "svelte.config.ts")
        with open(config_ts, "w", encoding="utf-8") as f:
            f.write("export default {};\n")
        ext = SvelteExtractor()
        assert ext.detect(str(tmp_path)) is True

    def test_detect_without_svelte_config(self, tmp_path):
        ext = SvelteExtractor()
        assert ext.detect(str(tmp_path)) is False


# ---------------------------------------------------------------------------
# File extensions
# ---------------------------------------------------------------------------


class TestFileExtensions:
    def test_file_extensions(self):
        ext = SvelteExtractor()
        assert ext.file_extensions() == [".svelte"]


# ---------------------------------------------------------------------------
# Script block extraction
# ---------------------------------------------------------------------------


class TestScriptBlockExtraction:
    def test_instance_script(self):
        source = '<script lang="ts">\nlet x = 1;\n</script>\n<p>hi</p>'
        blocks = _extract_script_blocks(source)
        assert "let x = 1;" in blocks["instance"]
        assert blocks["module"] == ""

    def test_module_script(self):
        source = "<script module>\nexport const A = 1;\n</script>\n<p>hi</p>"
        blocks = _extract_script_blocks(source)
        assert "export const A = 1;" in blocks["module"]

    def test_both_scripts(self, svelte_project):
        filepath = os.path.join(svelte_project, "src", "lib", "Utils.svelte")
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        blocks = _extract_script_blocks(source)
        assert "pauseAll" in blocks["module"]
        assert "VERSION" in blocks["module"]
        assert "refresh" in blocks["instance"]
        assert "name" in blocks["instance"]

    def test_no_script_block(self):
        source = "<p>Just HTML</p>"
        blocks = _extract_script_blocks(source)
        assert blocks["instance"] == ""
        assert blocks["module"] == ""

    def test_context_module_syntax(self, svelte_project):
        filepath = os.path.join(
            svelte_project, "src", "lib", "ContextModule.svelte"
        )
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        blocks = _extract_script_blocks(source)
        assert "SHARED" in blocks["module"]
        assert "title" in blocks["instance"]

    def test_plain_script_no_lang(self):
        source = "<script>\nlet y = 2;\n</script>"
        blocks = _extract_script_blocks(source)
        assert "let y = 2;" in blocks["instance"]

    def test_lang_js(self):
        source = '<script lang="js">\nlet z = 3;\n</script>'
        blocks = _extract_script_blocks(source)
        assert "let z = 3;" in blocks["instance"]


# ---------------------------------------------------------------------------
# Props: $props() destructuring (Svelte 5)
# ---------------------------------------------------------------------------


class TestPropsExtraction:
    def test_basic_destructuring(self):
        script = "let { name, count } = $props();"
        props = _extract_props(script)
        assert len(props) == 2
        assert props[0]["name"] == "name"
        assert props[1]["name"] == "count"

    def test_default_values(self):
        script = "let { name = 'hello', count = 0 } = $props();"
        props = _extract_props(script)
        assert props[0]["name"] == "name"
        assert props[0]["default"] == "'hello'"
        assert props[1]["name"] == "count"
        assert props[1]["default"] == "0"

    def test_bindable(self):
        script = "let { value = $bindable() } = $props();"
        props = _extract_props(script)
        assert len(props) == 1
        assert props[0]["name"] == "value"
        assert props[0]["bindable"] is True

    def test_bindable_with_default(self):
        script = "let { value = $bindable(42) } = $props();"
        props = _extract_props(script)
        assert len(props) == 1
        assert props[0]["name"] == "value"
        assert props[0]["bindable"] is True
        assert props[0]["default"] == "42"

    def test_inline_typed_props(self):
        script = "let { name, count }: { name: string; count: number } = $props();"
        props = _extract_props(script)
        assert len(props) == 2
        assert props[0]["name"] == "name"
        assert props[0]["type"] == "string"
        assert props[1]["name"] == "count"
        assert props[1]["type"] == "number"

    def test_interface_typed_props(self):
        script = "let { name, count }: Props = $props();"
        props = _extract_props(script)
        assert len(props) == 2
        # Interface name is assigned to all props
        assert props[0]["type"] == "Props"
        assert props[1]["type"] == "Props"

    def test_rest_props(self):
        script = "let { name, ...rest } = $props();"
        props = _extract_props(script)
        assert len(props) == 2
        assert props[0]["name"] == "name"
        assert props[1]["name"] == "rest"
        assert props[1]["default"] == "...rest"

    def test_no_props_call(self):
        script = "let x = 1;"
        props = _extract_props(script)
        assert props == []


# ---------------------------------------------------------------------------
# Props: legacy export let (Svelte 3/4)
# ---------------------------------------------------------------------------


class TestLegacyPropsExtraction:
    def test_basic_export_let(self):
        script = "export let name;"
        props = _extract_legacy_props(script)
        assert len(props) == 1
        assert props[0]["name"] == "name"
        assert props[0]["default"] == ""
        assert props[0]["bindable"] is False

    def test_export_let_with_default(self):
        script = "export let name = 'world';"
        props = _extract_legacy_props(script)
        assert props[0]["default"] == "'world'"

    def test_export_let_with_type(self):
        script = "export let size: string = 'medium';"
        props = _extract_legacy_props(script)
        assert props[0]["name"] == "size"
        assert props[0]["type"] == "string"
        assert props[0]["default"] == "'medium'"

    def test_multiple_legacy_props(self, svelte_project):
        filepath = os.path.join(svelte_project, "src", "lib", "Legacy.svelte")
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        blocks = _extract_script_blocks(source)
        props = _extract_legacy_props(blocks["instance"])
        assert len(props) == 3
        names = [p["name"] for p in props]
        assert "name" in names
        assert "count" in names
        assert "size" in names


# ---------------------------------------------------------------------------
# Instance exports
# ---------------------------------------------------------------------------


class TestInstanceExports:
    def test_export_function(self):
        script = "export function reset() {\n    count = 0;\n}\n"
        exports = _extract_exports(script)
        funcs = [e for e in exports if e["kind"] == "function"]
        assert len(funcs) == 1
        assert funcs[0]["name"] == "reset"
        assert "export function reset()" in funcs[0]["signature"]

    def test_export_const(self):
        script = "export const defaultCount = 10;"
        exports = _extract_exports(script)
        consts = [e for e in exports if e["kind"] == "const"]
        assert len(consts) == 1
        assert consts[0]["name"] == "defaultCount"
        assert "10" in consts[0]["signature"]


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_module_exports(self, svelte_project):
        filepath = os.path.join(svelte_project, "src", "lib", "Utils.svelte")
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        blocks = _extract_script_blocks(source)
        exports = _extract_exports(blocks["module"])
        names = [e["name"] for e in exports]
        assert "pauseAll" in names
        assert "VERSION" in names


# ---------------------------------------------------------------------------
# public_symbols
# ---------------------------------------------------------------------------


class TestPublicSymbols:
    def test_all_categories(self, svelte_project):
        ext = SvelteExtractor()
        filepath = os.path.join(
            svelte_project, "src", "lib", "Counter.svelte"
        )
        symbols = ext.public_symbols(filepath)
        # Component name from filename
        assert "Counter" in symbols
        # Props
        assert "count" in symbols
        assert "label" in symbols
        assert "value" in symbols
        assert "onchange" in symbols
        # Instance exports
        assert "reset" in symbols
        assert "defaultCount" in symbols

    def test_module_exports_in_symbols(self, svelte_project):
        ext = SvelteExtractor()
        filepath = os.path.join(svelte_project, "src", "lib", "Utils.svelte")
        symbols = ext.public_symbols(filepath)
        assert "Utils" in symbols
        assert "pauseAll" in symbols
        assert "VERSION" in symbols
        # Instance props and exports too
        assert "name" in symbols
        assert "refresh" in symbols

    def test_blank_component(self, svelte_project):
        ext = SvelteExtractor()
        filepath = os.path.join(svelte_project, "src", "lib", "Blank.svelte")
        symbols = ext.public_symbols(filepath)
        # Only the component name
        assert symbols == ["Blank"]

    def test_legacy_props_in_symbols(self, svelte_project):
        ext = SvelteExtractor()
        filepath = os.path.join(svelte_project, "src", "lib", "Legacy.svelte")
        symbols = ext.public_symbols(filepath)
        assert "Legacy" in symbols
        assert "name" in symbols
        assert "count" in symbols
        assert "size" in symbols


# ---------------------------------------------------------------------------
# :::ref handler
# ---------------------------------------------------------------------------


class TestRef:
    def test_ref_shows_all_sections(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.extract(
            "ref",
            {"path": "src/lib/Counter.svelte"},
            [],
            [],
            str(svelte_project),
        )
        # Component heading
        assert "## Counter" in result
        # Component-level JSDoc
        assert "A counter component" in result
        # Props section
        assert "### Props" in result
        assert "`count`" in result
        assert "`label`" in result
        assert "`value`" in result
        # Bindable indicator
        assert "Yes" in result
        # Instance exports section
        assert "### Instance Exports" in result
        assert "#### reset" in result
        assert "#### defaultCount" in result
        # Code block
        assert "```typescript" in result

    def test_ref_module_exports(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.extract(
            "ref",
            {"path": "src/lib/Utils.svelte"},
            [],
            [],
            str(svelte_project),
        )
        assert "### Module Exports" in result
        assert "#### pauseAll" in result
        assert "#### VERSION" in result

    def test_ref_not_found(self):
        ext = SvelteExtractor()
        result = ext.extract(
            "ref",
            {"path": "nonexistent.svelte"},
            [],
            [],
            "/tmp",
        )
        assert "selfdoc:" in result
        assert "not found" in result

    def test_ref_no_arg(self):
        ext = SvelteExtractor()
        result = ext.extract("ref", {"path": ""}, [], [], "/tmp")
        assert "selfdoc:" in result
        assert "requires" in result

    def test_ref_with_target_prop(self, tmp_path):
        """ref directive with target for a prop renders only that prop."""
        svelte_file = tmp_path / "Button.svelte"
        svelte_file.write_text(
            '<script lang="ts">\n'
            '  let { label = "Click", disabled = false }: { label?: string; disabled?: boolean } = $props();\n'
            '</script>\n'
            '<button {disabled}>{label}</button>\n',
            encoding="utf-8",
        )
        result = SvelteExtractor().extract(
            "ref",
            {"path": "Button.svelte", "target": "label"},
            [],
            [],
            str(tmp_path),
        )
        assert "### label" in result or "label" in result
        assert "disabled" not in result

    def test_ref_with_target_not_found(self, tmp_path):
        svelte_file = tmp_path / "Button.svelte"
        svelte_file.write_text(
            '<script>\n'
            '  export let name = "world";\n'
            '</script>\n'
            '<p>Hello {name}</p>\n',
            encoding="utf-8",
        )
        result = SvelteExtractor().extract(
            "ref",
            {"path": "Button.svelte", "target": "nonexistent"},
            [],
            [],
            str(tmp_path),
        )
        assert "not found" in result


# ---------------------------------------------------------------------------
# :::prose-desc handler
# ---------------------------------------------------------------------------


class TestProseDesc:
    def test_prose_desc_extracts_doc(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.extract(
            "prose-desc",
            {"path": "src/lib/Counter.svelte"},
            [],
            [],
            str(svelte_project),
        )
        assert "A counter component" in result
        # Should NOT contain props or export info
        assert "### Props" not in result
        assert "### Instance Exports" not in result

    def test_prose_desc_no_doc(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.extract(
            "prose-desc",
            {"path": "src/lib/Legacy.svelte"},
            [],
            [],
            str(svelte_project),
        )
        assert "selfdoc:" in result
        assert "no component-level JSDoc" in result


# ---------------------------------------------------------------------------
# :::table-schema handler
# ---------------------------------------------------------------------------


class TestTableSchema:
    def test_props_table(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "src/lib/Counter.svelte"},
            [],
            [],
            str(svelte_project),
        )
        # Should produce a markdown table
        assert "| Prop | Type | Default | Bindable |" in result
        assert "`count`" in result
        assert "`label`" in result
        assert "`value`" in result

    def test_no_props(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "src/lib/Blank.svelte"},
            [],
            [],
            str(svelte_project),
        )
        assert "selfdoc:" in result
        assert "no props found" in result

    def test_legacy_props_table(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.extract(
            "table-schema",
            {"path": "src/lib/Legacy.svelte"},
            [],
            [],
            str(svelte_project),
        )
        assert "`name`" in result
        assert "`count`" in result
        assert "`size`" in result


# ---------------------------------------------------------------------------
# Blank script block
# ---------------------------------------------------------------------------


class TestBlankScript:
    def test_empty_script_no_props_no_exports(self, svelte_project):
        ext = SvelteExtractor()
        filepath = os.path.join(
            svelte_project, "src", "lib", "EmptyScript.svelte"
        )
        symbols = ext.public_symbols(filepath)
        # Only the component name
        assert symbols == ["EmptyScript"]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_registry_includes_svelte(self):
        from selfdoc.extractors import EXTRACTORS

        assert "svelte" in EXTRACTORS

    def test_detection_order_includes_svelte(self):
        from selfdoc.extractors import _DETECTION_ORDER

        names = [ext.name for ext in _DETECTION_ORDER]
        assert "svelte" in names

    def test_svelte_before_typescript_in_detection_order(self):
        from selfdoc.extractors import _DETECTION_ORDER

        names = [ext.name for ext in _DETECTION_ORDER]
        svelte_idx = names.index("svelte")
        ts_idx = names.index("typescript")
        assert svelte_idx < ts_idx, (
            f"svelte (idx={svelte_idx}) must come before "
            f"typescript (idx={ts_idx}) in detection order"
        )


# ---------------------------------------------------------------------------
# Unknown directive
# ---------------------------------------------------------------------------


class TestUnknownDirective:
    def test_unknown_directive_errors(self):
        ext = SvelteExtractor()
        result = ext.extract(
            "code-help",
            {"path": "test.svelte"},
            [],
            [],
            "/tmp",
        )
        assert "selfdoc:" in result
        assert "unknown directive" in result


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_resolve_svelte_file(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.resolve_path(
            "src/lib/Counter.svelte", [], str(svelte_project)
        )
        assert result is not None
        assert result.endswith("Counter.svelte")

    def test_resolve_svelte_with_source_paths(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.resolve_path(
            "Counter.svelte", ["src/lib/"], str(svelte_project)
        )
        assert result is not None
        assert result.endswith("Counter.svelte")

    def test_resolve_svelte_implicit_extension(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.resolve_path(
            "src/lib/Counter", [], str(svelte_project)
        )
        assert result is not None
        assert result.endswith("Counter.svelte")

    def test_resolve_svelte_not_found(self, svelte_project):
        ext = SvelteExtractor()
        result = ext.resolve_path(
            "nonexistent.svelte", [], str(svelte_project)
        )
        assert result is None


class TestModuleDocstring:
    def test_module_docstring(self, tmp_path):
        svelte_file = tmp_path / "Counter.svelte"
        svelte_file.write_text(
            "<script>\n"
            "/**\n"
            " * A counter component with reset.\n"
            " */\n"
            "let x = 1;\n"
            "</script>\n",
            encoding="utf-8",
        )
        ext = SvelteExtractor()
        result = ext.module_docstring(str(svelte_file))
        assert result == "A counter component with reset."


# ---------------------------------------------------------------------------
# symbol_details
# ---------------------------------------------------------------------------


class TestSymbolDetails:
    def test_symbol_details_exported_function(self, tmp_path):
        svelte_file = tmp_path / "Greet.svelte"
        svelte_file.write_text(
            "<script>\n"
            "/**\n"
            " * Greet someone.\n"
            " * @param name The person's name\n"
            " */\n"
            "export function greet(name: string, count: number): string {\n"
            "    return `Hello ${name}! (${count})`;\n"
            "}\n"
            "</script>\n",
            encoding="utf-8",
        )
        ext = SvelteExtractor()
        result = ext.symbol_details(str(svelte_file), "greet")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0] == {"name": "name", "type": "string", "documented": True}
        assert result["params"][1] == {"name": "count", "type": "number", "documented": False}
        assert result["return_type"] == "string"
        assert result["return_documented"] is False

    def test_symbol_details_component_returns_none(self, tmp_path):
        svelte_file = tmp_path / "MyComponent.svelte"
        svelte_file.write_text(
            "<script lang=\"ts\">\n"
            "let { name, count }: { name: string; count: number } = $props();\n"
            "</script>\n"
            "<p>{name}: {count}</p>\n",
            encoding="utf-8",
        )
        ext = SvelteExtractor()
        result = ext.symbol_details(str(svelte_file), "MyComponent")
        assert result is None

    def test_symbol_details_unknown_returns_none(self, tmp_path):
        svelte_file = tmp_path / "Simple.svelte"
        svelte_file.write_text(
            "<script>\n"
            "export function hello() {}\n"
            "</script>\n",
            encoding="utf-8",
        )
        ext = SvelteExtractor()
        result = ext.symbol_details(str(svelte_file), "nonexistent")
        assert result is None
