"""Tests for post lint rules (POST001-POST005) in selfdoc.check."""

from __future__ import annotations

import json
import os

import pytest

from selfdoc.check import _check_posts


def _write_post(posts_dir, filename, frontmatter_lines, body=""):
    path = os.path.join(posts_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = "---\n" + "\n".join(frontmatter_lines) + "\n---\n" + body
    with open(path, "w") as f:
        f.write(content)


def _write_manifest(path, posts):
    data = {
        "schema_version": 1,
        "name": "test",
        "slug": "test",
        "version": "1.0.0",
        "description": "",
        "language": "python",
        "base_url": "",
        "pages": [],
        "posts": posts,
        "last_gen": "",
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def test_post_check_no_posts_dir(tmp_path):
    """No posts dir configured -> empty results."""
    config = {}
    result = _check_posts(config, str(tmp_path))
    assert result == []


def test_post_check_valid_posts(tmp_path):
    """Valid posts -> empty results."""
    posts_dir = tmp_path / "blog"
    _write_post(
        str(posts_dir),
        "hello.md",
        ["title: Hello World", "date: 2025-01-15"],
        body="Some body text.",
    )
    config = {"posts": {"dir": "blog"}}
    result = _check_posts(config, str(tmp_path))
    assert result == []


def test_post_check_missing_date(tmp_path):
    """Post missing date -> POST001."""
    posts_dir = tmp_path / "blog"
    _write_post(str(posts_dir), "p.md", ["title: No Date"])
    config = {"posts": {"dir": "blog"}}
    result = _check_posts(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST001"
    assert result[0].severity == "error"
    assert "'date' is required" in result[0].message


def test_post_check_missing_title(tmp_path):
    """Post missing title -> POST002."""
    posts_dir = tmp_path / "blog"
    _write_post(str(posts_dir), "p.md", ["date: 2025-01-01"])
    config = {"posts": {"dir": "blog"}}
    result = _check_posts(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST002"
    assert result[0].severity == "error"
    assert "'title' is required" in result[0].message


def test_post_check_invalid_date(tmp_path):
    """Post with bad date format -> POST003."""
    posts_dir = tmp_path / "blog"
    _write_post(
        str(posts_dir),
        "p.md",
        ["title: Bad Date", "date: Jan 15 2025"],
    )
    config = {"posts": {"dir": "blog"}}
    result = _check_posts(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST003"
    assert result[0].severity == "error"
    assert "must be YYYY-MM-DD" in result[0].message


def test_post_check_duplicate_slug(tmp_path):
    """Two posts with same slug -> POST004."""
    posts_dir = tmp_path / "blog"
    _write_post(str(posts_dir), "a.md", ["title: Same", "date: 2025-01-01"])
    _write_post(str(posts_dir), "b.md", ["title: Same", "date: 2025-02-01"])
    config = {"posts": {"dir": "blog"}}
    result = _check_posts(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST004"
    assert result[0].severity == "error"
    assert "Duplicate slug" in result[0].message


def test_post_check_slug_immutability(tmp_path):
    """Slug changed from manifest -> POST005."""
    posts_dir = tmp_path / "blog"
    _write_post(
        str(posts_dir),
        "hello.md",
        ["title: Hello", "date: 2025-01-01", "slug: hello-new"],
    )
    manifest_dir = tmp_path / ".selfdoc"
    _write_manifest(
        str(manifest_dir / "manifest.json"),
        [{"path": "hello.md", "slug": "hello-old"}],
    )
    config = {"posts": {"dir": "blog"}}
    result = _check_posts(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST005"
    assert result[0].severity == "error"
    assert "Slug immutability violation" in result[0].message
