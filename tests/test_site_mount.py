"""What changes when a project is built under a shared site's mount.

A project declaring ``topology.docs_base`` + ``topology.slug`` is not
served from its own output root: the site serves it under its slug, and
serves the site-level pages -- the posts -- from the site root at
``blog/<post-slug>/``.  Two roots, two different directories, and the
build has to address both correctly:

* No ``404.html``.  The provider answers an unmatched address from the
  root of what it serves, so a copy buried under ``site/<slug>/`` is
  never reached.
* Post addresses are site-level.  A post's canonical, its sitemap and
  feed entries, and every link a project page writes to it name
  ``<docs_base>/blog/<post-slug>/`` -- not the project's subtree, where
  the assembly does not put it.

A project with no mount keeps a self-contained blog: it IS its own site,
so its posts are its own and relative hops reach them.
"""

from __future__ import annotations

import json
import os
import re

import pytest

from selfdoc.build import build
from conftest import default_config


DOCS_BASE = "https://docs.example.com"
SLUG = "alpha"

_POST = (
    "hello.md",
    "---\ntitle: Hello World\ndate: 2024-01-15\nslug: hello-world\n"
    "tags: [release]\ndraft: false\ndirectives: false\n---\n"
    "This is the post content.\n",
)


def _project(tmp_path, *, mounted, with_post=True):
    """A minimal project, with or without a site mount."""
    overrides = {}
    if mounted:
        overrides["topology"] = {"docs_base": DOCS_BASE, "slug": SLUG}
    config = default_config(docs="docs/", output="docs/_build/", **overrides)
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
    with open(os.path.join(docs_dir, "guide.md"), "w") as f:
        f.write("# Guide\n\nHow to.\n")

    if with_post:
        posts_dir = os.path.join(tmp_path, ".selfdoc", "posts")
        os.makedirs(posts_dir, exist_ok=True)
        name, content = _POST
        with open(os.path.join(posts_dir, name), "w") as f:
            f.write(content)
    return str(tmp_path)


def _out(project, *parts):
    return os.path.join(project, "docs", "_build", *parts)


def _read(project, *parts):
    with open(_out(project, *parts), encoding="utf-8") as f:
        return f.read()


def _canonical(html):
    match = re.search(r'<link rel="canonical" href="([^"]*)"', html)
    return match.group(1) if match else None


def _hrefs(html):
    return re.findall(r'href="([^"]*)"', html)


@pytest.fixture()
def mounted(tmp_path):
    project = _project(tmp_path / "mounted", mounted=True)
    build(project)
    return project


@pytest.fixture()
def standalone(tmp_path):
    project = _project(tmp_path / "standalone", mounted=False)
    build(project)
    return project


@pytest.fixture(autouse=True)
def _dirs(tmp_path):
    (tmp_path / "mounted").mkdir(exist_ok=True)
    (tmp_path / "standalone").mkdir(exist_ok=True)


# -- the not-found page --------------------------------------------------------


def test_a_mounted_build_writes_no_404(mounted):
    """It would be unreachable: only the served root's 404 is ever asked."""
    assert not os.path.exists(_out(mounted, "404.html"))


def test_a_standalone_build_still_writes_its_404(standalone):
    """Its output root IS the served root, so its 404 is the one answered."""
    assert os.path.isfile(_out(standalone, "404.html"))


# -- post addresses ------------------------------------------------------------


def test_a_mounted_posts_canonical_is_the_site_blog_address(mounted):
    html = _read(mounted, "blog", "hello-world", "index.html")
    assert _canonical(html) == f"{DOCS_BASE}/blog/hello-world/"


def test_a_standalone_posts_canonical_is_its_own_blog_address(standalone):
    html = _read(standalone, "blog", "hello-world", "index.html")
    assert _canonical(html) == "https://example.com/blog/hello-world/"


def test_a_mounted_project_page_links_the_post_at_the_site_address(mounted):
    """The link has to cross out of the project's subtree, so it is absolute.

    A relative hop resolves inside ``site/<slug>/``, where the assembly
    does not put posts -- that is the dead reference this fixes.
    """
    html = _read(mounted, "guide", "index.html")
    assert f"{DOCS_BASE}/blog/hello-world/" in _hrefs(html)
    assert not [h for h in _hrefs(html) if h.endswith("../blog/hello-world/")]


def test_a_mounted_project_page_links_the_blog_index_at_the_site_address(mounted):
    html = _read(mounted, "guide", "index.html")
    assert f"{DOCS_BASE}/blog/" in _hrefs(html)


def test_a_standalone_project_page_links_the_post_relatively(standalone):
    """No mount, so the project's own output root serves the post too."""
    html = _read(standalone, "guide", "index.html")
    assert "../blog/hello-world/" in _hrefs(html)


def test_a_mounted_sitemap_lists_the_post_at_the_site_address(mounted):
    sitemap = _read(mounted, "sitemap.xml")
    assert f"<loc>{DOCS_BASE}/blog/hello-world/</loc>" in sitemap
    assert f"{DOCS_BASE}/{SLUG}/blog/" not in sitemap


def test_a_mounted_feed_links_the_post_at_the_site_address(mounted):
    feed = _read(mounted, "feed.xml")
    assert f"{DOCS_BASE}/blog/hello-world/" in feed
    assert f"{DOCS_BASE}/{SLUG}/blog/" not in feed


def test_the_project_pages_keep_the_slug(mounted):
    """Only the site-level pages are mountless; documentation is not."""
    html = _read(mounted, "guide", "index.html")
    assert _canonical(html) == f"{DOCS_BASE}/{SLUG}/guide/"
    sitemap = _read(mounted, "sitemap.xml")
    assert f"<loc>{DOCS_BASE}/{SLUG}/guide/</loc>" in sitemap
