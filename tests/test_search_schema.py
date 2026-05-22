"""Tests for expanded search index schema with SearchEntry fields."""

import dataclasses

from selfdoc.build import _build_search_index
from selfdoc.context import SearchEntry
from selfdoc.docs import parse_frontmatter


class TestSearchEntryFields:
    def test_returns_search_entries(self):
        md = {"index.md": "# Home\n\nWelcome to the site.\n"}
        result = _build_search_index(md)
        assert len(result) > 0
        assert isinstance(result[0], SearchEntry)

    def test_basic_fields(self):
        md = {"index.md": "# Home\n\nWelcome.\n"}
        result = _build_search_index(md)
        entry = result[0]
        assert entry.title == "Home"
        assert "Welcome" in entry.body
        assert entry.path != ""

    def test_version_locale_target_project(self):
        md = {"index.md": "# Home\n\nContent.\n"}
        result = _build_search_index(
            md, version="1.0.0", locale="fr", target="python", project="mylib",
        )
        entry = result[0]
        assert entry.version == "1.0.0"
        assert entry.locale == "fr"
        assert entry.target == "python"
        assert entry.project == "mylib"

    def test_defaults_empty(self):
        md = {"index.md": "# Home\n\nContent.\n"}
        result = _build_search_index(md)
        entry = result[0]
        assert entry.version == ""
        assert entry.locale == ""
        assert entry.target == ""
        assert entry.project == ""
        assert entry.group == ""
        assert entry.tags == []

    def test_asdict_serializable(self):
        md = {"index.md": "# Home\n\nContent.\n"}
        result = _build_search_index(md)
        d = dataclasses.asdict(result[0])
        assert isinstance(d, dict)
        assert "title" in d
        assert "version" in d
        assert "tags" in d


class TestGroupDerivation:
    def test_grouped_nav_item(self):
        md = {"api/reference.md": "# API Reference\n\nDetails.\n"}
        nav_items = [
            {"group": "API", "slug": "api", "items": [
                {"label": "Reference", "path": "api/reference/index.html", "md_path": "api/reference.md"},
            ]},
        ]
        result = _build_search_index(md, nav_items=nav_items)
        assert result[0].group == "API"

    def test_ungrouped_page(self):
        md = {"guide.md": "# Guide\n\nContent.\n"}
        nav_items = [
            {"label": "Guide", "path": "guide/index.html", "md_path": "guide.md"},
        ]
        result = _build_search_index(md, nav_items=nav_items)
        # Ungrouped pages have no "group" key, so group defaults to ""
        assert result[0].group == ""

    def test_page_not_in_nav(self):
        md = {"orphan.md": "# Orphan\n\nNo nav.\n"}
        nav_items = [
            {"group": "API", "slug": "api", "items": [
                {"label": "Ref", "path": "api/ref/index.html", "md_path": "api/ref.md"},
            ]},
        ]
        result = _build_search_index(md, nav_items=nav_items)
        assert result[0].group == ""

    def test_multiple_groups(self):
        md = {
            "api/ref.md": "# Ref\n\nAPI details.\n",
            "cli/usage.md": "# Usage\n\nCLI help.\n",
        }
        nav_items = [
            {"group": "API", "slug": "api", "items": [
                {"label": "Ref", "path": "api/ref/index.html", "md_path": "api/ref.md"},
            ]},
            {"group": "CLI", "slug": "cli", "items": [
                {"label": "Usage", "path": "cli/usage/index.html", "md_path": "cli/usage.md"},
            ]},
        ]
        result = _build_search_index(md, nav_items=nav_items)
        groups = {e.title: e.group for e in result}
        assert groups["Ref"] == "API"
        assert groups["Usage"] == "CLI"


class TestTypeDerivation:
    def test_api_page(self):
        md = {"api/ref.md": "# API Reference\n\nGenerated docs.\n"}
        fm = {"api/ref.md": {"generated": True}}
        nav_items = [
            {"group": "API", "slug": "api", "items": [
                {"label": "Ref", "path": "api/ref/index.html", "md_path": "api/ref.md"},
            ]},
        ]
        result = _build_search_index(md, frontmatter=fm, nav_items=nav_items)
        assert result[0].type == "api"

    def test_cli_page(self):
        md = {"cli/commands.md": "# Commands\n\nCLI reference.\n"}
        fm = {"cli/commands.md": {"generated": True}}
        nav_items = [
            {"group": "CLI Reference", "slug": "cli-reference", "items": [
                {"label": "Commands", "path": "cli/commands/index.html", "md_path": "cli/commands.md"},
            ]},
        ]
        result = _build_search_index(md, frontmatter=fm, nav_items=nav_items)
        assert result[0].type == "cli"

    def test_changelog_page(self):
        md = {"changelog.md": "# Changelog\n\n## 1.0.0\n\nInitial release.\n"}
        result = _build_search_index(md)
        for entry in result:
            assert entry.type == "changelog"

    def test_glossary_page(self):
        md = {"glossary.md": "# Glossary\n\nTerms and definitions.\n"}
        result = _build_search_index(md)
        for entry in result:
            assert entry.type == "glossary"

    def test_guide_page_default(self):
        md = {"getting-started.md": "# Getting Started\n\nFollow these steps.\n"}
        result = _build_search_index(md)
        assert result[0].type == "guide"

    def test_generated_without_api_group_is_guide(self):
        """generated: true but not in API/CLI group -> guide."""
        md = {"examples/demo.md": "# Demo\n\nExample.\n"}
        fm = {"examples/demo.md": {"generated": True}}
        nav_items = [
            {"group": "Examples", "slug": "examples", "items": [
                {"label": "Demo", "path": "examples/demo/index.html", "md_path": "examples/demo.md"},
            ]},
        ]
        result = _build_search_index(md, frontmatter=fm, nav_items=nav_items)
        assert result[0].type == "guide"


class TestTagsInSearchIndex:
    def test_tags_from_frontmatter(self):
        md = {"guide.md": "# Guide\n\nContent.\n"}
        fm = {"guide.md": {"tags": ["python", "deployment"]}}
        result = _build_search_index(md, frontmatter=fm)
        assert result[0].tags == ["python", "deployment"]

    def test_string_tag_wrapped_in_list(self):
        """A single string tag (no comma in frontmatter) is wrapped in a list."""
        md = {"guide.md": "# Guide\n\nContent.\n"}
        fm = {"guide.md": {"tags": "python"}}
        result = _build_search_index(md, frontmatter=fm)
        assert result[0].tags == ["python"]

    def test_no_tags_empty_list(self):
        md = {"guide.md": "# Guide\n\nContent.\n"}
        fm = {"guide.md": {}}
        result = _build_search_index(md, frontmatter=fm)
        assert result[0].tags == []

    def test_tags_from_parsed_frontmatter(self):
        """Integration: parse_frontmatter bracket list -> search index tags."""
        content = "---\ntags: [deploy, advanced, python]\n---\n# Guide\n\nContent.\n"
        meta, body = parse_frontmatter(content)
        md = {"guide.md": body}
        fm = {"guide.md": meta}
        result = _build_search_index(md, frontmatter=fm)
        assert result[0].tags == ["deploy", "advanced", "python"]
