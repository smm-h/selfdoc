"""An authored page may never sit where the build writes its own.

The build injects its post pages into the docs tree -- ``blog/<slug>.md``
plus the listing at ``blog.md`` -- builds them, and then deletes what it
injected.  An author's own ``docs/blog.md`` was destroyed by that sequence:
injection overwrote it, the reserved-path refusal ran afterwards and only
looked at the versioned/unversioned partitions (which exclude every
site-level path by construction), and cleanup then removed the file.  The
refusal now runs against the tree as the author committed it, before
anything writes into it.
"""

import json
import os

import pytest

from selfdoc.build import build
from conftest import default_config


def _project(tmp_path, *, posts=(), authored=()):
    """A minimal project with *posts* and *authored* docs pages.

    *posts* are ``(filename, content)`` under ``.selfdoc/posts/``;
    *authored* are ``(docs-relative path, content)`` under ``docs/``.
    """
    config = default_config(docs="docs/", output="docs/_build/")
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

    for rel, content in authored:
        path = os.path.join(docs_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    if posts:
        posts_dir = os.path.join(tmp_path, ".selfdoc", "posts")
        os.makedirs(posts_dir, exist_ok=True)
        for filename, content in posts:
            with open(os.path.join(posts_dir, filename), "w") as f:
                f.write(content)

    return str(tmp_path)


_POST = (
    "hello.md",
    "---\ntitle: Hello World\ndate: 2024-01-15\nslug: hello-world\n"
    "directives: false\n"
    "tags: []\ndraft: false\n---\nPost body.\n",
)

_AUTHORED_BLOG = "---\ntitle: My Blog\n---\n\n# My Blog\n\nHand-written.\n"


def test_authored_blog_page_refused_and_untouched(tmp_path):
    """A committed ``docs/blog.md`` stops the build and survives it.

    The audit's repro: build a project that has both posts and an authored
    blog page.  Before the refusal moved ahead of injection, the build
    succeeded and left the authored file deleted from the working tree.
    """
    project = _project(
        tmp_path, posts=[_POST], authored=[("blog.md", _AUTHORED_BLOG)],
    )
    authored = os.path.join(project, "docs", "blog.md")
    before = open(authored, "rb").read()

    with pytest.raises(RuntimeError, match="blog.md"):
        build(project)

    assert os.path.isfile(authored), "the authored page was deleted"
    assert open(authored, "rb").read() == before


def test_authored_blog_page_refused_without_posts(tmp_path):
    """The refusal does not depend on the project having posts.

    ``blog`` is the build's segment whether or not this build injects
    anything into it, so an authored page there is refused either way --
    otherwise adding the first post would silently destroy the page.
    """
    project = _project(tmp_path, authored=[("blog.md", _AUTHORED_BLOG)])
    authored = os.path.join(project, "docs", "blog.md")

    with pytest.raises(RuntimeError, match="blog.md"):
        build(project)

    assert os.path.isfile(authored)


def test_authored_page_under_blog_dir_refused(tmp_path):
    """A page under ``docs/blog/`` is refused too.

    Injection writes ``blog/<slug>.md``, so an authored page there is one
    matching post slug away from being overwritten and then deleted.
    """
    project = _project(
        tmp_path, posts=[_POST],
        authored=[("blog/notes.md", "# Notes\n\nHand-written.\n")],
    )
    authored = os.path.join(project, "docs", "blog", "notes.md")

    with pytest.raises(RuntimeError, match="blog/notes.md"):
        build(project)

    assert os.path.isfile(authored)


def test_authored_page_under_archive_prefix_refused(tmp_path):
    """A page under ``docs/v/`` is refused: that is the archive tree."""
    project = _project(
        tmp_path, authored=[("v/old.md", "# Old\n\nHand-written.\n")],
    )

    with pytest.raises(RuntimeError, match="v/old.md"):
        build(project)


def test_ordinary_project_still_builds(tmp_path):
    """A project with posts and no authored reserved page is unaffected."""
    project = _project(tmp_path, posts=[_POST])

    written = build(project)

    assert any(
        "blog" in path and path.endswith("index.html") for path in written
    )
    # The injected pages are cleaned up, and no authored file is left behind.
    assert not os.path.isfile(os.path.join(project, "docs", "blog.md"))
    assert not os.path.isdir(os.path.join(project, "docs", "blog"))
