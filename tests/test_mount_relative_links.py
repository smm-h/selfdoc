"""No visible link may name the site's own origin.

A built tree has to resolve under any mount point: the production host, a
local preview served from ``127.0.0.1``, a mirror, a subdirectory.  An
``<a href>`` written as ``https://<canonical-base>/blog/x/`` resolves under
exactly one of those, and on every other one it silently navigates the
reader off the tree they are looking at and onto production.  That is not a
dead link -- it works, which is what makes it dangerous: a preview reads as
a preview until a click leaves it.

So the rule is structural rather than per-instance:

* every reference that decides where a *click* goes is document-relative,
  derived from the page's own address (:mod:`selfdoc_core.address`);
* only metadata stays absolute -- ``rel=canonical``, ``og:url``, JSON-LD,
  sitemap ``<loc>``, feed entries and the share control's copyable
  addresses, all of which name where the page lives in the world rather
  than where a click goes.

:func:`~selfdoc_core.resolution.check_output_resolution` enforces it as
``LINK001``, beside the origin-absolute (``/path``) rule it already carried
for the same reason.
"""

from __future__ import annotations

import json
import os
import re

import pytest

from selfdoc.build import build
from selfdoc_core.resolution import check_output_resolution

from conftest import default_config


BASE = "https://example.com"
DOCS_BASE = "https://docs.example.com"
SLUG = "alpha"

_ANCHOR_RE = re.compile(r'<a\b[^>]*?\bhref="([^"]*)"', re.IGNORECASE)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def anchor_hrefs(page_html):
    """Every href a click can follow on this page."""
    return _ANCHOR_RE.findall(page_html)


def absolute_anchors(tree_dir, base):
    """``(page, href)`` for every visible link naming *base* under *tree_dir*."""
    found = []
    for dirpath, _dirs, files in os.walk(tree_dir):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            page = os.path.join(dirpath, name)
            with open(page, encoding="utf-8") as f:
                page_html = f.read()
            rel = os.path.relpath(page, tree_dir).replace(os.sep, "/")
            found.extend(
                (rel, href)
                for href in anchor_hrefs(page_html)
                if href.startswith(base)
            )
    return found


# -- the walker-level rule ------------------------------------------------------


def test_an_absolute_anchor_into_this_site_is_reported(tmp_path):
    """The whole class, seen by the walker rather than by a spot check."""
    out = str(tmp_path / "out")
    _write(
        os.path.join(out, "index.html"),
        f'<a href="{BASE}/blog/hello/">Hello</a>',
    )
    _write(os.path.join(out, "blog", "hello", "index.html"), "<p>hi</p>")

    lints = check_output_resolution(out, base_url=BASE)

    assert [lint.code for lint in lints] == ["LINK001"]
    assert "absolute" in lints[0].message
    assert f"{BASE}/blog/hello/" in lints[0].message


def test_an_absolute_anchor_is_reported_even_though_the_page_exists(tmp_path):
    """It is not a dangling reference -- it resolves, on one host only.

    The file the URL names is right there in the tree, which is exactly
    why the file-existence half of the check never saw this class.
    """
    out = str(tmp_path / "out")
    _write(os.path.join(out, "index.html"), f'<a href="{BASE}/guide/">G</a>')
    _write(os.path.join(out, "guide", "index.html"), "<p>guide</p>")

    assert [lint.code for lint in check_output_resolution(out, base_url=BASE)] \
        == ["LINK001"]


def test_an_anchor_to_somebody_elses_site_is_left_alone(tmp_path):
    out = str(tmp_path / "out")
    _write(
        os.path.join(out, "index.html"),
        '<a href="https://github.com/owner/repo">Repository</a>',
    )
    assert check_output_resolution(out, base_url=BASE) == []


def test_absolute_metadata_is_not_a_visible_link(tmp_path):
    """Canonical, share address and feed entry name a place in the world."""
    out = str(tmp_path / "out")
    _write(os.path.join(out, "index.html"), (
        f'<link rel="canonical" href="{BASE}/">'
        f'<button data-share-url="{BASE}/">Copy</button>'
    ))
    assert check_output_resolution(out, base_url=BASE) == []


def test_a_relative_anchor_to_the_same_page_is_fine(tmp_path):
    out = str(tmp_path / "out")
    _write(os.path.join(out, "index.html"), '<a href="guide/">Guide</a>')
    _write(os.path.join(out, "guide", "index.html"), "<p>guide</p>")
    assert check_output_resolution(out, base_url=BASE) == []


# -- a real mounted build ------------------------------------------------------


def _mounted_project(root):
    """A project served under ``<docs_base>/alpha/``, with a post."""
    os.makedirs(root, exist_ok=True)
    config = default_config(
        docs="docs/", output="docs/_build/",
        base_url=f"{DOCS_BASE}/{SLUG}",
        topology={"docs_base": DOCS_BASE, "slug": SLUG},
    )
    _write(os.path.join(root, "selfdoc.json"), json.dumps(config))
    _write(os.path.join(root, "src", "__init__.py"), '"""Example package."""\n')
    _write(os.path.join(root, "docs", "index.md"), "# Alpha\n\nWelcome.\n")
    _write(os.path.join(root, "docs", "guide.md"), (
        "# Guide\n\nHow to.\n\n"
        "## Widget catalog\n\n"
        "<dfn>Widget catalog</dfn> is a list of every widget this ships.\n\n"
        "See the notes on chained revision for the history model.\n"
    ))
    _write(os.path.join(root, "docs", "deep", "notes.md"), (
        "# Notes\n\nA page two levels below the mount root.\n"
    ))
    _write(os.path.join(root, ".selfdoc", "posts", "hello.md"), (
        "---\ntitle: Hello World\ndate: 2024-06-01\nslug: hello-world\n"
        "tags: []\ndraft: false\ndirectives: false\n---\nThe post body.\n\n"
        "## Chained revision\n\n"
        "<dfn>Chained revision</dfn> is a recorded edge between two states.\n\n"
        "The widget catalog is described at length in the guide.\n"
    ))
    build(root)
    return os.path.join(root, "docs", "_build")


@pytest.fixture()
def mounted_output(tmp_path):
    return _mounted_project(str(tmp_path / "alpha"))


def test_a_mounted_build_writes_no_visible_link_to_its_own_site_base(
        mounted_output):
    """Every hop out of the project's subtree is relative, at every depth."""
    assert absolute_anchors(mounted_output, DOCS_BASE) == []


def test_a_mounted_builds_own_output_resolves_when_it_declares_its_mount(
        mounted_output):
    """The subtree cannot answer its own mount-crossing references.

    Its pages reach the site level by climbing out of the output root and
    its posts are grafted out to the site root, so both sides address a
    tree this directory is only part of.  Declaring the mount is what says
    so; the assembly's pass over the assembled tree answers them.
    """
    assert check_output_resolution(
        mounted_output, base_url=f"{DOCS_BASE}/{SLUG}",
        mount_prefix=f"{SLUG}/",
    ) == []


def test_the_same_output_read_as_a_whole_site_reports_the_crossings(
        mounted_output):
    """Without the mount, the same references are escapes -- correctly.

    A build that really is its own site has no mount to climb, so a
    reference that leaves the output root names nothing.
    """
    lints = check_output_resolution(
        mounted_output, base_url=f"{DOCS_BASE}/{SLUG}",
    )
    assert any("escapes the output root" in lint.message for lint in lints)


def test_a_reference_climbing_past_the_mount_is_still_an_escape(tmp_path):
    """The allowance is exactly the mount, not "relative links are fine"."""
    out = str(tmp_path / "out")
    _write(
        os.path.join(out, "guide", "index.html"),
        '<a href="../../../elsewhere/">Out</a>',
    )
    lints = check_output_resolution(out, base_url=BASE, mount_prefix="alpha/")
    assert [lint.code for lint in lints] == ["LINK001"]
    assert "escapes the output root" in lints[0].message


def test_a_mounted_build_still_declares_absolute_canonicals(mounted_output):
    """Metadata is unchanged: only what a click follows became relative."""
    with open(
        os.path.join(mounted_output, "guide", "index.html"), encoding="utf-8",
    ) as f:
        page = f.read()
    assert f'<link rel="canonical" href="{DOCS_BASE}/{SLUG}/guide/">' in page
