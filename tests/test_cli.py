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

    _cmd_init()

    # selfdoc.json was created
    config_path = project_dir / "selfdoc.json"
    assert config_path.exists()

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    assert isinstance(config["source"], list)
    assert any(e["path"] == "testproj/" and e["language"] == "python" for e in config["source"])
    assert config["docs"] == "docs/"
    assert config["output"] == "docs/_build/"

    # docs/index.md was created
    index_path = project_dir / "docs" / "index.md"
    assert index_path.exists()

    content = index_path.read_text()
    assert "testproj" in content
    assert ':-: ref path="testproj" lang="python"' in content


def test_init_index_has_frontmatter(project_dir):
    """selfdoc init produces docs/index.md with description and date in frontmatter."""
    import datetime
    from selfdoc.cli import _cmd_init

    _cmd_init()

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

    with pytest.raises(SystemExit):
        _cmd_init()


def test_init_detects_multiple_languages(tmp_path, monkeypatch):
    """selfdoc init detects all languages and creates multi-language source config."""
    # Create both Python and Go marker files
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "polyglot"\nversion = "0.1.0"\n'
    )
    (tmp_path / "go.mod").write_text("module example.com/polyglot\n")

    # Create a Python package so _detect_source_entries finds it
    pkg_dir = tmp_path / "polyglot"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")

    # Create a Go directory so _detect_source_entries finds it
    cmd_dir = tmp_path / "cmd"
    cmd_dir.mkdir()

    monkeypatch.chdir(tmp_path)

    from selfdoc.cli import _cmd_init

    _cmd_init()

    config_path = tmp_path / "selfdoc.json"
    assert config_path.exists()

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    source = config["source"]
    languages = [e["language"] for e in source]
    assert "python" in languages
    assert "go" in languages

    # Verify Python source paths detected
    python_entries = [e for e in source if e["language"] == "python"]
    assert len(python_entries) >= 1

    # Verify Go source paths detected
    go_entries = [e for e in source if e["language"] == "go"]
    assert len(go_entries) >= 1


def _add_base_url(project_dir):
    """Add base_url, versions, and locales to selfdoc.json after init."""
    config_path = project_dir / "selfdoc.json"
    config = json.load(open(config_path, "r", encoding="utf-8"))
    config["base_url"] = "https://example.com"
    config["versions"] = [{"version": "1.0.0", "indexed": True}]
    config["locales"] = [{"code": "en", "label": "English", "default": True}]
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)


def test_build_produces_output(project_dir):
    """selfdoc build produces HTML in the output directory even when lints fail."""
    from selfdoc.cli import _cmd_init, _cmd_build

    # First init
    _cmd_init()
    _add_base_url(project_dir)

    # Build exits non-zero due to SEO lints on the starter template,
    # but the output files are still written before the lint check.
    try:
        _cmd_build()
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

    _cmd_init()
    _add_base_url(project_dir)

    # The starter template has a :::module directive that resolves OK,
    # but check exits 1 due to SEO warnings on the starter template.
    try:
        _cmd_check()
    except SystemExit:
        pass

    captured = capsys.readouterr()
    assert "OK" in captured.out
    assert "ref" in captured.out
    assert "directive(s)" in captured.out


def test_build_shows_seo_warnings(project_dir, capsys):
    """selfdoc build shows warnings but exits 0 when only warnings exist."""
    from selfdoc.cli import _cmd_init, _cmd_build

    _cmd_init()
    _add_base_url(project_dir)

    # The starter template triggers SEO warnings (e.g. SEO009 short
    # description) but no errors, so build exits 0.
    _cmd_build()

    captured = capsys.readouterr()
    # Build output is still written
    assert "Built" in captured.out
    # Individual lint messages are printed in compiler-style format
    assert "warning:" in captured.out
    assert "SEO" in captured.out
    assert "SEO warning(s) found" in captured.out


def test_build_exits_1_on_errors(project_dir, capsys):
    """selfdoc build exits 1 when lint errors (not just warnings) exist."""
    from selfdoc.cli import _cmd_init, _cmd_build

    _cmd_init()
    _add_base_url(project_dir)

    # Remove the description from frontmatter to trigger SEO006 (error)
    index_path = project_dir / "docs" / "index.md"
    index_path.write_text("# Test\n\nContent.\n")

    with pytest.raises(SystemExit) as exc_info:
        _cmd_build()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "error:" in captured.out
    assert "SEO006" in captured.out


def test_check_always_runs_seo_lints(project_dir, capsys):
    """selfdoc check always runs SEO lints (no --no-seo flag)."""
    from selfdoc.cli import _cmd_init, _cmd_check

    _cmd_init()
    _add_base_url(project_dir)

    # SEO warnings appear (e.g. SEO009 short description) but only
    # warnings, so check exits 0.
    _cmd_check()

    captured = capsys.readouterr()
    assert "SEO" in captured.out


def test_check_exits_1_on_errors(project_dir, capsys):
    """selfdoc check exits 1 when lint errors exist."""
    from selfdoc.cli import _cmd_init, _cmd_check

    _cmd_init()
    _add_base_url(project_dir)

    # Remove the description to trigger SEO006 (error severity)
    index_path = project_dir / "docs" / "index.md"
    index_path.write_text("# Test\n\nContent.\n")

    with pytest.raises(SystemExit) as exc_info:
        _cmd_check()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "SEO006" in captured.out


def test_build_without_init_fails(project_dir):
    """selfdoc build without selfdoc.json exits with error."""
    from selfdoc.cli import _cmd_build

    with pytest.raises(SystemExit):
        _cmd_build()
