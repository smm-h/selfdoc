"""Tests for selfdoc.cli commands."""

import json
import os
import subprocess
import sys

import pytest


@pytest.fixture()
def project_dir(tmp_path, monkeypatch):
    """Create a minimal Python project and chdir into it."""
    # Create pyproject.toml so init detects Python
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "testproj"\nversion = "1.0.0"\n'
    )

    # Create a package directory so init detects the main module
    pkg_dir = tmp_path / "testproj"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")

    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_init_creates_config_and_docs(project_dir):
    """selfdoc init creates selfdoc.json and docs/index.md."""
    from selfdoc.cli import _cmd_init

    class Args:
        pass

    _cmd_init(Args())

    # selfdoc.json was created
    config_path = project_dir / "selfdoc.json"
    assert config_path.exists()

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    assert config["language"] == "python"
    assert "testproj/" in config["source"]
    assert config["docs"] == "docs/"
    assert config["output"] == "docs/_build/"

    # docs/index.md was created
    index_path = project_dir / "docs" / "index.md"
    assert index_path.exists()

    content = index_path.read_text()
    assert "testproj" in content
    assert ":::module testproj" in content


def test_init_aborts_if_config_exists(project_dir):
    """selfdoc init aborts if selfdoc.json already exists."""
    (project_dir / "selfdoc.json").write_text("{}")

    from selfdoc.cli import _cmd_init

    class Args:
        pass

    with pytest.raises(SystemExit):
        _cmd_init(Args())


def test_build_produces_output(project_dir):
    """selfdoc build produces HTML in the output directory."""
    from selfdoc.cli import _cmd_init, _cmd_build

    class Args:
        pass

    # First init
    _cmd_init(Args())

    # Then build
    _cmd_build(Args())

    output_dir = project_dir / "docs" / "_build"
    assert output_dir.exists()
    assert (output_dir / "index.html").exists()

    content = (output_dir / "index.html").read_text()
    assert "<!DOCTYPE html>" in content


def test_check_finds_directives(project_dir, capsys):
    """selfdoc check reports directive validation results."""
    from selfdoc.cli import _cmd_init, _cmd_check

    class Args:
        pass

    _cmd_init(Args())

    # The starter template has a :::module directive that resolves OK
    _cmd_check(Args())

    captured = capsys.readouterr()
    assert "OK" in captured.out
    assert "module" in captured.out
    assert "directive(s)" in captured.out


def test_build_without_init_fails(project_dir):
    """selfdoc build without selfdoc.json exits with error."""
    from selfdoc.cli import _cmd_build

    class Args:
        pass

    with pytest.raises(SystemExit):
        _cmd_build(Args())
