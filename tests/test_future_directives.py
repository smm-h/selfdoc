"""Tests for the directives: prose-desc, list-tree, table-dep (and list-features removal)."""

import os

import pytest

from selfdoc.content import (
    resolve_content,
    resolve_list_tree,
    resolve_table_dep,
)
from selfdoc.extractors.python import PythonExtractor


# -- Fixtures -----------------------------------------------------------------


@pytest.fixture()
def sample_tree(tmp_path):
    """Create a sample directory structure for tree testing."""
    base = tmp_path / "myproject"
    base.mkdir()

    # Top-level files
    (base / "README.md").write_text("# My Project\n")
    (base / "setup.py").write_text("# setup\n")

    # src/ directory
    src = base / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text("# main\n")
    (src / "utils.py").write_text("# utils\n")

    # src/sub/ directory
    sub = src / "sub"
    sub.mkdir()
    (sub / "helper.py").write_text("# helper\n")

    # __pycache__ should be excluded
    cache = src / "__pycache__"
    cache.mkdir()
    (cache / "main.cpython-311.pyc").write_text("binary")

    # .git should be excluded
    git_dir = base / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("git config")

    return tmp_path


@pytest.fixture()
def pyproject_path(tmp_path):
    """Create a sample pyproject.toml for dependency testing."""
    content = """\
[project]
name = "myproject"
version = "1.0.0"
dependencies = [
    "requests>=2.28.0",
    "click>=8.0,<9.0",
    "pydantic",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "black>=23.0",
]
docs = [
    "sphinx>=5.0",
]
"""
    toml_file = tmp_path / "pyproject.toml"
    toml_file.write_text(content)
    return tmp_path


@pytest.fixture()
def modules_dir(tmp_path):
    """Create a directory of Python modules with docstrings for list-features testing."""
    pkg = tmp_path / "mylib"
    pkg.mkdir()

    (pkg / "__init__.py").write_text('"""Package init."""\n')

    (pkg / "build.py").write_text(
        '"""Build system for compiling templates into HTML output."""\n\ndef build(): pass\n'
    )
    (pkg / "check.py").write_text(
        '"""Validates directive resolution and computes documentation coverage."""\n\ndef check(): pass\n'
    )
    (pkg / "cli.py").write_text(
        '"""Command-line interface using strictcli."""\n\ndef main(): pass\n'
    )
    (pkg / "config.py").write_text(
        '"""Loads and validates selfdoc.json configuration."""\n\ndef load(): pass\n'
    )
    # No docstring -- should be skipped
    (pkg / "empty.py").write_text("def nothing(): pass\n")
    # Test file -- should be skipped
    (pkg / "test_build.py").write_text('"""Tests for build."""\n')

    return tmp_path


@pytest.fixture()
def prose_desc_module(tmp_path):
    """Create a Python module with a docstring for prose-desc testing."""
    src = tmp_path / "mylib"
    src.mkdir()

    (src / "core.py").write_text(
        '"""Core module providing essential utilities.\n\n'
        "This module handles the main processing pipeline\n"
        "and exposes the public API.\n\n"
        "Args:\n"
        "    verbose: Enable verbose output.\n"
        "    config_path: Path to the config file.\n"
        '"""\n\n'
        "def process(): pass\n"
    )

    (src / "empty.py").write_text("# No docstring here\ndef hello(): pass\n")

    return tmp_path


# -- prose-desc tests ---------------------------------------------------------


class TestProseDesc:
    """Tests for the prose-desc directive via the Python extractor."""

    def test_extracts_module_docstring(self, prose_desc_module):
        ext = PythonExtractor()
        result = ext.extract(
            "prose-desc",
            {"path": "core"},
            [],
            ["mylib/"],
            str(prose_desc_module),
        )
        assert "Core module providing essential utilities." in result
        assert "main processing pipeline" in result
        # Should format Google-style sections
        assert "**Args:**" in result
        assert "`verbose`" in result
        assert "`config_path`" in result

    def test_no_docstring_returns_error(self, prose_desc_module):
        ext = PythonExtractor()
        result = ext.extract(
            "prose-desc",
            {"path": "empty"},
            [],
            ["mylib/"],
            str(prose_desc_module),
        )
        assert "no docstring found" in result

    def test_module_not_found_returns_error(self, prose_desc_module):
        ext = PythonExtractor()
        result = ext.extract(
            "prose-desc",
            {"path": "nonexistent"},
            [],
            ["mylib/"],
            str(prose_desc_module),
        )
        assert "not found" in result

    def test_no_heading_or_function_list(self, prose_desc_module):
        """prose-desc should not include heading or function listings."""
        ext = PythonExtractor()
        result = ext.extract(
            "prose-desc",
            {"path": "core"},
            [],
            ["mylib/"],
            str(prose_desc_module),
        )
        # Should NOT have a ## heading (unlike :::ref)
        assert not result.startswith("##")
        # Should NOT list the process() function signature
        assert "def process" not in result
        assert "```python" not in result


# -- list-tree tests ----------------------------------------------------------


class TestListTree:
    """Tests for the list-tree directive."""

    def test_produces_tree_structure(self, sample_tree):
        result = resolve_list_tree(
            {"path": "myproject"}, str(sample_tree)
        )
        assert "```" in result
        assert "myproject/" in result
        # Should contain files and directories
        assert "README.md" in result
        assert "setup.py" in result
        assert "src/" in result
        assert "main.py" in result
        assert "utils.py" in result
        assert "sub/" in result
        assert "helper.py" in result

    def test_excludes_pycache_and_git(self, sample_tree):
        result = resolve_list_tree(
            {"path": "myproject"}, str(sample_tree)
        )
        assert "__pycache__" not in result
        assert ".git" not in result
        assert ".pyc" not in result

    def test_depth_limit(self, sample_tree):
        result = resolve_list_tree(
            {"path": "myproject", "depth": "1"}, str(sample_tree)
        )
        # At depth 1, should show top-level entries but not sub-entries
        assert "README.md" in result
        assert "src/" in result
        # Should NOT show files inside src/
        assert "main.py" not in result

    def test_uses_tree_connectors(self, sample_tree):
        result = resolve_list_tree(
            {"path": "myproject"}, str(sample_tree)
        )
        # Should use proper tree connectors
        assert any(c in result for c in ["├── ", "└── "])

    def test_nonexistent_directory(self, sample_tree):
        result = resolve_list_tree(
            {"path": "nonexistent"}, str(sample_tree)
        )
        assert "not found" in result

    def test_missing_path_attr(self, sample_tree):
        result = resolve_list_tree({}, str(sample_tree))
        assert "requires a path" in result

    def test_via_resolve_content(self, sample_tree):
        """list-tree should be dispatched by resolve_content."""
        result = resolve_content(
            "list-tree", {"path": "myproject"}, [], str(sample_tree)
        )
        assert result is not None
        assert "myproject/" in result


# -- table-dep tests ----------------------------------------------------------


class TestTableDep:
    """Tests for the table-dep directive."""

    def test_produces_dependency_table(self, pyproject_path):
        result = resolve_table_dep(
            {"path": "pyproject.toml"}, str(pyproject_path)
        )
        assert "| Package | Version Constraint |" in result
        assert "| --- | --- |" in result
        assert "`requests`" in result
        assert ">=2.28.0" in result
        assert "`click`" in result
        assert ">=8.0,<9.0" in result
        assert "`pydantic`" in result
        assert "\\*" in result or "*" in result  # pydantic has no constraint

    def test_includes_optional_dependencies(self, pyproject_path):
        result = resolve_table_dep(
            {"path": "pyproject.toml"}, str(pyproject_path)
        )
        assert "[dev]" in result
        assert "`pytest`" in result
        assert "`black`" in result
        assert "[docs]" in result
        assert "`sphinx`" in result

    def test_file_not_found(self, pyproject_path):
        result = resolve_table_dep(
            {"path": "nonexistent.toml"}, str(pyproject_path)
        )
        assert "not found" in result

    def test_missing_path_attr(self, pyproject_path):
        result = resolve_table_dep({}, str(pyproject_path))
        assert "requires a path" in result

    def test_via_resolve_content(self, pyproject_path):
        """table-dep should be dispatched by resolve_content."""
        result = resolve_content(
            "table-dep", {"path": "pyproject.toml"}, [], str(pyproject_path)
        )
        assert result is not None
        assert "`requests`" in result


# -- list-features removal (Phase 7.3) ----------------------------------------


class TestListFeaturesRemoved:
    """list-features was removed and superseded by list-modules."""

    def test_resolve_content_returns_none_for_removed_directive(self, modules_dir):
        """resolve_content no longer recognizes list-features."""
        result = resolve_content(
            "list-features", {"path": "mylib"}, [], str(modules_dir)
        )
        assert result is None

    def test_removed_directive_raises_unknown_directive_error(self):
        """Using list-features produces the standard unknown-directive error."""
        from selfdoc.directives import parse_directives, DirectiveError
        from selfdoc.catalog import ALL_BUILTIN_DIRECTIVES

        assert "list-features" not in ALL_BUILTIN_DIRECTIVES
        with pytest.raises(DirectiveError, match="list-features"):
            parse_directives(
                ':-: list-features path="src/"\n',
                valid_names=set(ALL_BUILTIN_DIRECTIVES),
            )
