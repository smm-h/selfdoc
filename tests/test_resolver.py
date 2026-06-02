"""Tests for selfdoc.resolver -- multi-language dispatch and source_entry tracking."""

import os

import pytest

from selfdoc.resolver import Resolver, make_resolver
from selfdoc.extractors import SourceEntry
from selfdoc.check import ResolvedDirective


def _make_config(**overrides):
    """Create a minimal valid config dict with optional overrides."""
    base = {
        "source": [{"path": "src/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "deploy": None,
        "directives": {},
    }
    base.update(overrides)
    return base


# -- Resolver class basics --


def test_make_resolver_returns_resolver(tmp_path):
    """make_resolver returns a Resolver instance."""
    config = _make_config()
    resolver = make_resolver(config, str(tmp_path))
    assert isinstance(resolver, Resolver)


def test_resolver_is_callable(tmp_path):
    """Resolver instances are callable."""
    config = _make_config()
    resolver = make_resolver(config, str(tmp_path))
    assert callable(resolver)


# -- Single-language dispatch --


def test_resolver_dispatches_single_language(tmp_path):
    """Single-language resolver dispatches to the correct extractor."""
    # Create a Python source file
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text(
        '"""My module."""\n\ndef greet():\n    """Say hi."""\n    pass\n'
    )

    config = _make_config()
    resolver = make_resolver(config, str(tmp_path))

    result = resolver("ref", {"path": "src"}, [])
    # Should resolve via Python extractor (module found)
    assert "greet" in result


# -- Multi-language dispatch --


def test_resolver_dispatches_to_correct_extractor(tmp_path):
    """Python and Go sources: directive with Python path resolves via Python extractor."""
    # Python source
    py_dir = tmp_path / "pylib"
    py_dir.mkdir()
    (py_dir / "__init__.py").write_text(
        '"""Python lib."""\n\ndef py_func():\n    """A function."""\n    pass\n'
    )

    # Go source (empty dir with a .go file)
    go_dir = tmp_path / "golib"
    go_dir.mkdir()
    (go_dir / "main.go").write_text(
        'package main\n\n// Hello says hello.\nfunc Hello() {}\n'
    )

    config = _make_config(source=[
        {"path": "pylib/", "language": "python"},
        {"path": "golib/", "language": "go"},
    ])
    resolver = make_resolver(config, str(tmp_path))

    # Resolve a Python module path
    result = resolver("ref", {"path": "pylib"}, [])
    assert "py_func" in result

    # Resolve a Go package path
    result = resolver("ref", {"path": "golib"}, [])
    assert "Hello" in result


def test_resolver_cross_language_ambiguity_error(tmp_path):
    """Two language groups that both resolve the same path should raise an error."""
    # Create a directory "shared/" with both Python and Go files
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    (shared_dir / "__init__.py").write_text(
        '"""Shared module."""\n\ndef shared_func():\n    pass\n'
    )
    (shared_dir / "main.go").write_text(
        'package shared\n\nfunc SharedFunc() {}\n'
    )

    config = _make_config(source=[
        {"path": "shared/", "language": "python"},
        {"path": "shared/", "language": "go"},
    ])
    resolver = make_resolver(config, str(tmp_path))

    # Both Python and Go extractors should find "shared" path
    # which should raise an ambiguity error
    with pytest.raises(RuntimeError, match="Ambiguous"):
        resolver("ref", {"path": "shared"}, [])


# -- last_source_entry tracking --


def test_resolver_sets_last_source_entry(tmp_path):
    """After resolving, resolver.last_source_entry is set correctly."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text(
        '"""Module."""\n\ndef func():\n    """Doc."""\n    pass\n'
    )

    config = _make_config()
    resolver = make_resolver(config, str(tmp_path))

    # Before resolving, last_source_entry is None
    assert resolver.last_source_entry is None

    # Resolve a directive with a valid path
    resolver("ref", {"path": "src"}, [])

    # last_source_entry should now be set
    assert resolver.last_source_entry is not None
    assert isinstance(resolver.last_source_entry, SourceEntry)
    assert resolver.last_source_entry.language == "python"
    assert resolver.last_source_entry.path == "src/"


def test_resolver_clears_last_source_entry_on_content_directive(tmp_path):
    """Content directives should not set last_source_entry."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text('"""Module."""\n')

    config = _make_config()
    resolver = make_resolver(config, str(tmp_path))

    # Resolve a content directive (e.g., list-glossary)
    resolver("list-glossary", {}, ["**Term**: Def"])

    # last_source_entry should be None (content directives are language-agnostic)
    assert resolver.last_source_entry is None


# -- ResolvedDirective.source_entry --


def test_resolved_directive_has_source_entry():
    """ResolvedDirective.source_entry field exists and defaults to None."""
    rd = ResolvedDirective(
        name="ref",
        attrs={"path": "mylib"},
        content="resolved content",
    )
    assert rd.source_entry is None


def test_resolved_directive_stores_source_entry():
    """ResolvedDirective.source_entry can store a SourceEntry."""
    from selfdoc.extractors import EXTRACTORS

    entry = SourceEntry(
        path="src/", language="python", extractor=EXTRACTORS["python"],
    )
    rd = ResolvedDirective(
        name="ref",
        attrs={"path": "src"},
        content="resolved content",
        source_entry=entry,
    )
    assert rd.source_entry is entry
    assert rd.source_entry.language == "python"


# -- Multi-language with zero matches falls through --


def test_resolver_zero_matches_uses_first_group_for_error(tmp_path):
    """When no group matches, the first group's extractor handles the error."""
    py_dir = tmp_path / "pylib"
    py_dir.mkdir()
    (py_dir / "__init__.py").write_text('"""Module."""\n')

    go_dir = tmp_path / "golib"
    go_dir.mkdir()
    (go_dir / "main.go").write_text('package main\n')

    config = _make_config(source=[
        {"path": "pylib/", "language": "python"},
        {"path": "golib/", "language": "go"},
    ])
    resolver = make_resolver(config, str(tmp_path))

    # Try to resolve a path that doesn't exist in either group
    result = resolver("ref", {"path": "nonexistent.module"}, [])
    # Should get an error marker, not crash
    assert "not found" in result


# -- Custom directives still work --


def test_custom_directives_work_with_resolver_class(tmp_path):
    """Custom directives should still work with the Resolver class."""
    script_path = tmp_path / "my_plugin.py"
    script_path.write_text(
        "def resolve(attrs, config, body):\n"
        "    return f'custom: {attrs.get(\"key\", \"\")}'\n"
    )

    config = _make_config(directives={"my-custom": "my_plugin.py"})
    resolver = make_resolver(config, str(tmp_path))

    result = resolver("my-custom", {"key": "value"}, [])
    assert result == "custom: value"
