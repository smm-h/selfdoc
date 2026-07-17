"""Tests for the ``selfdoc post new`` CLI command (``_cmd_post_new``)."""

from __future__ import annotations

import datetime
import json
import os

import pytest

from selfblog.cli import _cmd_post_new


def _setup_project(tmp_path, config_overrides=None):
    """Create a minimal selfdoc project directory."""
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0", "indexed": True}],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }
    if config_overrides:
        config.update(config_overrides)
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    return tmp_path


# ------------------------------------------------------------------
# Happy paths
# ------------------------------------------------------------------


def test_post_new_basic(tmp_path, monkeypatch):
    """Creates a post file with the expected name pattern."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    today = datetime.date.today().isoformat()
    _cmd_post_new(None, title="My First Post")

    expected = os.path.join(".selfdoc", "posts", f"{today}-my-first-post.md")
    assert os.path.isfile(expected)


def test_post_new_default_posts_dir(tmp_path, monkeypatch):
    """Uses .selfdoc/posts/ when no posts config is present."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    _cmd_post_new(None, title="Default Dir Test")

    today = datetime.date.today().isoformat()
    expected = tmp_path / ".selfdoc" / "posts" / f"{today}-default-dir-test.md"
    assert expected.is_file()


def test_post_new_custom_posts_dir(tmp_path, monkeypatch):
    """Uses posts.dir from config when specified."""
    _setup_project(tmp_path, config_overrides={
        "posts": {"dir": "blog/articles/"},
    })
    monkeypatch.chdir(tmp_path)

    _cmd_post_new(None, title="Custom Dir")

    today = datetime.date.today().isoformat()
    expected = tmp_path / "blog" / "articles" / f"{today}-custom-dir.md"
    assert expected.is_file()


def test_post_new_slug_generation(tmp_path, monkeypatch):
    """Title 'Hello World' produces slug 'hello-world' in filename."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    _cmd_post_new(None, title="Hello World")

    today = datetime.date.today().isoformat()
    expected = tmp_path / ".selfdoc" / "posts" / f"{today}-hello-world.md"
    assert expected.is_file()


def test_post_new_frontmatter_content(tmp_path, monkeypatch):
    """All expected frontmatter fields are present with correct values."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    _cmd_post_new(None, title="Frontmatter Check")

    today = datetime.date.today().isoformat()
    filepath = tmp_path / ".selfdoc" / "posts" / f"{today}-frontmatter-check.md"
    content = filepath.read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert "title: Frontmatter Check\n" in content
    assert f"date: {today}\n" in content
    assert "slug: frontmatter-check\n" in content
    assert "tags: []\n" in content
    assert "draft: true\n" in content
    assert "project: " in content
    # Ends with closing frontmatter fence and a blank line
    assert content.endswith("---\n\n")


def test_post_new_project_from_topology(tmp_path, monkeypatch):
    """project field comes from topology.slug when present."""
    _setup_project(tmp_path, config_overrides={
        "topology": {"slug": "my-cool-project"},
    })
    monkeypatch.chdir(tmp_path)

    _cmd_post_new(None, title="Topology Test")

    today = datetime.date.today().isoformat()
    filepath = tmp_path / ".selfdoc" / "posts" / f"{today}-topology-test.md"
    content = filepath.read_text(encoding="utf-8")
    assert "project: my-cool-project\n" in content


def test_post_new_project_from_dirname(tmp_path, monkeypatch):
    """project field falls back to kebab-cased directory name when no topology.slug."""
    # Create the project in a subdirectory with a meaningful name
    project_dir = tmp_path / "My Cool Project"
    project_dir.mkdir()
    _setup_project(project_dir)
    monkeypatch.chdir(project_dir)

    _cmd_post_new(None, title="Name Fallback")

    today = datetime.date.today().isoformat()
    filepath = project_dir / ".selfdoc" / "posts" / f"{today}-name-fallback.md"
    content = filepath.read_text(encoding="utf-8")
    assert "project: my-cool-project\n" in content


# ------------------------------------------------------------------
# Error paths
# ------------------------------------------------------------------


def test_post_new_file_already_exists(tmp_path, monkeypatch):
    """SystemExit when the post file already exists."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    today = datetime.date.today().isoformat()
    posts_dir = tmp_path / ".selfdoc" / "posts"
    posts_dir.mkdir(parents=True)
    (posts_dir / f"{today}-duplicate.md").write_text("existing")

    with pytest.raises(SystemExit):
        _cmd_post_new(None, title="Duplicate")


def test_post_new_no_title(tmp_path, monkeypatch):
    """SystemExit when title is empty."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _cmd_post_new(None, title="")


def test_post_new_no_title_default(tmp_path, monkeypatch):
    """SystemExit when title is omitted (default empty string)."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _cmd_post_new(None)


def test_post_new_no_config(tmp_path, monkeypatch):
    """SystemExit when no selfdoc.json exists."""
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _cmd_post_new(None, title="Orphan Post")


# ------------------------------------------------------------------
# Directory creation
# ------------------------------------------------------------------


def test_post_new_creates_dir(tmp_path, monkeypatch):
    """Creates the posts directory (and parents) if it does not exist."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    posts_dir = tmp_path / ".selfdoc" / "posts"
    assert not posts_dir.exists()

    _cmd_post_new(None, title="Dir Creation Test")

    assert posts_dir.is_dir()
    today = datetime.date.today().isoformat()
    assert (posts_dir / f"{today}-dir-creation-test.md").is_file()
