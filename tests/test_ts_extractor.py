"""Tests for the TypeScript/JavaScript source extractor (selfdoc.extractors.typescript)."""

import json
import os

import pytest

from selfdoc.extractors.typescript import TypeScriptExtractor


@pytest.fixture()
def ts_project(tmp_path):
    """Create a sample TypeScript project structure for testing."""
    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir)

    # Module with JSDoc, exported functions, interface, type, class
    core_ts = os.path.join(src_dir, "core.ts")
    with open(core_ts, "w", encoding="utf-8") as f:
        f.write('''\
/**
 * Core module for the widget library.
 *
 * Provides essential utilities for widget management.
 */

import type { Widget } from './types.js';

/**
 * Create a new widget with the given name and options.
 *
 * @param name - The widget name
 * @param options - Configuration options
 * @returns The created widget instance
 */
export function createWidget(name: string, options?: WidgetOptions): Widget {
  return { name, ...options };
}

/**
 * A processor that transforms widgets in bulk.
 */
export class WidgetProcessor {
  process(items: Widget[]): Widget[] {
    return items;
  }
}

/**
 * Configuration options for widget creation.
 */
export interface WidgetOptions {
  /** Widget width in pixels */
  width: number;
  /** Widget height in pixels */
  height: number;
  /** Whether the widget is visible */
  visible?: boolean;
  /** CSS class name for styling */
  className: string;
}

/**
 * Unique identifier for widgets.
 */
export type WidgetId = string | number;

export const DEFAULT_SIZE = 100;
''')

    return tmp_path


@pytest.fixture()
def js_project(tmp_path):
    """Create a sample JavaScript project structure for testing."""
    lib_dir = os.path.join(tmp_path, "lib")
    os.makedirs(lib_dir)

    utils_js = os.path.join(lib_dir, "utils.js")
    with open(utils_js, "w", encoding="utf-8") as f:
        f.write('''\
/**
 * Utility functions for data processing.
 *
 * Handles parsing, formatting, and validation.
 */

const path = require('path');

/**
 * Parse a configuration string into an object.
 *
 * @param raw - The raw config string
 * @param strict - Whether to enforce strict parsing
 * @returns Parsed configuration object
 */
export function parseConfig(raw, strict = false) {
  return JSON.parse(raw);
}

/**
 * Format a number as a human-readable string.
 *
 * @param value - The number to format
 * @returns Formatted string
 */
export function formatNumber(value) {
  return value.toLocaleString();
}
''')

    return tmp_path


@pytest.fixture()
def source_paths():
    return ["src/"]


# ---------------------------------------------------------------------------
# :::module tests
# ---------------------------------------------------------------------------


class TestModuleDirective:
    def test_extracts_module_jsdoc(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "ref", {"path": "core.ts"}, [], source_paths, str(ts_project)
        )
        assert "## core" in result
        assert "Core module for the widget library." in result
        assert "Provides essential utilities for widget management." in result

    def test_extracts_exported_function(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "ref", {"path": "core.ts"}, [], source_paths, str(ts_project)
        )
        assert "### createWidget" in result
        assert "export function createWidget" in result
        assert "```typescript" in result

    def test_extracts_jsdoc_params(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "ref", {"path": "core.ts"}, [], source_paths, str(ts_project)
        )
        assert "`name`" in result
        assert "`options`" in result
        assert "The widget name" in result
        assert "Configuration options" in result

    def test_extracts_jsdoc_returns(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "ref", {"path": "core.ts"}, [], source_paths, str(ts_project)
        )
        assert "The created widget instance" in result

    def test_extracts_exported_class(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "ref", {"path": "core.ts"}, [], source_paths, str(ts_project)
        )
        assert "### WidgetProcessor" in result
        assert "export class WidgetProcessor" in result

    def test_extracts_exported_interface(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "ref", {"path": "core.ts"}, [], source_paths, str(ts_project)
        )
        assert "### WidgetOptions" in result
        assert "export interface WidgetOptions" in result

    def test_extracts_exported_type(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "ref", {"path": "core.ts"}, [], source_paths, str(ts_project)
        )
        assert "### WidgetId" in result

    def test_extracts_exported_const(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "ref", {"path": "core.ts"}, [], source_paths, str(ts_project)
        )
        assert "### DEFAULT_SIZE" in result
        assert "export const DEFAULT_SIZE" in result

    def test_js_file_uses_javascript_lang(self, js_project):
        result = TypeScriptExtractor().extract(
            "ref", {"path": "utils.js"}, [], ["lib/"], str(js_project)
        )
        assert "```javascript" in result
        assert "### parseConfig" in result

    def test_missing_module_error(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "ref", {"path": "nonexistent.ts"}, [], source_paths, str(ts_project)
        )
        assert "not found" in result
        assert "nonexistent.ts" in result

    def test_empty_arg_error(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "ref", {}, [], source_paths, str(ts_project)
        )
        assert "requires" in result


# ---------------------------------------------------------------------------
# :::test tests
# ---------------------------------------------------------------------------


class TestTestDirective:
    @pytest.fixture()
    def test_file(self, tmp_path):
        """Create a test file for extraction."""
        tests_dir = os.path.join(tmp_path, "tests")
        os.makedirs(tests_dir)
        test_ts = os.path.join(tests_dir, "widget.test.ts")
        with open(test_ts, "w", encoding="utf-8") as f:
            f.write('''\
import { createWidget } from '../src/core';

describe("createWidget", () => {
  it("should create a widget with name", () => {
    const widget = createWidget("test");
    expect(widget.name).toBe("test");
  });

  it("should accept options", () => {
    const widget = createWidget("test", { width: 100 });
    expect(widget.width).toBe(100);
  });
});

describe("WidgetProcessor", () => {
  test("processes empty array", () => {
    const processor = new WidgetProcessor();
    expect(processor.process([])).toEqual([]);
  });
});
''')
        return tmp_path

    def test_extract_whole_file(self, test_file, source_paths):
        result = TypeScriptExtractor().extract(
            "code-test", {"path": "tests/widget.test.ts"}, [], source_paths, str(test_file)
        )
        assert "```typescript" in result
        assert "createWidget" in result
        assert "WidgetProcessor" in result

    def test_extract_describe_block(self, test_file, source_paths):
        result = TypeScriptExtractor().extract(
            "code-test",
            {"path": "tests/widget.test.ts", "target": "createWidget"},
            [],
            source_paths,
            str(test_file),
        )
        assert "```typescript" in result
        assert 'describe("createWidget"' in result
        assert "should create a widget with name" in result
        assert "should accept options" in result
        # Should not include the WidgetProcessor describe block
        assert "WidgetProcessor" not in result

    def test_extract_test_block(self, test_file, source_paths):
        result = TypeScriptExtractor().extract(
            "code-test",
            {"path": "tests/widget.test.ts", "target": "processes empty array"},
            [],
            source_paths,
            str(test_file),
        )
        assert "```typescript" in result
        assert 'test("processes empty array"' in result

    def test_missing_file_error(self, tmp_path, source_paths):
        result = TypeScriptExtractor().extract(
            "code-test",
            {"path": "tests/nonexistent.test.ts"},
            [],
            source_paths,
            str(tmp_path),
        )
        assert "not found" in result

    def test_target_not_found_error(self, test_file, source_paths):
        result = TypeScriptExtractor().extract(
            "code-test",
            {"path": "tests/widget.test.ts", "target": "nonexistentTest"},
            [],
            source_paths,
            str(test_file),
        )
        assert "not found" in result
        assert "nonexistentTest" in result

    def test_js_test_file(self, tmp_path):
        """Test extraction from a .test.js file."""
        tests_dir = os.path.join(tmp_path, "tests")
        os.makedirs(tests_dir)
        test_js = os.path.join(tests_dir, "util.test.js")
        with open(test_js, "w", encoding="utf-8") as f:
            f.write('''\
describe("formatNumber", () => {
  it("formats integers", () => {
    expect(formatNumber(1000)).toBe("1,000");
  });
});
''')

        result = TypeScriptExtractor().extract(
            "code-test", {"path": "tests/util.test.js"}, [], [], str(tmp_path)
        )
        assert "```javascript" in result
        assert "formatNumber" in result


# ---------------------------------------------------------------------------
# :::schema tests
# ---------------------------------------------------------------------------


class TestSchemaDirective:
    def test_extracts_interface_fields(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "table-schema",
            {"path": "core.ts", "target": "WidgetOptions"},
            [],
            source_paths,
            str(ts_project),
        )
        assert "| Field | Type | Description |" in result
        assert "| --- | --- | --- |" in result
        assert "`width`" in result
        assert "`number`" in result
        assert "Widget width in pixels" in result
        assert "`height`" in result
        assert "`visible`" in result
        assert "(optional)" in result
        assert "`className`" in result

    def test_json_schema_table(self, ts_project, source_paths):
        """JSON file should produce a markdown table."""
        schema_path = os.path.join(ts_project, "schema.json")
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(
                {"name": "widgets", "version": "1.0.0", "debug": True},
                f,
            )

        result = TypeScriptExtractor().extract(
            "table-schema", {"path": "schema.json"}, [], source_paths, str(ts_project)
        )
        assert "| Key | Type | Value |" in result
        assert "`name`" in result
        assert "string" in result

    def test_missing_type_error(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "table-schema",
            {"path": "core.ts", "target": "NoSuchType"},
            [],
            source_paths,
            str(ts_project),
        )
        assert "not found" in result
        assert "NoSuchType" in result

    def test_missing_file_error(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "table-schema", {"path": "missing.json"}, [], source_paths, str(ts_project)
        )
        assert "not found" in result

    def test_type_alias_object(self, tmp_path):
        """Test extraction from a type alias with object shape."""
        src_dir = os.path.join(tmp_path, "src")
        os.makedirs(src_dir)
        types_ts = os.path.join(src_dir, "types.ts")
        with open(types_ts, "w", encoding="utf-8") as f:
            f.write('''\
/** Point in 2D space. */
export type Point = {
  /** X coordinate */
  x: number;
  /** Y coordinate */
  y: number;
};
''')

        result = TypeScriptExtractor().extract(
            "table-schema", {"path": "types.ts", "target": "Point"}, [], ["src/"], str(tmp_path)
        )
        assert "| Field | Type | Description |" in result
        assert "`x`" in result
        assert "`y`" in result
        assert "X coordinate" in result
        assert "Y coordinate" in result


# ---------------------------------------------------------------------------
# :::cli tests
# ---------------------------------------------------------------------------


class TestCliDirective:
    def test_extracts_module_jsdoc(self, js_project):
        result = TypeScriptExtractor().extract(
            "code-help", {"path": "utils.js"}, [], ["lib/"], str(js_project)
        )
        assert "Utility functions for data processing." in result

    def test_extracts_help_constant(self, tmp_path):
        src_dir = os.path.join(tmp_path, "src")
        os.makedirs(src_dir)
        cli_ts = os.path.join(src_dir, "cli.ts")
        with open(cli_ts, "w", encoding="utf-8") as f:
            f.write('''\
/**
 * CLI entry point for the widget tool.
 */

const USAGE = `Usage: widget [options] <command>

Commands:
    create    Create a new widget
    list      List all widgets
`;
''')

        result = TypeScriptExtractor().extract(
            "code-help", {"path": "cli.ts"}, [], ["src/"], str(tmp_path)
        )
        assert "CLI entry point for the widget tool." in result
        assert "```" in result
        assert "Usage: widget [options] <command>" in result

    def test_missing_module_error(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "code-help", {"path": "nonexistent.ts"}, [], source_paths, str(ts_project)
        )
        assert "not found" in result


# ---------------------------------------------------------------------------
# :::config tests
# ---------------------------------------------------------------------------


class TestConfigDirective:
    def test_json_config_table(self, tmp_path):
        config_path = os.path.join(tmp_path, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"host": "localhost", "port": 3000, "ssl": False}, f)

        result = TypeScriptExtractor().extract(
            "table-config", {"path": "config.json"}, [], [], str(tmp_path)
        )
        assert "| Key | Type | Value |" in result
        assert "`host`" in result
        assert "string" in result
        assert "`port`" in result
        assert "integer" in result

    def test_jsonc_config_strips_comments(self, tmp_path):
        """JSONC files should have comments stripped before parsing."""
        config_path = os.path.join(tmp_path, "tsconfig.jsonc")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write('''\
{
  // Compiler options
  "target": "ES2020",
  "module": "commonjs",
  /* Multi-line
     comment */
  "strict": true
}
''')

        result = TypeScriptExtractor().extract(
            "table-config", {"path": "tsconfig.jsonc"}, [], [], str(tmp_path)
        )
        assert "| Key | Type | Value |" in result
        assert "`target`" in result
        assert "`module`" in result
        assert "`strict`" in result

    def test_missing_config_error(self, tmp_path):
        result = TypeScriptExtractor().extract(
            "table-config", {"path": "missing.json"}, [], [], str(tmp_path)
        )
        assert "not found" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unknown_directive(self, ts_project, source_paths):
        result = TypeScriptExtractor().extract(
            "unknown", {"path": "arg"}, [], source_paths, str(ts_project)
        )
        assert "unknown directive" in result

    def test_handles_both_ts_and_js(self, tmp_path):
        """Both .ts and .js files should be handled."""
        src = os.path.join(tmp_path, "src")
        os.makedirs(src)

        # Create a .ts file
        with open(os.path.join(src, "app.ts"), "w", encoding="utf-8") as f:
            f.write("export function hello(): string { return 'hi'; }\n")

        # Create a .js file
        with open(os.path.join(src, "app.js"), "w", encoding="utf-8") as f:
            f.write("export function hello() { return 'hi'; }\n")

        result_ts = TypeScriptExtractor().extract(
            "ref", {"path": "app.ts"}, [], ["src/"], str(tmp_path)
        )
        assert "### hello" in result_ts
        assert "```typescript" in result_ts

        result_js = TypeScriptExtractor().extract(
            "ref", {"path": "app.js"}, [], ["src/"], str(tmp_path)
        )
        assert "### hello" in result_js
        assert "```javascript" in result_js

    def test_file_not_found_returns_error(self, tmp_path):
        """Missing file should return a user-friendly error, not crash."""
        result = TypeScriptExtractor().extract(
            "ref", {"path": "does/not/exist.ts"}, [], ["src/"], str(tmp_path)
        )
        assert "not found" in result

    def test_export_default_function(self, tmp_path):
        """export default function should be extracted."""
        src = os.path.join(tmp_path, "src")
        os.makedirs(src)
        with open(os.path.join(src, "main.ts"), "w", encoding="utf-8") as f:
            f.write('''\
/**
 * Main entry point.
 *
 * @param args - CLI arguments
 */
export default function main(args: string[]): void {
  console.log(args);
}
''')

        result = TypeScriptExtractor().extract(
            "ref", {"path": "main.ts"}, [], ["src/"], str(tmp_path)
        )
        assert "### main" in result
        assert "export default function main" in result
        assert "CLI arguments" in result

    def test_interface_with_inline_comments(self, tmp_path):
        """Interface fields with // inline comments should be captured."""
        src = os.path.join(tmp_path, "src")
        os.makedirs(src)
        with open(os.path.join(src, "config.ts"), "w", encoding="utf-8") as f:
            f.write('''\
export interface AppConfig {
  host: string; // Server hostname
  port: number; // Server port
  debug: boolean; // Enable debug mode
}
''')

        result = TypeScriptExtractor().extract(
            "table-schema", {"path": "config.ts", "target": "AppConfig"}, [], ["src/"], str(tmp_path)
        )
        assert "`host`" in result
        assert "Server hostname" in result
        assert "`port`" in result
        assert "Server port" in result
