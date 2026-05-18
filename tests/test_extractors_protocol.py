"""Tests for the LanguageExtractor protocol, registry, and detection."""

from selfdoc.extractors import EXTRACTORS, detect_language
from selfdoc.extractors.go import GoExtractor
from selfdoc.extractors.protocol import LanguageExtractor
from selfdoc.extractors.python import PythonExtractor
from selfdoc.extractors.typescript import TypeScriptExtractor


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
        assert set(EXTRACTORS.keys()) == {"python", "go", "typescript", "javascript"}

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
