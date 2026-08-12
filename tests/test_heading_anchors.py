"""Heading anchor unification: one scan feeds the renderer and the index.

The renderer assigns heading ids with a de-duplication counter
(``setup``, ``setup-1``, ...).  Pagefind reads its sub-result anchors off
those same ids, so every anchor the index offers has to exist on the page
-- and a ``#``-prefixed line inside a fenced code block must not become
one.
"""

from __future__ import annotations

import json
import os
import re

from selfdoc_core.html import md_to_html
from selfdoc.build import build
from conftest import default_config
from test_pagefind_index import _fragments


def _ids_in(html: str) -> set[str]:
    """Every element id present in *html*."""
    return set(re.findall(r'\sid="([^"]+)"', html))


def _indexed_anchors(fragments) -> list[str]:
    """Every anchor id Pagefind recorded across the indexed site."""
    return [
        anchor["id"]
        for fragment in fragments
        for anchor in fragment["anchors"]
        if anchor.get("id")
    ]


DUPLICATE_HEADINGS = (
    "# Guide\n"
    "\n"
    "Intro text.\n"
    "\n"
    "## Setup\n"
    "\n"
    "First setup section.\n"
    "\n"
    "## Setup\n"
    "\n"
    "Second setup section.\n"
)

CODE_FENCE_BODY = (
    "```python\n"
    "# not a heading\n"
    "value = 1\n"
    "```\n"
    "\n"
    "## Real Heading\n"
    "\n"
    "Body.\n"
)

CODE_FENCE_HASH = "# Guide\n\nIntro text.\n\n" + CODE_FENCE_BODY


class TestDuplicateHeadings:
    """Repeated heading text must produce distinct, matching anchors."""

    def test_renderer_deduplicates(self):
        html = md_to_html(DUPLICATE_HEADINGS)
        ids = _ids_in(html)
        assert "setup" in ids
        assert "setup-1" in ids

    def test_rendered_ids_are_distinct(self):
        html = md_to_html(DUPLICATE_HEADINGS)
        setup_ids = sorted(i for i in _ids_in(html) if i.startswith("setup"))
        assert setup_ids == ["setup", "setup-1"]


class TestCodeFenceHashLines:
    """``#`` lines inside a fenced block are code, not headings."""

    def test_renderer_emits_no_anchor(self):
        html = md_to_html(CODE_FENCE_HASH)
        assert "not-a-heading" not in _ids_in(html)

    def test_real_heading_after_fence_still_gets_an_id(self):
        assert "real-heading" in _ids_in(md_to_html(CODE_FENCE_HASH))


class TestBuiltSiteAnchorsResolve:
    """End-to-end: every anchor the built index offers exists in its page."""

    def test_all_anchors_resolve(self, tmp_path):
        project = str(tmp_path)
        with open(os.path.join(project, "selfdoc.json"), "w") as f:
            json.dump(default_config(docs="docs/", output="docs/_build/"), f)
        src = os.path.join(project, "src")
        os.makedirs(src, exist_ok=True)
        with open(os.path.join(src, "__init__.py"), "w") as f:
            f.write('"""Example package."""\n')
        docs = os.path.join(project, "docs")
        os.makedirs(docs, exist_ok=True)
        with open(os.path.join(docs, "index.md"), "w") as f:
            f.write("# Home\n\nWelcome.\n")
        with open(os.path.join(docs, "guide.md"), "w") as f:
            f.write(DUPLICATE_HEADINGS + "\n" + CODE_FENCE_BODY)

        build(project)

        out = os.path.join(project, "docs", "_build")
        checked = 0
        for fragment in _fragments(out):
            page = fragment["url"].lstrip("/")
            if page == "" or page.endswith("/"):
                page += "index.html"
            html_path = os.path.join(out, page)
            assert os.path.isfile(html_path), f"{html_path} not built"
            with open(html_path, encoding="utf-8") as f:
                ids = _ids_in(f.read())
            for anchor in fragment["anchors"]:
                if not anchor.get("id"):
                    continue
                assert anchor["id"] in ids, (
                    f"anchor {anchor['id']!r} from {fragment['url']!r} "
                    f"missing in {page}"
                )
                checked += 1

        assert checked > 0

    def test_duplicate_headings_are_indexed_separately(self, tmp_path):
        """The second ``## Setup`` is its own sub-result, at its own id."""
        project = str(tmp_path)
        with open(os.path.join(project, "selfdoc.json"), "w") as f:
            json.dump(default_config(docs="docs/", output="docs/_build/"), f)
        os.makedirs(os.path.join(project, "src"), exist_ok=True)
        with open(os.path.join(project, "src", "__init__.py"), "w") as f:
            f.write('"""Example package."""\n')
        docs = os.path.join(project, "docs")
        os.makedirs(docs, exist_ok=True)
        with open(os.path.join(docs, "index.md"), "w") as f:
            f.write("# Home\n\nWelcome.\n")
        with open(os.path.join(docs, "guide.md"), "w") as f:
            f.write(DUPLICATE_HEADINGS)

        build(project)

        anchors = _indexed_anchors(_fragments(os.path.join(project, "docs", "_build")))
        assert "setup" in anchors
        assert "setup-1" in anchors
        assert "not-a-heading" not in anchors
