"""Per-page heading anchors in the project manifest.

The manifest records each page's headings with the final, de-duplicated
anchors the built page carries, so a consumer (editor outline, deep-link
checker) never has to re-derive them.
"""

from __future__ import annotations

import json
import os

from selfdoc_core.manifest import generate_manifest, load_manifest


PAGE_WITH_DUPES = (
    "# Guide\n"
    "\n"
    "Intro.\n"
    "\n"
    "## Setup\n"
    "\n"
    "One.\n"
    "\n"
    "## Setup\n"
    "\n"
    "Two.\n"
    "\n"
    "### Deeper\n"
    "\n"
    "```python\n"
    "# not a heading\n"
    "```\n"
)


def _pages_data(content, frontmatter=None):
    """Shape one page the way ``resolve_all_docs`` returns it."""
    return {"guide.md": (frontmatter or {}, content, content, 0)}


def _read(tmp_path):
    with open(os.path.join(tmp_path, ".selfdoc", "manifest.json")) as f:
        return json.load(f)


class TestManifestHeadings:
    def test_pages_carry_heading_anchors(self, tmp_path):
        generate_manifest(
            {"name": "proj"}, _pages_data(PAGE_WITH_DUPES),
            dir_path=str(tmp_path),
        )
        page = _read(tmp_path)["pages"][0]
        assert page["headings"] == [
            {"level": 1, "text": "Guide", "anchor": "guide"},
            {"level": 2, "text": "Setup", "anchor": "setup"},
            {"level": 2, "text": "Setup", "anchor": "setup-1"},
            {"level": 3, "text": "Deeper", "anchor": "deeper"},
        ]

    def test_code_fence_hash_line_is_not_a_heading(self, tmp_path):
        generate_manifest(
            {"name": "proj"}, _pages_data(PAGE_WITH_DUPES),
            dir_path=str(tmp_path),
        )
        page = _read(tmp_path)["pages"][0]
        assert all(h["text"] != "not a heading" for h in page["headings"])

    def test_page_title_anchor_follows_frontmatter_title(self, tmp_path):
        """The first H1 is rendered from the page title, so its anchor is too."""
        generate_manifest(
            {"name": "proj"},
            _pages_data(PAGE_WITH_DUPES, frontmatter={"title": "Getting Started"}),
            dir_path=str(tmp_path),
        )
        page = _read(tmp_path)["pages"][0]
        assert page["headings"][0] == {
            "level": 1, "text": "Guide", "anchor": "getting-started",
        }

    def test_page_with_no_headings_gets_empty_list(self, tmp_path):
        generate_manifest(
            {"name": "proj"}, _pages_data("Just a paragraph.\n"),
            dir_path=str(tmp_path),
        )
        assert _read(tmp_path)["pages"][0]["headings"] == []

    def test_schema_version_unchanged(self, tmp_path):
        """Headings are an additive field: the tolerant reader contract
        covers them, so schema_version stays 1."""
        generate_manifest(
            {"name": "proj"}, _pages_data(PAGE_WITH_DUPES),
            dir_path=str(tmp_path),
        )
        data = _read(tmp_path)
        assert data["schema_version"] == 1
        manifest = load_manifest(
            os.path.join(tmp_path, ".selfdoc", "manifest.json")
        )
        assert manifest is not None
        assert manifest.pages[0]["headings"][0]["anchor"] == "guide"
