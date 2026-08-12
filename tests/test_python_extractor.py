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
        assert "## `core`" in result
        assert "Core module for mylib." in result
        assert "Provides essential utilities." in result

    def test_extracts_public_function(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "ref", {"path": "core"}, [], source_paths, str(sample_project)
        )
        assert "### `greet`" in result
        assert "def greet(name: str, loud: bool=False) -> str" in result
        assert "Say hello to someone." in result

    def test_extracts_class(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "ref", {"path": "core"}, [], source_paths, str(sample_project)
        )
        assert "### `Processor`" in result
        assert "Processes items in a pipeline." in result
        assert "#### `run`" in result
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
        assert "## `mylib.core`" in result
        assert "Core module for mylib." in result

    def test_empty_arg_error(self, sample_project, source_paths):
        result = PythonExtractor().extract(
            "ref", {}, [], source_paths, str(sample_project)
        )
        assert "requires" in result

    def test_dataclass_field_table_via_ref(self, sample_project, source_paths):
        """Dataclass without docstring renders a 3-column field table."""
        dc_py = os.path.join(sample_project, "mylib", "settings.py")
        with open(dc_py, "w", encoding="utf-8") as f:
            f.write('''\
"""Settings module."""

from dataclasses import dataclass


@dataclass
class Settings:
    host: str = "localhost"
    port: int = 8080
    debug: bool = False
    _internal: str = "hidden"
''')

        result = PythonExtractor().extract(
            "ref", {"path": "settings"}, [], source_paths, str(sample_project)
        )
        assert "### `Settings`" in result
        assert "| Field | Type | Default |" in result
        assert "| --- | --- | --- |" in result
        assert "| `host` | `str` | `'localhost'` |" in result
        assert "| `port` | `int` | `8080` |" in result
        assert "| `debug` | `bool` | `False` |" in result
        assert "_internal" not in result

    def test_ref_with_target(self, tmp_path):
        """ref directive with target renders only the specified symbol."""
        src = tmp_path / "mymod.py"
        src.write_text(
            '"""Module docstring."""\n\n'
            'def foo():\n'
            '    """Foo doc."""\n'
            '    pass\n\n'
            'def bar():\n'
            '    """Bar doc."""\n'
            '    pass\n',
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref",
            {"path": "mymod.py", "target": "bar"},
            [],
            [],
            str(tmp_path),
        )
        assert "### `bar`" in result
        assert "Bar doc" in result
        assert "foo" not in result
        assert "Module docstring" not in result

    def test_ref_with_target_not_found(self, tmp_path):
        """ref directive with nonexistent target returns error."""
        src = tmp_path / "mymod.py"
        src.write_text(
            'def foo():\n'
            '    """Foo doc."""\n'
            '    pass\n',
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref",
            {"path": "mymod.py", "target": "nonexistent"},
            [],
            [],
            str(tmp_path),
        )
        assert "not found" in result


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

    def test_json_schema_exclude(self, sample_project, source_paths):
        """Exclude attribute should remove specified keys from JSON schema table."""
        schema_path = os.path.join(sample_project, "test.json")
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump({"name": "mylib", "version": "1.0.0", "count": 42}, f)

        result = PythonExtractor().extract(
            "table-schema",
            {"path": "test.json", "exclude": "version"},
            [],
            source_paths,
            str(sample_project),
        )
        assert "`version`" not in result
        assert "`name`" in result
        assert "`count`" in result

    def test_json_schema_exclude_whitespace(self, sample_project, source_paths):
        """Exclude with multiple comma-separated keys and whitespace."""
        schema_path = os.path.join(sample_project, "test.json")
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump({"name": "mylib", "version": "1.0.0", "count": 42}, f)

        result = PythonExtractor().extract(
            "table-schema",
            {"path": "test.json", "exclude": "version, count"},
            [],
            source_paths,
            str(sample_project),
        )
        assert "`version`" not in result
        assert "`count`" not in result
        assert "`name`" in result

    def test_json_schema_exclude_missing_key(self, sample_project, source_paths):
        """Excluding a nonexistent key should produce an error."""
        schema_path = os.path.join(sample_project, "test.json")
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump({"name": "mylib", "version": "1.0.0", "count": 42}, f)

        result = PythonExtractor().extract(
            "table-schema",
            {"path": "test.json", "exclude": "nonexistent"},
            [],
            source_paths,
            str(sample_project),
        )
        assert "selfdoc:" in result


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

    def test_config_exclude_json(self, sample_project, source_paths):
        """Exclude attribute should remove specified keys from JSON config table."""
        config_path = os.path.join(sample_project, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"host": "localhost", "port": 3000, "ssl": False}, f)

        result = PythonExtractor().extract(
            "table-config",
            {"path": "config.json", "exclude": "ssl"},
            [],
            source_paths,
            str(sample_project),
        )
        assert "`ssl`" not in result
        assert "`host`" in result
        assert "`port`" in result

    def test_config_exclude_toml(self, sample_project, source_paths):
        """Exclude attribute should remove specified top-level sections from TOML config."""
        config_path = os.path.join(sample_project, "config.toml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(
                '[server]\nhost = "localhost"\nport = 3000\n'
                '[logging]\nlevel = "debug"\n'
            )

        result = PythonExtractor().extract(
            "table-config",
            {"path": "config.toml", "exclude": "logging"},
            [],
            source_paths,
            str(sample_project),
        )
        assert "`logging.level`" not in result
        assert "`server.host`" in result or "`host`" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# symbol_details tests
# ---------------------------------------------------------------------------


class TestSymbolDetails:
    def test_all_params_documented(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
def greet(name: str, loud: bool = False) -> str:
    """Say hello.

    Args:
        name: The name.
        loud: Whether to shout.

    Returns:
        The greeting string.
    """
    pass
''')
        result = PythonExtractor().symbol_details(str(py), "greet")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0] == {"name": "name", "type": "str", "documented": True}
        assert result["params"][1] == {"name": "loud", "type": "bool", "documented": True}
        assert result["return_type"] == "str"
        assert result["return_documented"] is True

    def test_some_params_undocumented(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
def process(x: int, y: int, z: int) -> int:
    """Process values.

    Args:
        x: The first value.
    """
    return x + y + z
''')
        result = PythonExtractor().symbol_details(str(py), "process")
        assert result is not None
        assert result["params"][0]["documented"] is True
        assert result["params"][1]["documented"] is False
        assert result["params"][2]["documented"] is False

    def test_return_type_with_returns_section(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
def compute(a: int) -> float:
    """Compute something.

    Args:
        a: Input.

    Returns:
        The result as float.
    """
    return float(a)
''')
        result = PythonExtractor().symbol_details(str(py), "compute")
        assert result["return_type"] == "float"
        assert result["return_documented"] is True

    def test_return_type_no_returns_section(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
def compute(a: int) -> float:
    """Compute something."""
    return float(a)
''')
        result = PythonExtractor().symbol_details(str(py), "compute")
        assert result["return_type"] == "float"
        assert result["return_documented"] is False

    def test_no_return_type_annotation(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
def do_stuff(x):
    """Do stuff."""
    pass
''')
        result = PythonExtractor().symbol_details(str(py), "do_stuff")
        assert result["return_type"] is None

    def test_self_and_cls_skipped(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
class MyClass:
    def method(self, x: int) -> None:
        """A method.

        Args:
            x: The value.
        """
        pass

    @classmethod
    def from_value(cls, v: str) -> "MyClass":
        """Create from value.

        Args:
            v: The value.
        """
        pass
''')
        # Test instance method
        result = PythonExtractor().symbol_details(str(py), "method")
        assert result is not None
        param_names = [p["name"] for p in result["params"]]
        assert "self" not in param_names
        assert "x" in param_names
        assert len(result["params"]) == 1

        # Test classmethod
        result = PythonExtractor().symbol_details(str(py), "from_value")
        param_names = [p["name"] for p in result["params"]]
        assert "cls" not in param_names
        assert "v" in param_names

    def test_class_symbol_returns_init_details(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
class Widget:
    """A widget."""

    def __init__(self, name: str, size: int = 10):
        """Create a widget.

        Args:
            name: The widget name.
            size: The widget size.
        """
        self.name = name
        self.size = size
''')
        result = PythonExtractor().symbol_details(str(py), "Widget")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0] == {"name": "name", "type": "str", "documented": True}
        assert result["params"][1] == {"name": "size", "type": "int", "documented": True}

    def test_class_without_init(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
class Empty:
    """An empty class."""
    pass
''')
        result = PythonExtractor().symbol_details(str(py), "Empty")
        assert result is not None
        assert result["params"] == []
        assert result["return_type"] is None
        assert result["return_documented"] is True

    def test_symbol_not_found(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
def existing():
    pass
''')
        result = PythonExtractor().symbol_details(str(py), "nonexistent")
        assert result is None

    def test_file_with_syntax_error(self, tmp_path):
        py = tmp_path / "bad.py"
        py.write_text("def broken(\n")
        result = PythonExtractor().symbol_details(str(py), "broken")
        assert result is None

    def test_symbol_details_dotted_class_method(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
class MyClass:
    """A sample class."""

    def my_method(self, x: int, y: str = "hi") -> bool:
        """Do something.

        Args:
            x: First arg.
            y: Second arg.

        Returns:
            True if ok.
        """
        return True
''')
        result = PythonExtractor().symbol_details(str(py), "MyClass.my_method")
        assert result is not None
        assert len(result["params"]) == 2
        assert result["params"][0] == {"name": "x", "type": "int", "documented": True}
        assert result["params"][1] == {"name": "y", "type": "str", "documented": True}
        assert result["return_type"] == "bool"
        assert result["return_documented"] is True

    def test_symbol_details_dotted_class_not_found(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
class Other:
    def method(self):
        pass
''')
        result = PythonExtractor().symbol_details(str(py), "Missing.method")
        assert result is None

    def test_symbol_details_dotted_member_not_found(self, tmp_path):
        py = tmp_path / "mod.py"
        py.write_text('''\
class MyClass:
    def existing(self):
        pass
''')
        result = PythonExtractor().symbol_details(str(py), "MyClass.nonexistent")
        assert result is None


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


# ---------------------------------------------------------------------------
# Re-export handling in ref output (Bug 1)
# ---------------------------------------------------------------------------


class TestReexportInRefOutput:
    def test_reexport_appears_in_ref_output(self, tmp_path):
        """A plain `from ._impl import X` re-export in __all__ gets a heading."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "_impl.py").write_text(
            '"""Impl module."""\n\n\nclass Foo:\n    """The real Foo."""\n    pass\n',
            encoding="utf-8",
        )
        (pkg / "__init__.py").write_text(
            '"""Package pkg."""\n\n'
            "from ._impl import Foo\n\n"
            '__all__ = ["Foo"]\n',
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "pkg"}, [], [], str(tmp_path)
        )
        assert "### `Foo`" in result
        assert "from ._impl import Foo" in result

    def test_reexport_with_alias(self, tmp_path):
        """`from ._impl import Foo as Bar` produces a ### Bar heading."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "_impl.py").write_text('class Foo:\n    pass\n', encoding="utf-8")
        (pkg / "__init__.py").write_text(
            "from ._impl import Foo as Bar\n\n"
            '__all__ = ["Bar"]\n',
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "pkg"}, [], [], str(tmp_path)
        )
        assert "### `Bar`" in result
        assert "Foo as Bar" in result

    def test_reexport_nested_in_try_block(self, tmp_path):
        """A re-export inside a top-level try/except is still emitted."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "_impl.py").write_text('class Fast:\n    pass\n', encoding="utf-8")
        (pkg / "__init__.py").write_text(
            "try:\n"
            "    from ._impl import Fast\n"
            "except ImportError:\n"
            "    from ._fallback import Fast\n\n"
            '__all__ = ["Fast"]\n',
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "pkg"}, [], [], str(tmp_path)
        )
        assert "### `Fast`" in result

    def test_reexport_nested_in_type_checking_block(self, tmp_path):
        """A re-export inside `if TYPE_CHECKING:` is still emitted."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "_types.py").write_text('class Spec:\n    pass\n', encoding="utf-8")
        (pkg / "__init__.py").write_text(
            "from typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n"
            "    from ._types import Spec\n\n"
            '__all__ = ["Spec"]\n',
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "pkg"}, [], [], str(tmp_path)
        )
        assert "### `Spec`" in result

    def test_version_constant_appears_in_ref_output(self, tmp_path):
        """A module-level `__version__ = "..."` constant listed in __all__ appears."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text(
            '__version__ = "1.2.3"\n\n'
            '__all__ = ["__version__"]\n',
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "pkg"}, [], [], str(tmp_path)
        )
        assert "### `__version__`" in result
        assert "__version__ = " in result
        assert "1.2.3" in result

    def test_incidental_import_not_in_all_is_not_emitted(self, tmp_path):
        """An import not listed in __all__ must not pollute ref output."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "_impl.py").write_text('class Foo:\n    pass\n', encoding="utf-8")
        (pkg / "__init__.py").write_text(
            "import os\n"
            "from ._impl import Foo\n\n"
            '__all__ = ["Foo"]\n',
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "pkg"}, [], [], str(tmp_path)
        )
        assert "### `os`" not in result
        assert "import os" not in result

    def test_target_resolves_reexport(self, tmp_path):
        """ref with target=X resolves X even when it's only a re-export."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "_impl.py").write_text('class Foo:\n    pass\n', encoding="utf-8")
        (pkg / "__init__.py").write_text(
            "from ._impl import Foo\n\n"
            '__all__ = ["Foo"]\n',
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "pkg", "target": "Foo"}, [], [], str(tmp_path)
        )
        assert "### `Foo`" in result
        assert "from ._impl import Foo" in result
        assert "not found" not in result


# ---------------------------------------------------------------------------
# Docstring-less pydantic models / public classes (Bug 2)
# ---------------------------------------------------------------------------


class TestDocstringlessPublicClasses:
    def test_pydantic_model_without_docstring_gets_field_table(self, tmp_path):
        """A docstring-less pydantic BaseModel subclass renders a field table."""
        mod = tmp_path / "models.py"
        mod.write_text(
            "from pydantic import BaseModel\n\n\n"
            "class Params(BaseModel):\n"
            "    name: str\n"
            "    count: int = 0\n",
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "models.py"}, [], [], str(tmp_path)
        )
        assert "### `Params`" in result
        assert "| Field | Type | Default |" in result
        assert "`name`" in result
        assert "`count`" in result

    def test_empty_class_still_gets_heading(self, tmp_path):
        """A docstring-less, method-less, non-dataclass class still gets a heading."""
        mod = tmp_path / "plain.py"
        mod.write_text(
            "class Plain:\n"
            "    pass\n",
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "plain.py"}, [], [], str(tmp_path)
        )
        assert "### `Plain`" in result
        assert "class Plain" in result

    def test_existing_dataclass_rendering_unchanged(self, tmp_path):
        """Dataclass field-table rendering is unaffected by the pydantic fix."""
        mod = tmp_path / "dc.py"
        mod.write_text(
            "from dataclasses import dataclass\n\n\n"
            "@dataclass\n"
            "class Point:\n"
            "    x: int = 0\n"
            "    y: int = 0\n",
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "dc.py"}, [], [], str(tmp_path)
        )
        assert "### `Point`" in result
        assert "| Field | Type | Default |" in result
        assert "`x`" in result
        assert "`y`" in result

    def test_docstring_class_rendering_unchanged(self, tmp_path):
        """Docstring + methods classes are unaffected by the fallback signature."""
        mod = tmp_path / "doc.py"
        mod.write_text(
            "class Documented:\n"
            '    """A documented class."""\n\n'
            "    def run(self):\n"
            '        """Run it."""\n'
            "        pass\n",
            encoding="utf-8",
        )
        result = PythonExtractor().extract(
            "ref", {"path": "doc.py"}, [], [], str(tmp_path)
        )
        assert "### `Documented`" in result
        assert "A documented class." in result
        assert "#### `run`" in result
        # No spurious raw class-signature fallback block should be added
        # when a docstring is already present.
        assert result.count("### `Documented`") == 1
