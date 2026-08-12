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
        "author": {"name": "Test Author", "url": "https://author.example"},
        "search_engine": "pagefind",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
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
    # Ends with closing frontmatter fence and a blank line
    assert content.endswith("---\n\n")


def test_post_new_writes_no_project_field(tmp_path, monkeypatch):
    """The scaffold emits no 'project' key: nothing ever read it.

    A post's owning project is the repository the post lives in, and the
    assembly learns it from the manifest the deploy copies -- never from a
    line in the post's own frontmatter that no reader consulted.
    """
    _setup_project(tmp_path, config_overrides={
        "topology": {"slug": "my-cool-project"},
    })
    monkeypatch.chdir(tmp_path)

    _cmd_post_new(None, title="No Project Key")

    today = datetime.date.today().isoformat()
    filepath = tmp_path / ".selfdoc" / "posts" / f"{today}-no-project-key.md"
    content = filepath.read_text(encoding="utf-8")
    assert "project:" not in content


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
