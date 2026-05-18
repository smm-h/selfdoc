"""Tests for the Python source extractor (selfdoc.extractors.python)."""

import json
import os

import pytest

from selfdoc.extractors.python import PythonExtractor


@pytest.fixture()
def sample_project(tmp_path):
    """Create a sample Python project structure for testing."""
    # Create source directory
    src_dir = os.path.join(tmp_path, "mylib")
    os.makedirs(src_dir)

    # Module with docstring, functions, and class
    module_py = os.path.join(src_dir, "core.py")
    with open(module_py, "w", encoding="utf-8") as f:
        f.write('''\
"""Core module for mylib.

Provides essential utilities.
"""


def greet(name: str, loud: bool = False) -> str:
    """Say hello to someone.

    Args:
        name: The person to greet.
        loud: Whether to shout.
    """
    msg = f"Hello, {name}!"
    return msg.upper() if loud else msg


def _private_helper():
    # No docstring -- should be skipped
    pass


def _documented_private(x: int) -> int:
    """A private function that has a docstring -- should be included."""
    return x * 2


class Processor:
    """Processes items in a pipeline."""

    def run(self, items: list) -> list:
        """Run the pipeline on items."""
        return [self._transform(i) for i in items]

    def _transform(self, item):
        # No docstring -- skipped
        return item

    def _special_transform(self, item):
        """Internal but documented transform."""
        return item
''')

    # __init__.py so it's a package
    init_py = os.path.join(src_dir, "__init__.py")
    with open(init_py, "w", encoding="utf-8") as f:
        f.write('"""mylib package."""\n')

    return tmp_path


@pytest.fixture()
def source_paths():
    return ["mylib/"]


# ---------------------------------------------------------------------------
# :::module tests
# ---------------------------------------------------------------------------


class TestModuleDirective:
    def test_extracts_module_docstring(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "ref", {"path": "core"}, [], source_paths, str(sample_project)
        )
        assert "## core" in result
        assert "Core module for mylib." in result
        assert "Provides essential utilities." in result

    def test_extracts_public_function(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "ref", {"path": "core"}, [], source_paths, str(sample_project)
        )
        assert "### greet" in result
        assert "def greet(name: str, loud: bool=False) -> str" in result
        assert "Say hello to someone." in result

    def test_extracts_class(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "ref", {"path": "core"}, [], source_paths, str(sample_project)
        )
        assert "### Processor" in result
        assert "Processes items in a pipeline." in result
        assert "#### run" in result
        assert "Run the pipeline on items." in result

    def test_skips_private_without_docstring(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "ref", {"path": "core"}, [], source_paths, str(sample_project)
        )
        assert "_private_helper" not in result

    def test_includes_private_with_docstring(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "ref", {"path": "core"}, [], source_paths, str(sample_project)
        )
        assert "_documented_private" in result
        assert "A private function that has a docstring" in result

    def test_skips_private_method_without_docstring(
        self, sample_project, source_paths
    ):
        result = PythonExtractor().extract(
            "ref", {"path": "core"}, [], source_paths, str(sample_project)
        )
        # _transform has no docstring -- should not appear
        assert "_transform" not in result or "_special_transform" in result
        # More precise: check that we don't have just "_transform" as a heading
        lines = result.split("\n")
        headings = [l for l in lines if l.startswith("####")]
        heading_names = [h.strip("# ") for h in headings]
        assert "_transform" not in heading_names

    def test_includes_private_method_with_docstring(
        self, sample_project, source_paths
    ):
        result = PythonExtractor().extract(
            "ref", {"path": "core"}, [], source_paths, str(sample_project)
        )
        assert "_special_transform" in result
        assert "Internal but documented transform." in result

    def test_missing_module_error(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "ref", {"path": "nonexistent.module"}, [], source_paths, str(sample_project)
        )
        assert "not found" in result
        assert "nonexistent.module" in result

    def test_dotted_path_resolution(self, sample_project, source_paths):
        """mylib.core should resolve to mylib/core.py."""
        result = PythonExtractor().extract(
            "ref", {"path": "mylib.core"}, [], source_paths, str(sample_project)
        )
        # When source_paths is ["mylib/"], "mylib.core" would look for
        # mylib/mylib/core.py which won't exist. But direct resolution
        # against base_dir should find it.
        assert "## mylib.core" in result
        assert "Core module for mylib." in result

    def test_empty_arg_error(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "ref", {}, [], source_paths, str(sample_project)
        )
        assert "requires" in result


# ---------------------------------------------------------------------------
# :::test tests
# ---------------------------------------------------------------------------


class TestTestDirective:
    @pytest.fixture()
    def test_file(self, sample_project):
        """Create a test file for extraction."""
        tests_dir = os.path.join(sample_project, "tests")
        os.makedirs(tests_dir)
        test_py = os.path.join(tests_dir, "test_core.py")
        with open(test_py, "w", encoding="utf-8") as f:
            f.write('''\
"""Tests for mylib.core."""

import pytest


def test_greet_basic():
    """Test basic greeting."""
    from mylib.core import greet
    assert greet("World") == "Hello, World!"


def test_greet_loud():
    """Test loud greeting."""
    from mylib.core import greet
    assert greet("World", loud=True) == "HELLO, WORLD!"


class TestProcessor:
    """Tests for the Processor class."""

    def test_run_empty(self):
        from mylib.core import Processor
        p = Processor()
        assert p.run([]) == []
''')
        return sample_project

    def test_extract_specific_function(self, test_file, source_paths):
        result = PythonExtractor().extract(
            "code-test",
            {"path": "tests/test_core.py", "target": "test_greet_basic"},
            [],
            source_paths,
            str(test_file),
        )
        assert "```python" in result
        assert "def test_greet_basic():" in result
        assert 'greet("World")' in result

    def test_extract_specific_class(self, test_file, source_paths):
        result = PythonExtractor().extract(
            "code-test",
            {"path": "tests/test_core.py", "target": "TestProcessor"},
            [],
            source_paths,
            str(test_file),
        )
        assert "```python" in result
        assert "class TestProcessor:" in result
        assert "test_run_empty" in result

    def test_whole_file(self, test_file, source_paths):
        result = PythonExtractor().extract(
            "code-test", {"path": "tests/test_core.py"}, [], source_paths, str(test_file)
        )
        assert "```python" in result
        assert "test_greet_basic" in result
        assert "test_greet_loud" in result
        assert "TestProcessor" in result

    def test_missing_file_error(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "code-test",
            {"path": "tests/nonexistent.py"},
            [],
            source_paths,
            str(sample_project),
        )
        assert "not found" in result

    def test_target_not_found_error(self, test_file, source_paths):
        result = PythonExtractor().extract(
            "code-test",
            {"path": "tests/test_core.py", "target": "nonexistent_test"},
            [],
            source_paths,
            str(test_file),
        )
        assert "not found" in result
        assert "nonexistent_test" in result


# ---------------------------------------------------------------------------
# :::schema tests
# ---------------------------------------------------------------------------


class TestSchemaDirective:
    def test_json_schema_table(self, sample_project, source_paths):
        """JSON file should produce a markdown table."""
        schema_path = os.path.join(sample_project, "schema.json")
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(
                {"name": "mylib", "version": "1.0.0", "debug": True, "port": 8080},
                f,
            )

        result = PythonExtractor().extract(
            "table-schema", {"path": "schema.json"}, [], source_paths, str(sample_project)
        )
        assert "| Key | Type | Value |" in result
        assert "| --- | --- | --- |" in result
        assert "`name`" in result
        assert "string" in result
        assert "`version`" in result
        assert "`debug`" in result
        assert "boolean" in result
        assert "`port`" in result
        assert "integer" in result

    def test_dataclass_fields(self, sample_project, source_paths):
        """Python dataclass should produce a field table."""
        models_py = os.path.join(sample_project, "mylib", "models.py")
        with open(models_py, "w", encoding="utf-8") as f:
            f.write('''\
"""Data models."""

from dataclasses import dataclass


@dataclass
class Config:
    """Application configuration."""

    host: str = "localhost"  # Server hostname
    port: int = 8080  # Server port
    debug: bool = False  # Enable debug mode
''')

        result = PythonExtractor().extract(
            "table-schema",
            {"path": "models", "target": "Config"},
            [],
            source_paths,
            str(sample_project),
        )
        assert "| Field | Type | Default | Description |" in result
        assert "`host`" in result
        assert "`str`" in result
        assert "`'localhost'`" in result
        assert "Server hostname" in result
        assert "`port`" in result
        assert "`int`" in result

    def test_missing_json_error(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "table-schema", {"path": "missing.json"}, [], source_paths, str(sample_project)
        )
        assert "not found" in result

    def test_missing_class_error(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "table-schema",
            {"path": "core", "target": "NoSuchClass"},
            [],
            source_paths,
            str(sample_project),
        )
        assert "not found" in result


# ---------------------------------------------------------------------------
# :::cli tests
# ---------------------------------------------------------------------------


class TestCliDirective:
    def test_extracts_help_constant(self, sample_project, source_paths):
        """Module with a HELP constant should produce formatted output."""
        cli_py = os.path.join(sample_project, "mylib", "cli.py")
        with open(cli_py, "w", encoding="utf-8") as f:
            f.write('''\
"""Command-line interface for mylib."""

HELP = """
Usage: mylib [options] <command>

Commands:
    run     Run the processor
    check   Check configuration
"""
''')

        result = PythonExtractor().extract(
            "code-help", {"path": "cli"}, [], source_paths, str(sample_project)
        )
        assert "Command-line interface for mylib." in result
        assert "```" in result
        assert "Usage: mylib [options] <command>" in result

    def test_missing_module_error(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "code-help", {"path": "nonexistent"}, [], source_paths, str(sample_project)
        )
        assert "not found" in result


# ---------------------------------------------------------------------------
# :::config tests
# ---------------------------------------------------------------------------


class TestConfigDirective:
    def test_json_config_table(self, sample_project, source_paths):
        """JSON config should be rendered as a key-value table."""
        config_path = os.path.join(sample_project, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"host": "localhost", "port": 3000, "ssl": False}, f)

        result = PythonExtractor().extract(
            "table-config", {"path": "config.json"}, [], source_paths, str(sample_project)
        )
        assert "| Key | Type | Value |" in result
        assert "`host`" in result
        assert "string" in result
        assert "`port`" in result
        assert "integer" in result
        assert "`ssl`" in result
        assert "boolean" in result

    def test_toml_config_table(self, sample_project, source_paths):
        """TOML config should be rendered as a key-value table."""
        config_path = os.path.join(sample_project, "config.toml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write('[server]\nhost = "localhost"\nport = 3000\n')

        result = PythonExtractor().extract(
            "table-config", {"path": "config.toml"}, [], source_paths, str(sample_project)
        )
        assert "| Key | Type | Value |" in result
        assert "`server.host`" in result or "`host`" in result
        assert "string" in result

    def test_missing_file_error(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "table-config", {"path": "missing.json"}, [], source_paths, str(sample_project)
        )
        assert "not found" in result

    def test_unsupported_format_as_codeblock(self, sample_project, source_paths):
        """Unsupported file formats should be shown as a code block."""
        ini_path = os.path.join(sample_project, "app.ini")
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write("[section]\nkey = value\n")

        result = PythonExtractor().extract(
            "table-config", {"path": "app.ini"}, [], source_paths, str(sample_project)
        )
        assert "```" in result
        assert "[section]" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unknown_directive(self, sample_project, source_paths):
        """Unknown directive name should produce an error message."""
        result = PythonExtractor().extract(
            "unknown", {"path": "arg"}, [], source_paths, str(sample_project)
        )
        assert "unknown directive" in result

    def test_syntax_error_in_module(self, sample_project, source_paths):
        """Syntax error in source should produce error, not crash."""
        bad_py = os.path.join(sample_project, "mylib", "bad.py")
        with open(bad_py, "w", encoding="utf-8") as f:
            f.write("def broken(\n")  # Syntax error

        result = PythonExtractor().extract(
            "ref", {"path": "bad"}, [], source_paths, str(sample_project)
        )
        assert "syntax error" in result
