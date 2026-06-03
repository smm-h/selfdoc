"""Tests for the LanguageExtractor protocol, registry, and detection."""

import dataclasses

import pytest

from selfdoc.extractors import (
    EXTRACTORS,
    SourceEntry,
    detect_language,
    detect_languages,
    resolve_source_entries,
    source_paths,
)
from selfdoc.extractors.base import StubExtractor
from selfdoc.extractors.go import GoExtractor
from selfdoc.extractors.protocol import LanguageExtractor
from selfdoc.extractors.python import PythonExtractor
from selfdoc.extractors.typescript import TypeScriptExtractor
from selfdoc.extractors.zig import ZigExtractor


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_python_extractor_is_language_extractor(self):
        assert isinstance(PythonExtractor(), LanguageExtractor)

    def test_go_extractor_is_language_extractor(self):
        assert isinstance(GoExtractor(), LanguageExtractor)

    def test_typescript_extractor_is_language_extractor(self):
        assert isinstance(TypeScriptExtractor(), LanguageExtractor)

    def test_zig_extractor_is_language_extractor(self):
        assert isinstance(ZigExtractor(), LanguageExtractor)

    def test_stub_extractor_is_language_extractor(self):
        assert isinstance(StubExtractor("swift"), LanguageExtractor)


# ---------------------------------------------------------------------------
# StubExtractor
# ---------------------------------------------------------------------------


class TestStubExtractor:
    def test_stub_extractor_name(self):
        stub = StubExtractor("swift")
        assert stub.name == "swift"

    def test_stub_extractor_detect_false(self, tmp_path):
        stub = StubExtractor("swift")
        assert stub.detect(str(tmp_path)) is False

    def test_stub_extractor_file_extensions_empty(self):
        stub = StubExtractor("swift")
        assert stub.file_extensions() == []

    def test_stub_extractor_public_symbols_empty(self):
        stub = StubExtractor("swift")
        assert stub.public_symbols("/some/file.swift") == []

    def test_stub_extractor_resolve_path_none(self):
        stub = StubExtractor("swift")
        assert stub.resolve_path("Foo", ["src/"], "/base") is None

    def test_stub_extractor_extract_returns_error(self):
        stub = StubExtractor("swift")
        result = stub.extract("ref", {"path": "Foo"}, [], ["src/"], "/base")
        assert "no extractor for 'swift'" in result
        assert result.startswith("> *[selfdoc:")

    def test_resolve_source_entries_unsupported_uses_stub(self):
        config = {"source": [{"path": "ios/Sources/", "language": "swift"}]}
        entries = resolve_source_entries(config)
        assert len(entries) == 1
        assert isinstance(entries[0].extractor, StubExtractor)
        assert entries[0].extractor.name == "swift"
        assert entries[0].path == "ios/Sources/"


# ---------------------------------------------------------------------------
# Name property
# ---------------------------------------------------------------------------


class TestNameProperty:
    def test_python_name(self):
        assert PythonExtractor().name == "python"

    def test_go_name(self):
        assert GoExtractor().name == "go"

    def test_typescript_name(self):
        assert TypeScriptExtractor().name == "typescript"

    def test_zig_name(self):
        assert ZigExtractor().name == "zig"


# ---------------------------------------------------------------------------
# detect()
# ---------------------------------------------------------------------------


class TestDetect:
    def test_python_detects_pyproject_toml(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        assert PythonExtractor().detect(str(tmp_path)) is True

    def test_python_detects_setup_py(self, tmp_path):
        (tmp_path / "setup.py").touch()
        assert PythonExtractor().detect(str(tmp_path)) is True

    def test_python_not_detected_empty(self, tmp_path):
        assert PythonExtractor().detect(str(tmp_path)) is False

    def test_go_detects_go_mod(self, tmp_path):
        (tmp_path / "go.mod").touch()
        assert GoExtractor().detect(str(tmp_path)) is True

    def test_go_not_detected_empty(self, tmp_path):
        assert GoExtractor().detect(str(tmp_path)) is False

    def test_typescript_detects_tsconfig(self, tmp_path):
        (tmp_path / "tsconfig.json").touch()
        assert TypeScriptExtractor().detect(str(tmp_path)) is True

    def test_typescript_not_detected_empty(self, tmp_path):
        assert TypeScriptExtractor().detect(str(tmp_path)) is False

    def test_zig_detects_build_zig(self, tmp_path):
        (tmp_path / "build.zig").touch()
        assert ZigExtractor().detect(str(tmp_path)) is True

    def test_zig_detects_build_zig_zon(self, tmp_path):
        (tmp_path / "build.zig.zon").touch()
        assert ZigExtractor().detect(str(tmp_path)) is True

    def test_zig_not_detected_empty(self, tmp_path):
        assert ZigExtractor().detect(str(tmp_path)) is False


# ---------------------------------------------------------------------------
# file_extensions()
# ---------------------------------------------------------------------------


class TestFileExtensions:
    def test_python_extensions(self):
        assert PythonExtractor().file_extensions() == [".py"]

    def test_go_extensions(self):
        assert GoExtractor().file_extensions() == [".go"]

    def test_typescript_extensions(self):
        exts = TypeScriptExtractor().file_extensions()
        assert exts == [".ts", ".tsx", ".js", ".jsx"]

    def test_zig_extensions(self):
        assert ZigExtractor().file_extensions() == [".zig"]


# ---------------------------------------------------------------------------
# public_symbols()
# ---------------------------------------------------------------------------


class TestPublicSymbols:
    def test_python_public_symbols(self, tmp_path):
        py_file = tmp_path / "example.py"
        py_file.write_text(
            'def greet(): pass\n'
            'def _private(): pass\n'
            'class Widget: pass\n'
            'class _Internal: pass\n'
            'async def fetch_data(): pass\n',
            encoding="utf-8",
        )
        symbols = PythonExtractor().public_symbols(str(py_file))
        assert symbols == ["greet", "Widget", "fetch_data"]

    def test_python_public_symbols_syntax_error(self, tmp_path):
        py_file = tmp_path / "bad.py"
        py_file.write_text("def broken(\n", encoding="utf-8")
        assert PythonExtractor().public_symbols(str(py_file)) == []

    def test_python_public_symbols_missing_file(self):
        assert PythonExtractor().public_symbols("/nonexistent/file.py") == []

    def test_go_public_symbols(self, tmp_path):
        go_file = tmp_path / "example.go"
        go_file.write_text(
            "package main\n"
            "\n"
            "func Hello() {}\n"
            "func hello() {}\n"
            "type Config struct {}\n"
            "type config struct {}\n"
            "var MaxRetries int\n"
            "const DefaultTimeout = 30\n",
            encoding="utf-8",
        )
        symbols = GoExtractor().public_symbols(str(go_file))
        assert "Hello" in symbols
        assert "Config" in symbols
        assert "MaxRetries" in symbols
        assert "DefaultTimeout" in symbols
        assert "hello" not in symbols
        assert "config" not in symbols

    def test_go_public_symbols_const_block(self, tmp_path):
        go_file = tmp_path / "consts.go"
        go_file.write_text(
            "package exitcodes\n"
            "\n"
            "const (\n"
            "\tExitSuccess = 0\n"
            "\tExitGeneral = 1\n"
            ")\n",
            encoding="utf-8",
        )
        symbols = GoExtractor().public_symbols(str(go_file))
        assert "ExitSuccess" in symbols
        assert "ExitGeneral" in symbols

    def test_go_public_symbols_var_block(self, tmp_path):
        go_file = tmp_path / "vars.go"
        go_file.write_text(
            "package config\n"
            "\n"
            "var (\n"
            "\tDefaultTimeout int = 30\n"
            "\tMaxRetries int = 3\n"
            ")\n",
            encoding="utf-8",
        )
        symbols = GoExtractor().public_symbols(str(go_file))
        assert "DefaultTimeout" in symbols
        assert "MaxRetries" in symbols

    def test_go_public_symbols_mixed(self, tmp_path):
        go_file = tmp_path / "mixed.go"
        go_file.write_text(
            "package main\n"
            "\n"
            "const SingleConst = 42\n"
            "\n"
            "const (\n"
            "\tBlockConst1 = 1\n"
            "\tBlockConst2 = 2\n"
            ")\n"
            "\n"
            "var SingleVar int\n"
            "\n"
            "var (\n"
            "\tBlockVar1 string = \"hello\"\n"
            ")\n"
            "\n"
            "func ExportedFunc() {}\n",
            encoding="utf-8",
        )
        symbols = GoExtractor().public_symbols(str(go_file))
        assert "SingleConst" in symbols
        assert "BlockConst1" in symbols
        assert "BlockConst2" in symbols
        assert "SingleVar" in symbols
        assert "BlockVar1" in symbols
        assert "ExportedFunc" in symbols

    def test_go_public_symbols_block_unexported(self, tmp_path):
        go_file = tmp_path / "unexported.go"
        go_file.write_text(
            "package exitcodes\n"
            "\n"
            "const (\n"
            "\texitSuccess = 0\n"
            "\tExitGeneral = 1\n"
            ")\n",
            encoding="utf-8",
        )
        symbols = GoExtractor().public_symbols(str(go_file))
        assert "ExitGeneral" in symbols
        assert "exitSuccess" not in symbols

    def test_go_public_symbols_nested_comment_in_block(self, tmp_path):
        go_file = tmp_path / "commented.go"
        go_file.write_text(
            "package codes\n"
            "\n"
            "const (\n"
            "\t// ExitSuccess is the success code.\n"
            "\tExitSuccess = 0\n"
            "\t// internal comment\n"
            "\tExitGeneral = 1\n"
            ")\n",
            encoding="utf-8",
        )
        symbols = GoExtractor().public_symbols(str(go_file))
        assert "ExitSuccess" in symbols
        assert "ExitGeneral" in symbols
        assert len(symbols) == 2

    def test_go_public_symbols_iota_with_blank(self, tmp_path):
        go_file = tmp_path / "iota.go"
        go_file.write_text(
            "package main\n"
            "\n"
            "const (\n"
            "\t_ = iota\n"
            "\tExitSuccess\n"
            "\tExitGeneral\n"
            "\t_reserved\n"
            ")\n",
            encoding="utf-8",
        )
        symbols = GoExtractor().public_symbols(str(go_file))
        assert "ExitSuccess" in symbols
        assert "ExitGeneral" in symbols
        assert "_" not in symbols
        assert "_reserved" not in symbols
        assert len(symbols) == 2

    def test_go_public_symbols_missing_file(self):
        assert GoExtractor().public_symbols("/nonexistent/file.go") == []

    def test_typescript_public_symbols(self, tmp_path):
        ts_file = tmp_path / "example.ts"
        ts_file.write_text(
            "export function createWidget(): void {}\n"
            "function internal(): void {}\n"
            "export class Processor {}\n"
            "export const MAX_SIZE = 100;\n"
            "export interface Options {}\n"
            "export type Id = string;\n"
            "export default function main(): void {}\n",
            encoding="utf-8",
        )
        symbols = TypeScriptExtractor().public_symbols(str(ts_file))
        assert "createWidget" in symbols
        assert "Processor" in symbols
        assert "MAX_SIZE" in symbols
        assert "Options" in symbols
        assert "Id" in symbols
        assert "main" in symbols
        assert "internal" not in symbols

    def test_typescript_public_symbols_reexport(self, tmp_path):
        ts_file = tmp_path / "index.ts"
        ts_file.write_text(
            "export { Foo, Bar as Baz } from './module';\n",
            encoding="utf-8",
        )
        symbols = TypeScriptExtractor().public_symbols(str(ts_file))
        assert "Foo" in symbols
        assert "Baz" in symbols
        assert "Bar" not in symbols

    def test_typescript_public_symbols_missing_file(self):
        assert TypeScriptExtractor().public_symbols("/nonexistent/file.ts") == []

    def test_python_public_symbols_with_all(self, tmp_path):
        py_file = tmp_path / "mod.py"
        py_file.write_text(
            '__all__ = ["Foo", "bar"]\n'
            'class Foo: pass\n'
            'def bar(): pass\n'
            'class Baz: pass\n',
            encoding="utf-8",
        )
        symbols = PythonExtractor().public_symbols(str(py_file))
        assert symbols == ["Foo", "bar"]

    def test_python_public_symbols_all_with_private(self, tmp_path):
        py_file = tmp_path / "mod.py"
        py_file.write_text(
            '__all__ = ["_private_helper", "Public"]\n'
            'def _private_helper(): pass\n'
            'class Public: pass\n',
            encoding="utf-8",
        )
        symbols = PythonExtractor().public_symbols(str(py_file))
        assert symbols == ["_private_helper", "Public"]

    def test_python_public_symbols_all_non_literal(self, tmp_path):
        py_file = tmp_path / "mod.py"
        py_file.write_text(
            '__all__ = some_function()\n'
            'def greet(): pass\n'
            'def _hidden(): pass\n'
            'class Widget: pass\n',
            encoding="utf-8",
        )
        symbols = PythonExtractor().public_symbols(str(py_file))
        assert symbols == ["greet", "Widget"]

    def test_python_public_symbols_all_empty(self, tmp_path):
        py_file = tmp_path / "mod.py"
        py_file.write_text(
            '__all__ = []\n'
            'def greet(): pass\n'
            'class Widget: pass\n',
            encoding="utf-8",
        )
        symbols = PythonExtractor().public_symbols(str(py_file))
        assert symbols == []

    def test_python_public_symbols_all_tuple(self, tmp_path):
        py_file = tmp_path / "mod.py"
        py_file.write_text(
            '__all__ = ("Foo", "Bar")\n'
            'class Foo: pass\n'
            'class Bar: pass\n'
            'class Baz: pass\n',
            encoding="utf-8",
        )
        symbols = PythonExtractor().public_symbols(str(py_file))
        assert symbols == ["Foo", "Bar"]

    def test_zig_public_symbols(self, tmp_path):
        zig_file = tmp_path / "example.zig"
        zig_file.write_text(
            "const std = @import(\"std\");\n"
            "\n"
            "pub fn init() void {}\n"
            "pub const MAX_SIZE = 100;\n"
            "pub var counter: u32 = 0;\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert "init" in symbols
        assert "MAX_SIZE" in symbols
        assert "counter" in symbols
        assert "std" not in symbols

    def test_zig_public_symbols_extern_fn(self, tmp_path):
        zig_file = tmp_path / "ffi.zig"
        zig_file.write_text(
            "pub extern fn SDL_Init(flags: u32) c_int;\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert symbols == ["SDL_Init"]

    def test_zig_public_symbols_export_fn(self, tmp_path):
        zig_file = tmp_path / "exports.zig"
        zig_file.write_text(
            "pub export fn gameInit() void {}\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert symbols == ["gameInit"]

    def test_zig_public_symbols_inline_fn(self, tmp_path):
        zig_file = tmp_path / "inline.zig"
        zig_file.write_text(
            "pub inline fn fastAdd(a: u32, b: u32) u32 {\n"
            "    return a + b;\n"
            "}\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert symbols == ["fastAdd"]

    def test_zig_public_symbols_struct(self, tmp_path):
        zig_file = tmp_path / "types.zig"
        zig_file.write_text(
            "pub const Config = struct {\n"
            "    timeout: u32 = 30,\n"
            "    retries: u8 = 3,\n"
            "};\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert symbols == ["Config"]

    def test_zig_public_symbols_enum(self, tmp_path):
        zig_file = tmp_path / "enums.zig"
        zig_file.write_text(
            "pub const Color = enum {\n"
            "    red,\n"
            "    green,\n"
            "    blue,\n"
            "};\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert symbols == ["Color"]

    def test_zig_public_symbols_union(self, tmp_path):
        zig_file = tmp_path / "unions.zig"
        zig_file.write_text(
            "pub const Token = union(enum) {\n"
            "    number: f64,\n"
            "    string: []const u8,\n"
            "    eof,\n"
            "};\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert symbols == ["Token"]

    def test_zig_public_symbols_private_excluded(self, tmp_path):
        zig_file = tmp_path / "mixed.zig"
        zig_file.write_text(
            "const private_const = 42;\n"
            "var private_var: u32 = 0;\n"
            "fn privateFunc() void {}\n"
            "pub fn publicFunc() void {}\n"
            "pub const PUBLIC_CONST = 100;\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert "publicFunc" in symbols
        assert "PUBLIC_CONST" in symbols
        assert "private_const" not in symbols
        assert "private_var" not in symbols
        assert "privateFunc" not in symbols
        assert len(symbols) == 2

    def test_zig_public_symbols_test_block_excluded(self, tmp_path):
        zig_file = tmp_path / "tested.zig"
        zig_file.write_text(
            "pub fn add(a: u32, b: u32) u32 {\n"
            "    return a + b;\n"
            "}\n"
            "\n"
            'test "add works" {\n'
            "    try std.testing.expectEqual(@as(u32, 3), add(1, 2));\n"
            "}\n",
            encoding="utf-8",
        )
        symbols = ZigExtractor().public_symbols(str(zig_file))
        assert symbols == ["add"]

    def test_zig_public_symbols_missing_file(self):
        assert ZigExtractor().public_symbols("/nonexistent/file.zig") == []


# ---------------------------------------------------------------------------
# resolve_path()
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_python_resolve_path(self, tmp_path):
        src_dir = tmp_path / "mylib"
        src_dir.mkdir()
        (src_dir / "core.py").touch()
        result = PythonExtractor().resolve_path(
            "core", ["mylib/"], str(tmp_path)
        )
        assert result is not None
        assert result.endswith("core.py")

    def test_python_resolve_path_not_found(self, tmp_path):
        result = PythonExtractor().resolve_path(
            "nonexistent", ["src/"], str(tmp_path)
        )
        assert result is None

    def test_go_resolve_path(self, tmp_path):
        pkg_dir = tmp_path / "internal" / "commit"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "commit.go").write_text("package commit\n", encoding="utf-8")
        result = GoExtractor().resolve_path(
            "internal/commit", [], str(tmp_path)
        )
        assert result is not None
        assert result.endswith("commit")

    def test_typescript_resolve_path(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "core.ts").touch()
        result = TypeScriptExtractor().resolve_path(
            "core.ts", ["src/"], str(tmp_path)
        )
        assert result is not None
        assert result.endswith("core.ts")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_extractors_has_all_keys(self):
        assert set(EXTRACTORS.keys()) == {"python", "go", "typescript", "javascript", "zig"}

    def test_javascript_is_typescript_alias(self):
        # Both should be TypeScriptExtractor instances
        assert isinstance(EXTRACTORS["javascript"], TypeScriptExtractor)
        assert isinstance(EXTRACTORS["typescript"], TypeScriptExtractor)

    def test_all_extractors_are_language_extractors(self):
        for name, ext in EXTRACTORS.items():
            assert isinstance(ext, LanguageExtractor), f"{name} is not a LanguageExtractor"


# ---------------------------------------------------------------------------
# detect_language()
# ---------------------------------------------------------------------------


class TestDetectLanguage:
    def test_detects_python(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        assert detect_language(str(tmp_path)) == "python"

    def test_detects_go(self, tmp_path):
        (tmp_path / "go.mod").touch()
        assert detect_language(str(tmp_path)) == "go"

    def test_detects_typescript(self, tmp_path):
        (tmp_path / "tsconfig.json").touch()
        assert detect_language(str(tmp_path)) == "typescript"

    def test_returns_none_for_empty(self, tmp_path):
        assert detect_language(str(tmp_path)) is None

    def test_python_takes_priority_over_go(self, tmp_path):
        """If both pyproject.toml and go.mod exist, Python wins."""
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "go.mod").touch()
        assert detect_language(str(tmp_path)) == "python"

    def test_go_takes_priority_over_typescript(self, tmp_path):
        """If both go.mod and tsconfig.json exist, Go wins."""
        (tmp_path / "go.mod").touch()
        (tmp_path / "tsconfig.json").touch()
        assert detect_language(str(tmp_path)) == "go"


# ---------------------------------------------------------------------------
# SourceEntry & helpers
# ---------------------------------------------------------------------------


class TestSourceEntries:
    def test_resolve_source_entries_single(self):
        config = {"source": [{"path": "mylib/", "language": "python"}]}
        entries = resolve_source_entries(config)
        assert len(entries) == 1
        assert entries[0].path == "mylib/"
        assert entries[0].language == "python"
        assert isinstance(entries[0].extractor, PythonExtractor)

    def test_resolve_source_entries_multi(self):
        config = {"source": [
            {"path": "src/", "language": "python"},
            {"path": "lib/", "language": "python"},
        ]}
        entries = resolve_source_entries(config)
        assert len(entries) == 2
        assert entries[0].path == "src/"
        assert entries[1].path == "lib/"
        assert all(e.language == "python" for e in entries)

    def test_resolve_source_entries_go(self):
        config = {"source": [{"path": ".", "language": "go"}]}
        entries = resolve_source_entries(config)
        assert len(entries) == 1
        assert entries[0].language == "go"
        assert isinstance(entries[0].extractor, GoExtractor)

    def test_resolve_source_entries_unsupported_language(self):
        config = {"source": [{"path": "lib/", "language": "ruby"}]}
        entries = resolve_source_entries(config)
        assert len(entries) == 1
        assert entries[0].language == "ruby"
        assert isinstance(entries[0].extractor, StubExtractor)

    def test_source_paths_extracts_paths(self):
        config = {"source": [
            {"path": "selfdoc/", "language": "python"},
            {"path": "tests/", "language": "python"},
        ]}
        result = source_paths(config)
        assert result == ["selfdoc/", "tests/"]

    def test_source_entry_frozen(self):
        entry = SourceEntry(
            path="src/", language="python", extractor=EXTRACTORS["python"]
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry.path = "other/"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# detect_languages()
# ---------------------------------------------------------------------------


class TestDetectLanguages:
    def test_detects_single_python(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        result = detect_languages(str(tmp_path))
        assert len(result) == 1
        assert result[0]["language"] == "python"

    def test_detects_multiple(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "go.mod").touch()
        result = detect_languages(str(tmp_path))
        assert len(result) == 2
        languages = [r["language"] for r in result]
        assert "python" in languages
        assert "go" in languages

    def test_detects_all_three(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "go.mod").touch()
        (tmp_path / "tsconfig.json").touch()
        result = detect_languages(str(tmp_path))
        assert len(result) == 3
        languages = [r["language"] for r in result]
        assert languages == ["python", "go", "typescript"]

    def test_empty_dir_returns_empty(self, tmp_path):
        result = detect_languages(str(tmp_path))
        assert result == []
