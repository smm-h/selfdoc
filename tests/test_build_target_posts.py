"""Tests for build(target='posts') -- posts-only build mode."""

from __future__ import annotations

import json
import os

import pytest

from selfdoc.build import build
from conftest import default_config


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

_POST_SECOND = (
    "second.md",
    "---\ntitle: Second Post\ndate: 2024-02-01\nslug: second-post\n"
    "tags: []\ndraft: false\n---\nSecond post body.\n",
)

_POST_WITH_DIRECTIVE = (
    "directive.md",
    "---\ntitle: Directive Post\ndate: 2024-03-01\nslug: directive-post\n"
    "tags: []\ndraft: false\n---\n# Directive Post\n\n"
    ":-: ref path=\"mymod\"\n",
)


# -- Tests -----------------------------------------------------------------


def test_target_posts_produces_html_for_posts(tmp_path):
    """target=posts produces HTML output for post pages."""
    project = _setup_project_with_posts(tmp_path, posts=[_POST_HELLO])

    written = build(str(project), target="posts")

    assert len(written) > 0

    # Post HTML should exist in the output
    output_dir = os.path.join(project, "docs", "_build")
    post_html = os.path.join(output_dir, "posts", "hello-world", "index.html")
    assert post_html in written
    assert os.path.isfile(post_html)

    content = open(post_html).read()
    assert "Hello World" in content


def test_target_posts_no_versioned_doc_pages(tmp_path):
    """target=posts does not produce versioned doc pages (e.g. en/1.0.0/index.html)."""
    project = _setup_project_with_posts(tmp_path, posts=[_POST_HELLO])

    written = build(str(project), target="posts")

    output_dir = os.path.join(project, "docs", "_build")

    # The versioned path should NOT exist
    versioned_index = os.path.join(output_dir, "en", "1.0.0", "index.html")
    assert versioned_index not in written
    assert not os.path.isfile(versioned_index)


def test_target_posts_no_posts_empty_output(tmp_path):
    """target=posts with no posts directory produces empty output."""
    project = _setup_project_with_posts(tmp_path, posts=None)

    written = build(str(project), target="posts")

    assert written == {}


def test_target_posts_resolves_directives(tmp_path):
    """target=posts still resolves directives in post content."""
    project = _setup_project_with_posts(
        tmp_path, posts=[_POST_WITH_DIRECTIVE],
    )

    written = build(str(project), target="posts")

    output_dir = os.path.join(project, "docs", "_build")
    post_html = os.path.join(
        output_dir, "posts", "directive-post", "index.html",
    )
    assert post_html in written
    assert os.path.isfile(post_html)

    content = open(post_html).read()
    # The directive should have been resolved (producing either the
    # referenced content or an error message for a missing module).
    # Either way, the raw directive marker should not appear in HTML.
    assert ":-:" not in content


def test_target_posts_skips_auxiliary_files(tmp_path):
    """target=posts does not produce sitemap.xml, feed.xml, or style.css."""
    project = _setup_project_with_posts(tmp_path, posts=[_POST_HELLO])

    written = build(str(project), target="posts")

    output_dir = os.path.join(project, "docs", "_build")

    assert not os.path.isfile(os.path.join(output_dir, "sitemap.xml"))
    assert not os.path.isfile(os.path.join(output_dir, "feed.xml"))
    assert not os.path.isfile(os.path.join(output_dir, "style.css"))
    assert not os.path.isfile(os.path.join(output_dir, "search-index.json"))
    assert not os.path.isfile(os.path.join(output_dir, "index.html"))


def test_target_posts_cleans_up_injected_files(tmp_path):
    """target=posts cleans up injected post files from docs/ after building."""
    project = _setup_project_with_posts(tmp_path, posts=[_POST_HELLO])

    build(str(project), target="posts")

    # The injected files under docs/posts/ should be cleaned up
    docs_posts = os.path.join(project, "docs", "posts")
    assert not os.path.isdir(docs_posts) or not os.listdir(docs_posts)


def test_target_posts_multiple_posts(tmp_path):
    """target=posts produces HTML for all posts."""
    project = _setup_project_with_posts(
        tmp_path, posts=[_POST_HELLO, _POST_SECOND],
    )

    written = build(str(project), target="posts")

    output_dir = os.path.join(project, "docs", "_build")
    hello_html = os.path.join(
        output_dir, "posts", "hello-world", "index.html",
    )
    second_html = os.path.join(
        output_dir, "posts", "second-post", "index.html",
    )
    assert hello_html in written
    assert second_html in written
