"""Heading anchor unification: one scan feeds renderer and search index.

The renderer assigns heading ids with a de-duplication counter
(``setup``, ``setup-1``, ...).  The search index must emit the *same*
anchors, and must not invent headings from ``#``-prefixed lines inside
fenced code blocks.
"""

from __future__ import annotations

import json
import os
import re

from selfdoc_core.build import _build_search_index
from selfdoc_core.html import md_to_html
from selfdoc.build import build
from conftest import default_config, DEFAULT_PREFIX


def _ids_in(html: str) -> set[str]:
    """Every element id present in *html*."""
    return set(re.findall(r'\sid="([^"]+)"', html))


def _anchors(entries) -> list[str]:
    """The fragment of every search entry path that has one."""
    out = []
    for entry in entries:
        if "#" in entry.path:
            out.append(entry.path.split("#", 1)[1])
    return out


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

    def test_search_entries_target_distinct_anchors(self):
        entries = _build_search_index({"guide.md": DUPLICATE_HEADINGS})
        setup_anchors = [a for a in _anchors(entries) if a.startswith("setup")]
        assert setup_anchors == ["setup", "setup-1"]

    def test_search_anchors_resolve_in_rendered_page(self):
        entries = _build_search_index({"guide.md": DUPLICATE_HEADINGS})
        html = md_to_html(DUPLICATE_HEADINGS)
        ids = _ids_in(html)
        # The first H1 is consumed as the page title by the page wrapper,
        # so only the body headings are checked here.
        for anchor in _anchors(entries):
            if anchor == "guide":
                continue
            assert anchor in ids, f"{anchor!r} missing from rendered page"


class TestCodeFenceHashLines:
    """``#`` lines inside a fenced block are code, not headings."""

    def test_renderer_emits_no_anchor(self):
        html = md_to_html(CODE_FENCE_HASH)
        assert "not-a-heading" not in _ids_in(html)

    def test_search_index_emits_no_entry(self):
        entries = _build_search_index({"guide.md": CODE_FENCE_HASH})
        titles = [e.title for e in entries]
        assert "not a heading" not in titles
        assert "not-a-heading" not in _anchors(entries)

    def test_real_heading_after_fence_still_indexed(self):
        entries = _build_search_index({"guide.md": CODE_FENCE_HASH})
        assert "real-heading" in _anchors(entries)


class TestBuiltSiteAnchorsResolve:
    """End-to-end: every emitted search anchor exists in its page."""

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
        with open(os.path.join(out, "search-index.json"), encoding="utf-8") as f:
            index = json.load(f)

        checked = 0
        for entry in index:
            path = entry["path"]
            if "#" not in path:
                continue
            page, anchor = path.split("#", 1)
            page = page.lstrip("/")
            if page.endswith("/"):
                page += "index.html"
            html_path = os.path.join(out, page)
            assert os.path.isfile(html_path), f"{html_path} not built"
            with open(html_path, encoding="utf-8") as f:
                html = f.read()
            assert anchor in _ids_in(html), (
                f"anchor {anchor!r} from {path!r} missing in {page}"
            )
            checked += 1

        assert checked > 0
        assert DEFAULT_PREFIX  # locale/version prefix is in use
