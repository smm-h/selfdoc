"""Tests for the ``selfdoc post list`` CLI command (``_cmd_post_list``)."""

from __future__ import annotations

import json
import os

import pytest

from selfdoc.cli import _cmd_post_list


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
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text("")
    return tmp_path


def _write_post(posts_dir, filename, frontmatter_lines, body=""):
    """Write a markdown post file with given frontmatter."""
    path = os.path.join(posts_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = "---\n" + "\n".join(frontmatter_lines) + "\n---\n" + body
    with open(path, "w") as f:
        f.write(content)


# ------------------------------------------------------------------
# Error paths
# ------------------------------------------------------------------


def test_post_list_no_config(tmp_path, monkeypatch, capsys):
    """SystemExit when no selfdoc.json exists."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        _cmd_post_list()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No selfdoc.json" in captured.err


# ------------------------------------------------------------------
# Empty state
# ------------------------------------------------------------------


def test_post_list_no_posts(tmp_path, monkeypatch, capsys):
    """Prints 'No posts found.' when posts dir is empty or missing."""
    _setup_project(tmp_path, {"posts": {"dir": ".selfdoc/posts/"}})
    monkeypatch.chdir(tmp_path)
    _cmd_post_list()
    captured = capsys.readouterr()
    assert "No posts found" in captured.out


# ------------------------------------------------------------------
# Happy paths
# ------------------------------------------------------------------


def test_post_list_with_posts(tmp_path, monkeypatch, capsys):
    """Lists posts with date, title, slug, and count."""
    _setup_project(tmp_path, {"posts": {"dir": ".selfdoc/posts/"}})
    posts_dir = str(tmp_path / ".selfdoc" / "posts")
    _write_post(posts_dir, "a.md", ["title: First Post", "date: 2025-01-15"])
    _write_post(posts_dir, "b.md", ["title: Second Post", "date: 2025-03-20"])
    monkeypatch.chdir(tmp_path)
    _cmd_post_list()
    captured = capsys.readouterr()
    assert "First Post" in captured.out
    assert "Second Post" in captured.out
    assert "2 post(s) found" in captured.out


def test_post_list_drafts_marked(tmp_path, monkeypatch, capsys):
    """Draft posts show [DRAFT] marker."""
    _setup_project(tmp_path, {"posts": {"dir": ".selfdoc/posts/"}})
    posts_dir = str(tmp_path / ".selfdoc" / "posts")
    _write_post(posts_dir, "a.md", ["title: Draft Post", "date: 2025-01-15", "draft: true"])
    monkeypatch.chdir(tmp_path)
    _cmd_post_list()
    captured = capsys.readouterr()
    assert "[DRAFT]" in captured.out


def test_post_list_non_draft_no_marker(tmp_path, monkeypatch, capsys):
    """Non-draft posts do not show [DRAFT] marker."""
    _setup_project(tmp_path, {"posts": {"dir": ".selfdoc/posts/"}})
    posts_dir = str(tmp_path / ".selfdoc" / "posts")
    _write_post(posts_dir, "a.md", ["title: Published Post", "date: 2025-01-15"])
    monkeypatch.chdir(tmp_path)
    _cmd_post_list()
    captured = capsys.readouterr()
    assert "[DRAFT]" not in captured.out
    assert "Published Post" in captured.out


def test_post_list_sorted_newest_first(tmp_path, monkeypatch, capsys):
    """Output is sorted with newest posts first."""
    _setup_project(tmp_path, {"posts": {"dir": ".selfdoc/posts/"}})
    posts_dir = str(tmp_path / ".selfdoc" / "posts")
    _write_post(posts_dir, "old.md", ["title: Old", "date: 2024-06-01"])
    _write_post(posts_dir, "new.md", ["title: New", "date: 2025-07-01"])
    _write_post(posts_dir, "mid.md", ["title: Mid", "date: 2025-01-01"])
    monkeypatch.chdir(tmp_path)
    _cmd_post_list()
    captured = capsys.readouterr()
    lines = [l for l in captured.out.strip().split("\n") if l and "post(s)" not in l]
    # New should be first, Old last
    assert "2025-07-01" in lines[0]
    assert "2024-06-01" in lines[2]


def test_post_list_shows_slug(tmp_path, monkeypatch, capsys):
    """Output includes the slug in parentheses."""
    _setup_project(tmp_path, {"posts": {"dir": ".selfdoc/posts/"}})
    posts_dir = str(tmp_path / ".selfdoc" / "posts")
    _write_post(posts_dir, "a.md", ["title: My Great Post", "date: 2025-01-15", "slug: custom-slug"])
    monkeypatch.chdir(tmp_path)
    _cmd_post_list()
    captured = capsys.readouterr()
    assert "(custom-slug)" in captured.out


def test_post_list_default_posts_dir(tmp_path, monkeypatch, capsys):
    """Uses default .selfdoc/posts/ when no posts config is present."""
    _setup_project(tmp_path)  # No posts config override
    posts_dir = str(tmp_path / ".selfdoc" / "posts")
    _write_post(posts_dir, "a.md", ["title: Default Dir", "date: 2025-02-01"])
    monkeypatch.chdir(tmp_path)
    _cmd_post_list()
    captured = capsys.readouterr()
    assert "Default Dir" in captured.out
    assert "1 post(s) found" in captured.out
