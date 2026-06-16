"""Tests for posts in the build pipeline -- injection, cleanup, and full builds."""

from __future__ import annotations

import json
import os

import pytest

from selfdoc.build import build, _inject_posts_into_docs, _cleanup_injected_posts
from selfdoc.config import load_config
from conftest import default_config, DEFAULT_PREFIX


# -- Helpers ---------------------------------------------------------------


def _setup_project_with_posts(tmp_path, posts=None, config_overrides=None):
    """Create a minimal selfdoc project with optional posts.

    Posts are written to ``.selfdoc/posts/`` (the default posts directory).
    Each entry in *posts* is ``(filename, content)`` where *content* is the
    full markdown including frontmatter fences.
    """
    config = default_config(docs="docs/", output="docs/_build/")
    if config_overrides:
        config.update(config_overrides)

    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(src_dir, "__init__.py"), "w") as f:
        f.write('"""Example package."""\n')

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    with open(os.path.join(docs_dir, "index.md"), "w") as f:
        f.write("# Test Project\n\nWelcome.\n")

    if posts:
        posts_dir = os.path.join(tmp_path, ".selfdoc", "posts")
        os.makedirs(posts_dir, exist_ok=True)
        for filename, content in posts:
            path = os.path.join(posts_dir, filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)

    return tmp_path


_POST_HELLO = (
    "hello.md",
    "---\ntitle: Hello World\ndate: 2024-01-15\nslug: hello-world\n"
    "tags: [release]\ndraft: false\n---\nThis is the post content.\n",
)

_POST_DRAFT = (
    "draft.md",
    "---\ntitle: Draft Post\ndate: 2024-01-16\nslug: draft-post\n"
    "tags: []\ndraft: true\n---\nDraft content here.\n",
)


# -- Unit tests: _inject_posts_into_docs -----------------------------------


def test_inject_posts_no_posts_dir(tmp_path):
    """When no posts directory exists, return an empty list."""
    project = _setup_project_with_posts(tmp_path)
    config = load_config(str(project))
    docs_dir = os.path.join(project, "docs")

    result = _inject_posts_into_docs(str(project), config, docs_dir, False)

    assert result == []


def test_inject_posts_basic(tmp_path):
    """A non-draft post is injected into docs/posts/."""
    project = _setup_project_with_posts(tmp_path, posts=[_POST_HELLO])
    config = load_config(str(project))
    docs_dir = os.path.join(project, "docs")

    injected = _inject_posts_into_docs(str(project), config, docs_dir, False)

    assert len(injected) == 1
    expected_path = os.path.join(docs_dir, "posts", "hello-world.md")
    assert injected[0] == expected_path
    assert os.path.isfile(expected_path)

    content = open(expected_path).read()
    assert "Hello World" in content
    assert "This is the post content." in content


def test_inject_posts_draft_excluded(tmp_path):
    """Draft posts are excluded when include_drafts is False."""
    project = _setup_project_with_posts(
        tmp_path, posts=[_POST_HELLO, _POST_DRAFT],
    )
    config = load_config(str(project))
    docs_dir = os.path.join(project, "docs")

    injected = _inject_posts_into_docs(str(project), config, docs_dir, False)

    slugs = [os.path.basename(p) for p in injected]
    assert "hello-world.md" in slugs
    assert "draft-post.md" not in slugs
    assert not os.path.isfile(os.path.join(docs_dir, "posts", "draft-post.md"))


def test_inject_posts_draft_included(tmp_path):
    """Draft posts are included when include_drafts is True."""
    project = _setup_project_with_posts(
        tmp_path, posts=[_POST_HELLO, _POST_DRAFT],
    )
    config = load_config(str(project))
    docs_dir = os.path.join(project, "docs")

    injected = _inject_posts_into_docs(str(project), config, docs_dir, True)

    slugs = [os.path.basename(p) for p in injected]
    assert "hello-world.md" in slugs
    assert "draft-post.md" in slugs
    assert os.path.isfile(os.path.join(docs_dir, "posts", "draft-post.md"))


# -- Unit tests: _cleanup_injected_posts -----------------------------------


def test_cleanup_injected_posts(tmp_path):
    """Cleanup removes injected files and empty posts/ directory."""
    docs_dir = os.path.join(tmp_path, "docs")
    posts_dir = os.path.join(docs_dir, "posts")
    os.makedirs(posts_dir, exist_ok=True)

    # Create two fake injected files
    file_a = os.path.join(posts_dir, "a.md")
    file_b = os.path.join(posts_dir, "b.md")
    for path in (file_a, file_b):
        with open(path, "w") as f:
            f.write("placeholder")

    _cleanup_injected_posts([file_a, file_b], docs_dir)

    assert not os.path.isfile(file_a)
    assert not os.path.isfile(file_b)
    assert not os.path.isdir(posts_dir)


def test_cleanup_preserves_nonempty_dir(tmp_path):
    """Cleanup does not remove posts/ if other files remain."""
    docs_dir = os.path.join(tmp_path, "docs")
    posts_dir = os.path.join(docs_dir, "posts")
    os.makedirs(posts_dir, exist_ok=True)

    injected = os.path.join(posts_dir, "injected.md")
    other = os.path.join(posts_dir, "other.md")
    for path in (injected, other):
        with open(path, "w") as f:
            f.write("placeholder")

    _cleanup_injected_posts([injected], docs_dir)

    assert not os.path.isfile(injected)
    assert os.path.isfile(other)
    assert os.path.isdir(posts_dir)


# -- Integration tests: full build with posts ------------------------------


def test_build_with_posts(tmp_path):
    """Full build produces HTML for posts."""
    project = _setup_project_with_posts(tmp_path, posts=[_POST_HELLO])

    written = build(str(project))

    # Post output should exist
    output_dir = os.path.join(project, "docs", "_build")
    post_html = os.path.join(output_dir, "en", "posts", "hello-world", "index.html")
    assert post_html in written
    assert os.path.isfile(post_html)

    # HTML should contain the post title
    content = open(post_html).read()
    assert "Hello World" in content


def test_build_posts_in_output_path(tmp_path):
    """Post output lands at en/posts/<slug>/index.html."""
    project = _setup_project_with_posts(tmp_path, posts=[_POST_HELLO])

    written = build(str(project))

    output_dir = os.path.join(project, "docs", "_build")
    expected = os.path.join(output_dir, "en", "posts", "hello-world", "index.html")
    assert expected in written


def test_build_posts_search_index(tmp_path):
    """Posts appear in the search index."""
    # The search index only indexes heading-delimited sections, so the post
    # body must contain at least one markdown heading to produce an entry.
    post_with_heading = (
        "hello.md",
        "---\ntitle: Hello World\ndate: 2024-01-15\nslug: hello-world\n"
        "tags: [release]\ndraft: false\n---\n# Hello World\n\n"
        "This is the post content.\n",
    )
    project = _setup_project_with_posts(tmp_path, posts=[post_with_heading])

    build(str(project))

    search_index_path = os.path.join(
        project, "docs", "_build", "search-index.json",
    )
    assert os.path.isfile(search_index_path)

    with open(search_index_path) as f:
        entries = json.load(f)

    # At least one entry should reference the post
    post_entries = [
        e for e in entries
        if "hello-world" in e.get("path", "") or "Hello World" in e.get("title", "")
    ]
    assert len(post_entries) > 0


def test_build_posts_draft_excluded_by_default(tmp_path):
    """Drafts are not in build output when include_drafts is False (default)."""
    project = _setup_project_with_posts(
        tmp_path, posts=[_POST_HELLO, _POST_DRAFT],
    )

    written = build(str(project))

    output_dir = os.path.join(project, "docs", "_build")
    draft_html = os.path.join(
        output_dir, "en", "posts", "draft-post", "index.html",
    )
    assert draft_html not in written
    assert not os.path.isfile(draft_html)

    # Non-draft should still be present
    hello_html = os.path.join(
        output_dir, "en", "posts", "hello-world", "index.html",
    )
    assert hello_html in written


def test_build_posts_draft_included(tmp_path):
    """Drafts are in build output when include_drafts is True."""
    project = _setup_project_with_posts(
        tmp_path, posts=[_POST_HELLO, _POST_DRAFT],
    )

    written = build(str(project), include_drafts=True)

    output_dir = os.path.join(project, "docs", "_build")
    draft_html = os.path.join(
        output_dir, "en", "posts", "draft-post", "index.html",
    )
    assert draft_html in written
    assert os.path.isfile(draft_html)


def test_build_posts_cleanup(tmp_path):
    """After build(), injected files in docs/posts/ are cleaned up."""
    project = _setup_project_with_posts(tmp_path, posts=[_POST_HELLO])

    written = build(str(project))

    # The output must contain the post
    output_dir = os.path.join(project, "docs", "_build")
    post_html = os.path.join(output_dir, "en", "posts", "hello-world", "index.html")
    assert post_html in written

    # But docs/posts/ should have been cleaned up
    docs_posts = os.path.join(project, "docs", "posts")
    assert not os.path.isdir(docs_posts)
