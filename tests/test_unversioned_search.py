"""Tests for Phase 2 Task 2.4: unversioned search index entries.

Verifies that:
- _build_search_index produces entries with the given version string
- Unversioned pages (version="") produce entries with empty version
- build() produces a search-index.json with both versioned and unversioned entries
- A project with only unversioned pages produces all-empty version entries
- A project with no unversioned pages produces no empty version entries
"""

import json
import os

from selfdoc.build import build, _build_search_index
from selfdoc.context import SearchEntry
from conftest import default_config


def _read_search_index(project_dir):
    """Read and parse the search-index.json from a built project."""
    output_dir = project_dir / "docs" / "_build"
    index_path = output_dir / "search-index.json"
    with open(index_path) as f:
        return json.load(f)


class TestBuildSearchIndexDirect:
    """Direct calls to _build_search_index with version parameter."""

    def test_search_entries_versioned_have_version(self):
        """Entries built with version='1.0.0' carry that version string."""
        markdown_files = {
            "index.md": "# Home\n\nWelcome to the docs.\n",
            "guide.md": "# Guide\n\nA helpful guide.\n",
        }

        entries = _build_search_index(markdown_files, version="1.0.0")

        assert len(entries) > 0
        for entry in entries:
            assert isinstance(entry, SearchEntry)
            assert entry.version == "1.0.0"

    def test_search_entries_unversioned_empty_version(self):
        """Entries built with version='' carry an empty version string."""
        markdown_files = {
            "about.md": "# About\n\nAbout this project.\n",
            "terms.md": "# Terms\n\nTerms of service.\n",
        }

        entries = _build_search_index(markdown_files, version="")

        assert len(entries) > 0
        for entry in entries:
            assert isinstance(entry, SearchEntry)
            assert entry.version == ""


class TestBuildSearchIndexIntegration:
    """Full build() producing search-index.json with versioned/unversioned entries."""

    def test_build_produces_mixed_search_entries(self, make_project):
        """Versioned pages have version='1.0.0'; unversioned pages have version=''."""
        project_dir = make_project()

        # Add an unversioned page
        about_path = project_dir / "docs" / "about.md"
        about_path.write_text(
            "---\ntitle: About\nversioned: false\n---\n\n# About\n\nAbout us.\n"
        )

        build(str(project_dir))
        entries = _read_search_index(project_dir)

        assert len(entries) > 0

        versioned = [e for e in entries if e["version"] == "1.0.0"]
        unversioned = [e for e in entries if e["version"] == ""]

        assert len(versioned) > 0, "Expected at least one versioned search entry"
        assert len(unversioned) > 0, "Expected at least one unversioned search entry"

        # The unversioned entries should come from the about page
        unversioned_titles = [e["title"] for e in unversioned]
        assert "About" in unversioned_titles

    def test_search_index_contains_both_versioned_and_unversioned(self, make_project):
        """Both versioned and unversioned pages produce entries in the index."""
        project_dir = make_project()

        # Add unversioned page
        faq_path = project_dir / "docs" / "faq.md"
        faq_path.write_text(
            "---\ntitle: FAQ\nversioned: false\n---\n\n# FAQ\n\nFrequently asked.\n"
        )

        build(str(project_dir))
        entries = _read_search_index(project_dir)

        # Verify both versioned and unversioned entries exist
        versions_seen = {e["version"] for e in entries}
        assert "1.0.0" in versions_seen, "Missing versioned entries"
        assert "" in versions_seen, "Missing unversioned entries"

        # Verify the versioned entry comes from index.md (the default page)
        versioned_titles = [e["title"] for e in entries if e["version"] == "1.0.0"]
        assert "Test Project" in versioned_titles

        # Verify the unversioned entry comes from faq.md
        unversioned_titles = [e["title"] for e in entries if e["version"] == ""]
        assert "FAQ" in unversioned_titles

    def test_all_unversioned_search_entries(self, make_project):
        """When ALL pages are unversioned, all entries have version=''."""
        project_dir = make_project()

        # Make the default index.md unversioned
        index_path = project_dir / "docs" / "index.md"
        index_path.write_text(
            "---\ntitle: Home\nversioned: false\n---\n\n# Home\n\nWelcome.\n"
        )

        build(str(project_dir))
        entries = _read_search_index(project_dir)

        assert len(entries) > 0
        for entry in entries:
            assert entry["version"] == "", (
                f"Expected empty version but got '{entry['version']}' "
                f"for entry '{entry['title']}'"
            )

    def test_no_unversioned_search_entries_when_none(self, make_project):
        """When no pages are unversioned, all entries have a non-empty version."""
        project_dir = make_project()

        # Default project has only versioned pages (index.md without versioned: false)
        build(str(project_dir))
        entries = _read_search_index(project_dir)

        assert len(entries) > 0
        for entry in entries:
            assert entry["version"] != "", (
                f"Expected non-empty version but got empty for entry '{entry['title']}'"
            )
