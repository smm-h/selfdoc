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
    assert ':-: ref path="testproj"' in content


def test_init_index_has_frontmatter(project_dir):
    """selfdoc init produces docs/index.md with description and date in frontmatter."""
    import datetime
    from selfdoc.cli import _cmd_init

    class Args:
        pass

    _cmd_init(Args())

    index_path = project_dir / "docs" / "index.md"
    content = index_path.read_text()

    # Check frontmatter delimiters
    assert content.startswith("---\n")
    # Extract frontmatter block
    parts = content.split("---\n", 2)
    assert len(parts) >= 3, "frontmatter must have opening and closing ---"
    fm_text = parts[1]

    assert "description: Documentation for" in fm_text
    assert "date: " in fm_text
    # Verify date is a valid ISO date
    for line in fm_text.strip().split("\n"):
        if line.startswith("date: "):
            date_val = line[len("date: "):]
            # Should be today's date in ISO format
            datetime.date.fromisoformat(date_val)


def test_init_aborts_if_config_exists(project_dir):
    """selfdoc init aborts if selfdoc.json already exists."""
    (project_dir / "selfdoc.json").write_text("{}")

    from selfdoc.cli import _cmd_init

    class Args:
        pass

    with pytest.raises(SystemExit):
        _cmd_init(Args())


def _add_base_url(project_dir):
    """Add base_url to selfdoc.json after init (required field)."""
    config_path = project_dir / "selfdoc.json"
    config = json.load(open(config_path, "r", encoding="utf-8"))
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)


def test_build_produces_output(project_dir):
    """selfdoc build produces HTML in the output directory even when lints fail."""
    from selfdoc.cli import _cmd_init, _cmd_build

    class Args:
        pass

    # First init
    _cmd_init(Args())
    _add_base_url(project_dir)

    # Build exits non-zero due to SEO lints on the starter template,
    # but the output files are still written before the lint check.
    try:
        _cmd_build(Args())
    except SystemExit:
        pass

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
    _add_base_url(project_dir)

    # The starter template has a :::module directive that resolves OK,
    # but check exits 1 due to SEO warnings on the starter template.
    try:
        _cmd_check(Args())
    except SystemExit:
        pass

    captured = capsys.readouterr()
    assert "OK" in captured.out
    assert "ref" in captured.out
    assert "directive(s)" in captured.out


def test_build_shows_seo_warnings(project_dir, capsys):
    """selfdoc build exits non-zero and shows individual lint messages."""
    from selfdoc.cli import _cmd_init, _cmd_build

    class Args:
        pass

    _cmd_init(Args())
    _add_base_url(project_dir)

    # The starter template has no frontmatter description,
    # so SEO006 (missing description) will fire as a warning.
    with pytest.raises(SystemExit) as exc_info:
        _cmd_build(Args())

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    # Build output is still written
    assert "Built" in captured.out
    # Individual lint messages are printed in compiler-style format
    assert "warning:" in captured.out
    assert "SEO" in captured.out
    assert "SEO warning(s) found" in captured.out


def test_check_always_runs_seo_lints(project_dir, capsys):
    """selfdoc check always runs SEO lints (no --no-seo flag)."""
    from selfdoc.cli import _cmd_init, _cmd_check

    class Args:
        pass

    _cmd_init(Args())
    _add_base_url(project_dir)

    # SEO warnings always appear (e.g. SEO006 missing description)
    with pytest.raises(SystemExit) as exc_info:
        _cmd_check(Args())

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "SEO" in captured.out


def test_build_without_init_fails(project_dir):
    """selfdoc build without selfdoc.json exits with error."""
    from selfdoc.cli import _cmd_build

    class Args:
        pass

    with pytest.raises(SystemExit):
        _cmd_build(Args())
