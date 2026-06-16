"""Tests for selfdoc.posts -- post discovery and validation."""

from __future__ import annotations

import json
import os

import pytest

from selfdoc.posts import discover_posts


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


# ------------------------------------------------------------------
# Basic discovery
# ------------------------------------------------------------------


def test_discover_posts_empty_dir(tmp_path):
    posts_dir = tmp_path / "posts"
    posts_dir.mkdir()
    result = discover_posts(str(posts_dir))
    assert result == []


def test_discover_posts_nonexistent_dir(tmp_path):
    result = discover_posts(str(tmp_path / "does-not-exist"))
    assert result == []


def test_discover_posts_basic(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(
        str(posts_dir),
        "hello.md",
        ["title: Hello World", "date: 2025-01-15"],
        body="Some body text.",
    )
    result = discover_posts(str(posts_dir))
    assert len(result) == 1
    post = result[0]
    assert post["path"] == "hello.md"
    assert post["title"] == "Hello World"
    assert post["date"] == "2025-01-15"
    assert post["slug"] == "hello-world"
    assert post["tags"] == []
    assert post["draft"] is False
    assert post["type"] == "post"
    assert post["versioned"] is False
    assert post["content"] == "Some body text."


# ------------------------------------------------------------------
# Sorting
# ------------------------------------------------------------------


def test_discover_posts_multiple_sorted(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(str(posts_dir), "old.md", ["title: Old", "date: 2024-06-01"])
    _write_post(str(posts_dir), "mid.md", ["title: Mid", "date: 2025-01-01"])
    _write_post(str(posts_dir), "new.md", ["title: New", "date: 2025-07-01"])

    result = discover_posts(str(posts_dir))
    dates = [p["date"] for p in result]
    assert dates == ["2025-07-01", "2025-01-01", "2024-06-01"]


def test_discover_posts_same_date_sorted_by_slug(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(str(posts_dir), "z.md", ["title: Zeta", "date: 2025-03-01"])
    _write_post(str(posts_dir), "a.md", ["title: Alpha", "date: 2025-03-01"])
    _write_post(str(posts_dir), "m.md", ["title: Mid", "date: 2025-03-01"])

    result = discover_posts(str(posts_dir))
    slugs = [p["slug"] for p in result]
    assert slugs == ["alpha", "mid", "zeta"]


# ------------------------------------------------------------------
# Slug handling
# ------------------------------------------------------------------


def test_discover_posts_auto_slug(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(
        str(posts_dir),
        "post.md",
        ["title: My Great Post!", "date: 2025-01-01"],
    )
    result = discover_posts(str(posts_dir))
    assert result[0]["slug"] == "my-great-post"


def test_discover_posts_explicit_slug(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(
        str(posts_dir),
        "post.md",
        ["title: My Post", "date: 2025-01-01", "slug: custom-slug"],
    )
    result = discover_posts(str(posts_dir))
    assert result[0]["slug"] == "custom-slug"


# ------------------------------------------------------------------
# Tags
# ------------------------------------------------------------------


def test_discover_posts_tags_default(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(str(posts_dir), "p.md", ["title: No Tags", "date: 2025-01-01"])
    result = discover_posts(str(posts_dir))
    assert result[0]["tags"] == []


def test_discover_posts_tags_from_frontmatter(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(
        str(posts_dir),
        "p.md",
        ["title: Tagged", "date: 2025-01-01", "tags: [python, testing, ci]"],
    )
    result = discover_posts(str(posts_dir))
    assert result[0]["tags"] == ["python", "testing", "ci"]


# ------------------------------------------------------------------
# Draft handling
# ------------------------------------------------------------------


def test_discover_posts_draft(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(
        str(posts_dir),
        "p.md",
        ["title: Draft Post", "date: 2025-01-01", "draft: true"],
    )
    result = discover_posts(str(posts_dir))
    assert result[0]["draft"] is True


def test_discover_posts_draft_default_false(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(str(posts_dir), "p.md", ["title: Normal", "date: 2025-01-01"])
    result = discover_posts(str(posts_dir))
    assert result[0]["draft"] is False


# ------------------------------------------------------------------
# Injected fields
# ------------------------------------------------------------------


def test_discover_posts_type_injected(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(str(posts_dir), "p.md", ["title: Typed", "date: 2025-01-01"])
    result = discover_posts(str(posts_dir))
    assert result[0]["type"] == "post"


def test_discover_posts_versioned_injected(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(str(posts_dir), "p.md", ["title: Unversioned", "date: 2025-01-01"])
    result = discover_posts(str(posts_dir))
    assert result[0]["versioned"] is False


# ------------------------------------------------------------------
# Validation errors
# ------------------------------------------------------------------


def test_discover_posts_missing_title(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(str(posts_dir), "p.md", ["date: 2025-01-01"])
    with pytest.raises(RuntimeError, match="'title' is required"):
        discover_posts(str(posts_dir))


def test_discover_posts_missing_date(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(str(posts_dir), "p.md", ["title: No Date"])
    with pytest.raises(RuntimeError, match="'date' is required"):
        discover_posts(str(posts_dir))


def test_discover_posts_invalid_date(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(
        str(posts_dir),
        "p.md",
        ["title: Bad Date", "date: Jan 15 2025"],
    )
    with pytest.raises(RuntimeError, match="must be YYYY-MM-DD"):
        discover_posts(str(posts_dir))


def test_discover_posts_duplicate_slugs(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(str(posts_dir), "a.md", ["title: Same", "date: 2025-01-01"])
    _write_post(str(posts_dir), "b.md", ["title: Same", "date: 2025-02-01"])
    with pytest.raises(RuntimeError, match="Duplicate slug"):
        discover_posts(str(posts_dir))


# ------------------------------------------------------------------
# Slug immutability (manifest)
# ------------------------------------------------------------------


def test_discover_posts_slug_immutability_ok(tmp_path):
    posts_dir = tmp_path / "posts"
    manifest_path = tmp_path / "manifest.json"
    _write_post(
        str(posts_dir),
        "hello.md",
        ["title: Hello", "date: 2025-01-01", "slug: hello"],
    )
    _write_manifest(
        str(manifest_path),
        [{"path": "hello.md", "slug": "hello"}],
    )
    result = discover_posts(str(posts_dir), manifest_path=str(manifest_path))
    assert len(result) == 1
    assert result[0]["slug"] == "hello"


def test_discover_posts_slug_immutability_violation(tmp_path):
    posts_dir = tmp_path / "posts"
    manifest_path = tmp_path / "manifest.json"
    _write_post(
        str(posts_dir),
        "hello.md",
        ["title: Hello", "date: 2025-01-01", "slug: hello-new"],
    )
    _write_manifest(
        str(manifest_path),
        [{"path": "hello.md", "slug": "hello-old"}],
    )
    with pytest.raises(RuntimeError, match="Slug immutability violation"):
        discover_posts(str(posts_dir), manifest_path=str(manifest_path))


def test_discover_posts_slug_immutability_no_manifest(tmp_path):
    posts_dir = tmp_path / "posts"
    manifest_path = tmp_path / "no-such-manifest.json"
    _write_post(
        str(posts_dir),
        "hello.md",
        ["title: Hello", "date: 2025-01-01", "slug: hello"],
    )
    # manifest_path points to a non-existent file; load_manifest returns None
    result = discover_posts(str(posts_dir), manifest_path=str(manifest_path))
    assert len(result) == 1


# ------------------------------------------------------------------
# Optional fields and content body
# ------------------------------------------------------------------


def test_discover_posts_optional_fields(tmp_path):
    posts_dir = tmp_path / "posts"
    _write_post(
        str(posts_dir),
        "release.md",
        [
            "title: Release Notes",
            "date: 2025-06-01",
            "locale: en",
            "project: mylib",
            "version: 2.0.0",
            "prev_version: 1.9.0",
            "bump_type: major",
            "release_url: https://github.com/org/repo/releases/v2.0.0",
            "registry_urls: [https://pypi.org/project/mylib/2.0.0]",
        ],
    )
    result = discover_posts(str(posts_dir))
    post = result[0]
    assert post["locale"] == "en"
    assert post["project"] == "mylib"
    assert post["version"] == "2.0.0"
    assert post["prev_version"] == "1.9.0"
    assert post["bump_type"] == "major"
    assert post["release_url"] == "https://github.com/org/repo/releases/v2.0.0"
    assert post["registry_urls"] == [
        "https://pypi.org/project/mylib/2.0.0",
    ]


def test_discover_posts_content_body(tmp_path):
    posts_dir = tmp_path / "posts"
    body = "First paragraph.\n\nSecond paragraph."
    _write_post(
        str(posts_dir),
        "p.md",
        ["title: With Body", "date: 2025-01-01"],
        body=body,
    )
    result = discover_posts(str(posts_dir))
    assert result[0]["content"] == body
