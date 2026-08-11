"""Tests for `selfdoc init` on projects with no source code.

A portfolio or personal site is pure content: markdown pages, no code to
extract from.  Init must produce a configuration for such a project that
load_config accepts and build consumes without any hand-editing, and a
source-dependent directive used in such a project must fail loudly rather
than render a placeholder note.
"""

import json

import pytest


BASE_URL = "https://example.com"


@pytest.fixture()
def codeless_dir(tmp_path, monkeypatch):
    """A project directory containing only markdown -- no code, no manifests."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "about.md").write_text(
        "---\n"
        "title: About\n"
        "description: A short page about this site and the person who writes it.\n"
        "---\n"
        "\n"
        "# About\n"
        "\n"
        "This page has no code behind it.\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def code_dir(tmp_path, monkeypatch):
    """A minimal Python project directory."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "testproj"\nversion = "2.3.4"\n'
    )
    pkg = tmp_path / "testproj"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""Test package."""\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _read_config(project_dir):
    with open(project_dir / "selfdoc.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_init_accepts_codeless_project(codeless_dir):
    """init no longer refuses a directory with no detectable language."""
    from selfdoc.cli import _cmd_init

    _cmd_init(None, base_url=BASE_URL, auto_commit=False)

    config = _read_config(codeless_dir)
    # No source declaration at all -- the project has nothing to extract from.
    assert "source" not in config
    assert config["base_url"] == BASE_URL


def test_codeless_init_config_loads(codeless_dir):
    """The emitted config passes load_config with no hand-editing."""
    from selfdoc.cli import _cmd_init
    from selfdoc.config import load_config

    _cmd_init(None, base_url=BASE_URL, auto_commit=False)

    config = load_config(".")
    assert config is not None
    assert config["base_url"] == BASE_URL
    assert config["source"] == []
    assert config["versions"] and "indexed" not in config["versions"][0]
    assert config["locales"] and config["locales"][0]["code"] == "en"


def test_codeless_init_builds(codeless_dir):
    """init then build produces HTML for a project with no code."""
    from selfdoc.cli import _cmd_init
    from selfdoc.build import build

    _cmd_init(None, base_url=BASE_URL, auto_commit=False)

    build(".")

    # Pages land under the always-prefixed /<locale>/<version>/ layout that
    # init's emitted versions and locales arrays declare.
    out = codeless_dir / "docs" / "_build"
    assert (out / "index.html").exists()
    assert (out / "en" / "0.1.0" / "index.html").exists()
    assert (out / "en" / "0.1.0" / "about" / "index.html").exists()
    assert "<!DOCTYPE html>" in (out / "en" / "0.1.0" / "index.html").read_text()


def test_codeless_starter_has_no_code_directive(codeless_dir):
    """The starter page for a codeless project carries no extraction directive."""
    from selfdoc.cli import _cmd_init

    _cmd_init(None, base_url=BASE_URL, auto_commit=False)

    index = (codeless_dir / "docs" / "index.md").read_text()
    assert ":-: ref" not in index
    assert "API Reference" not in index


def test_code_directive_in_codeless_project_hard_errors(codeless_dir):
    """A code-extraction directive with no source configured is a hard error."""
    from selfdoc.cli import _cmd_init
    from selfdoc.build import build

    _cmd_init(None, base_url=BASE_URL, auto_commit=False)
    (codeless_dir / "docs" / "api.md").write_text(
        "---\n"
        "title: API\n"
        "description: An API page in a project that declares no source code.\n"
        "---\n"
        "\n"
        "# API\n"
        "\n"
        ':-: ref path="nothing" lang="python"\n'
    )

    with pytest.raises(RuntimeError) as exc_info:
        build(".")

    message = str(exc_info.value)
    assert "ref" in message
    assert "source" in message


def test_list_modules_in_codeless_project_hard_errors(codeless_dir):
    """list-modules with no source configured is a hard error, not a note."""
    from selfdoc_core.content import resolve_content

    (codeless_dir / "pages").mkdir()

    with pytest.raises(RuntimeError) as exc_info:
        resolve_content(
            "list-modules", {"path": "pages"}, [], str(codeless_dir), config={},
        )

    assert "source" in str(exc_info.value)


def test_generate_docs_hard_errors_for_codeless_project(codeless_dir):
    """generate_docs refuses a project with no source rather than emitting an empty index."""
    from selfdoc.cli import _cmd_init
    from selfdoc.config import load_config
    from selfdoc.gen import generate_docs

    _cmd_init(None, base_url=BASE_URL, auto_commit=False)

    with pytest.raises(RuntimeError) as exc_info:
        generate_docs(load_config("."), base_dir=".")

    assert "source" in str(exc_info.value)


def test_gen_command_skips_reference_pages_for_codeless_project(
    codeless_dir, capsys,
):
    """`selfdoc gen` says so and writes no API index when there is no source."""
    from selfdoc.cli import _cmd_init, _cmd_gen

    _cmd_init(None, base_url=BASE_URL, auto_commit=False)
    capsys.readouterr()

    _cmd_gen(None, auto_commit=False)

    assert not (codeless_dir / "docs" / "gen-index.md").exists()
    out = capsys.readouterr().out
    assert "source" in out


def test_init_emits_loadable_config_for_code_project(code_dir):
    """A code project's emitted config also loads and builds unedited."""
    from selfdoc.cli import _cmd_init
    from selfdoc.config import load_config
    from selfdoc.build import build

    _cmd_init(None, base_url=BASE_URL, auto_commit=False)

    raw = _read_config(code_dir)
    assert raw["base_url"] == BASE_URL
    assert raw["versions"] == [{"version": "2.3.4"}]
    assert raw["locales"] == [
        {"code": "en", "label": "English", "default": True}
    ]

    config = load_config(".")
    assert config["source"]

    build(".")
    assert (code_dir / "docs" / "_build" / "en" / "2.3.4" / "index.html").exists()
