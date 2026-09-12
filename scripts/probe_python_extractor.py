#!/usr/bin/env python3
"""Print the Python extractor's output for the fixtures the Go port pins.

The Go port of ``selfdoc_core.extractors.python`` asserts against exact
strings.  Rather than hand-transcribing them, this prints what the Python
implementation actually produces for each fixture, so a test expectation is
always a recorded observation.

Run from the repository root:

    UV_NO_SYNC=1 uv run python scripts/probe_python_extractor.py
"""

import os
import sys
import tempfile

from selfdoc_core.extractors.python import PythonExtractor

CORE_PY = '''\
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
'''

SETTINGS_PY = '''\
"""Settings module."""

from dataclasses import dataclass


@dataclass
class Settings:
    host: str = "localhost"
    port: int = 8080
    debug: bool = False
    _internal: str = "hidden"
'''

MODELS_PY = '''\
"""Data models."""

from dataclasses import dataclass


@dataclass
class Config:
    """Application configuration."""

    host: str = "localhost"  # Server hostname
    port: int = 8080  # Server port
    debug: bool = False  # Enable debug mode
'''

CLI_PY = '''\
"""Command-line interface for mylib."""

HELP = """
Usage: mylib [options] <command>

Commands:
    run     Run the processor
    check   Check configuration
"""
'''

TEST_CORE_PY = '''\
"""Tests for mylib.core."""

import pytest


def test_greet_basic():
    """Test basic greeting."""
    from mylib.core import greet
    assert greet("World") == "Hello, World!"


class TestProcessor:
    """Tests for the Processor class."""

    def test_run_empty(self):
        from mylib.core import Processor
        p = Processor()
        assert p.run([]) == []
'''

PLAIN_PY = "class Plain:\n    pass\n"
PYDANTIC_PY = (
    "from pydantic import BaseModel\n\n\n"
    "class Params(BaseModel):\n"
    "    name: str\n"
    "    count: int = 0\n"
)
PKG_INIT_PY = (
    '"""Package pkg."""\n\n'
    "import os\n"
    "from ._impl import Foo\n"
    "from ._impl import Bar as Baz\n\n"
    '__version__ = "1.2.3"\n\n'
    '__all__ = ["Foo", "Baz", "__version__"]\n'
)


def main():
    base = tempfile.mkdtemp()
    lib = os.path.join(base, "mylib")
    os.makedirs(lib)
    tests = os.path.join(base, "tests")
    os.makedirs(tests)
    pkg = os.path.join(base, "pkg")
    os.makedirs(pkg)

    files = {
        os.path.join(lib, "core.py"): CORE_PY,
        os.path.join(lib, "__init__.py"): '"""mylib package."""\n',
        os.path.join(lib, "settings.py"): SETTINGS_PY,
        os.path.join(lib, "models.py"): MODELS_PY,
        os.path.join(lib, "cli.py"): CLI_PY,
        os.path.join(tests, "test_core.py"): TEST_CORE_PY,
        os.path.join(base, "plain.py"): PLAIN_PY,
        os.path.join(base, "pydantic_models.py"): PYDANTIC_PY,
        os.path.join(pkg, "_impl.py"): "class Foo:\n    pass\n\n\nclass Bar:\n    pass\n",
        os.path.join(pkg, "__init__.py"): PKG_INIT_PY,
    }
    for path, content in files.items():
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    extractor = PythonExtractor()
    source_paths = ["mylib/"]

    probes = [
        ("ref core", "ref", {"path": "core"}, source_paths),
        ("ref settings", "ref", {"path": "settings"}, source_paths),
        ("ref plain.py", "ref", {"path": "plain.py"}, []),
        ("ref pydantic_models.py", "ref", {"path": "pydantic_models.py"}, []),
        ("ref pkg", "ref", {"path": "pkg"}, []),
        ("ref pkg target Foo", "ref", {"path": "pkg", "target": "Foo"}, []),
        ("ref core target greet", "ref", {"path": "core", "target": "greet"}, source_paths),
        ("code-help cli", "code-help", {"path": "cli"}, source_paths),
        ("prose-desc core", "prose-desc", {"path": "core"}, source_paths),
        (
            "table-schema models Config",
            "table-schema",
            {"path": "models", "target": "Config"},
            source_paths,
        ),
        (
            "code-test whole",
            "code-test",
            {"path": "tests/test_core.py"},
            source_paths,
        ),
        (
            "code-test function",
            "code-test",
            {"path": "tests/test_core.py", "target": "test_greet_basic"},
            source_paths,
        ),
        (
            "code-test class",
            "code-test",
            {"path": "tests/test_core.py", "target": "TestProcessor"},
            source_paths,
        ),
    ]

    for label, directive, attrs, paths in probes:
        result = extractor.extract(directive, attrs, [], paths, base)
        print("=== " + label)
        print(repr(result))

    print("=== public_symbols core")
    print(repr(extractor.public_symbols(os.path.join(lib, "core.py"))))
    print("=== public_symbols pkg")
    print(repr(extractor.public_symbols(os.path.join(pkg, "__init__.py"))))
    print("=== module_docstring core")
    print(repr(extractor.module_docstring(os.path.join(lib, "core.py"))))
    print("=== symbol_details greet")
    print(repr(extractor.symbol_details(os.path.join(lib, "core.py"), "greet")))
    print("=== symbol_details Processor.run")
    print(repr(extractor.symbol_details(os.path.join(lib, "core.py"), "Processor.run")))
    print("base=" + base, file=sys.stderr)


main()
