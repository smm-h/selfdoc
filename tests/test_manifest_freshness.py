"""Tests for STALE002 manifest freshness check."""

import json
import os

import pytest

from selfdoc.check import _check_manifest_freshness


def _write_manifest(path, pages, posts=None):
    data = {
        "schema_version": 1,
        "name": "test",
        "slug": "test",
        "version": "1.0.0",
        "description": "",
        "language": "python",
        "base_url": "",
        "pages": pages,
        "posts": posts or [],
        "last_gen": "",
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def test_stale002_no_manifest(tmp_path):
    """No manifest file -- empty results."""
    config = {"docs": "docs/"}
    result = _check_manifest_freshness(config, str(tmp_path))
    assert result == []


def test_stale002_all_in_sync(tmp_path):
    """Pages and posts on disk match manifest -- empty results."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Index")
    (docs_dir / "guide.md").write_text("# Guide")

    posts_dir = tmp_path / ".selfdoc" / "posts"
    posts_dir.mkdir(parents=True)
    (posts_dir / "hello.md").write_text("# Hello")

    manifest_path = tmp_path / ".selfdoc" / "manifest.json"
    _write_manifest(
        str(manifest_path),
        pages=[
            {"path": "index.md", "title": "Index", "type": "doc"},
            {"path": "guide.md", "title": "Guide", "type": "doc"},
        ],
        posts=[
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello", "tags": []},
        ],
    )

    config = {"docs": "docs/", "posts": {"dir": ".selfdoc/posts/"}}
    result = _check_manifest_freshness(config, str(tmp_path))
    assert result == []


def test_stale002_page_on_disk_not_in_manifest(tmp_path):
    """New page on disk not in manifest -- STALE002."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Index")
    (docs_dir / "new-page.md").write_text("# New")

    manifest_path = tmp_path / ".selfdoc" / "manifest.json"
    _write_manifest(
        str(manifest_path),
        pages=[{"path": "index.md", "title": "Index", "type": "doc"}],
    )

    config = {"docs": "docs/"}
    result = _check_manifest_freshness(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "STALE002"
    assert "new-page.md" in result[0].message or result[0].file == "new-page.md"
    assert "not in manifest" in result[0].message


def test_stale002_manifest_page_missing_from_disk(tmp_path):
    """Manifest lists page that doesn't exist on disk -- STALE002."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Index")

    manifest_path = tmp_path / ".selfdoc" / "manifest.json"
    _write_manifest(
        str(manifest_path),
        pages=[
            {"path": "index.md", "title": "Index", "type": "doc"},
            {"path": "deleted.md", "title": "Deleted", "type": "doc"},
        ],
    )

    config = {"docs": "docs/"}
    result = _check_manifest_freshness(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "STALE002"
    assert "deleted.md" in result[0].message
    assert "not found on disk" in result[0].message


def test_stale002_post_on_disk_not_in_manifest(tmp_path):
    """New post on disk not in manifest -- STALE002."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    posts_dir = tmp_path / ".selfdoc" / "posts"
    posts_dir.mkdir(parents=True)
    (posts_dir / "new-post.md").write_text("# New Post")

    manifest_path = tmp_path / ".selfdoc" / "manifest.json"
    _write_manifest(str(manifest_path), pages=[], posts=[])

    config = {"docs": "docs/", "posts": {"dir": ".selfdoc/posts/"}}
    result = _check_manifest_freshness(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "STALE002"
    assert "post" in result[0].message
    assert "not in manifest" in result[0].message


def test_stale002_manifest_post_missing_from_disk(tmp_path):
    """Manifest lists post that doesn't exist on disk -- STALE002."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    posts_dir = tmp_path / ".selfdoc" / "posts"
    posts_dir.mkdir(parents=True)

    manifest_path = tmp_path / ".selfdoc" / "manifest.json"
    _write_manifest(
        str(manifest_path),
        pages=[],
        posts=[
            {"path": "gone.md", "title": "Gone", "date": "2025-01-01",
             "slug": "gone", "tags": []},
        ],
    )

    config = {"docs": "docs/", "posts": {"dir": ".selfdoc/posts/"}}
    result = _check_manifest_freshness(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "STALE002"
    assert "gone.md" in result[0].message
    assert "not found on disk" in result[0].message


def test_stale002_ignores_underscore_templates(tmp_path):
    """Template files like _README.md are ignored -- empty results."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Index")
    (docs_dir / "_README.md").write_text("# Template")
    (docs_dir / "_CLAUDE.md").write_text("# Template")

    manifest_path = tmp_path / ".selfdoc" / "manifest.json"
    _write_manifest(
        str(manifest_path),
        pages=[{"path": "index.md", "title": "Index", "type": "doc"}],
    )

    config = {"docs": "docs/"}
    result = _check_manifest_freshness(config, str(tmp_path))
    assert result == []
