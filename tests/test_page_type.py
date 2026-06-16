"""Tests for frontmatter-driven page type resolution (Phase 1, Task 1.1)."""

from selfdoc.build import _build_search_index


class TestFrontmatterTypeOverride:
    """Explicit frontmatter 'type' overrides the heuristic."""

    def test_explicit_type_overrides_guide_default(self):
        md = {"intro.md": "# Intro\nHello"}
        fm = {"intro.md": {"type": "tutorial"}}
        entries = _build_search_index(md, frontmatter=fm)
        assert entries[0].type == "tutorial"

    def test_explicit_type_overrides_changelog_heuristic(self):
        md = {"changelog.md": "# Changelog\nStuff"}
        fm = {"changelog.md": {"type": "post"}}
        entries = _build_search_index(md, frontmatter=fm)
        assert entries[0].type == "post"

    def test_explicit_type_overrides_glossary_heuristic(self):
        md = {"glossary.md": "# Glossary\nTerms"}
        fm = {"glossary.md": {"type": "reference"}}
        entries = _build_search_index(md, frontmatter=fm)
        assert entries[0].type == "reference"

    def test_explicit_type_overrides_api_heuristic(self):
        md = {"api.md": "# API\nDocs"}
        fm = {"api.md": {"generated": True, "type": "reference"}}
        nav = [{"group": "API Reference", "slug": "api-reference",
                "items": [{"slug": "api", "md_path": "api.md"}]}]
        entries = _build_search_index(md, frontmatter=fm, nav_items=nav)
        assert entries[0].type == "reference"

    def test_explicit_type_overrides_cli_heuristic(self):
        md = {"cli.md": "# CLI\nCommands"}
        fm = {"cli.md": {"generated": True, "type": "tutorial"}}
        nav = [{"group": "CLI Reference", "slug": "cli-reference",
                "items": [{"slug": "cli", "md_path": "cli.md"}]}]
        entries = _build_search_index(md, frontmatter=fm, nav_items=nav)
        assert entries[0].type == "tutorial"

    def test_arbitrary_type_value(self):
        md = {"blog.md": "# Blog Post\nContent"}
        fm = {"blog.md": {"type": "post"}}
        entries = _build_search_index(md, frontmatter=fm)
        assert entries[0].type == "post"

    def test_custom_type_preserved_exactly(self):
        md = {"page.md": "# Page\nContent"}
        fm = {"page.md": {"type": "cookbook"}}
        entries = _build_search_index(md, frontmatter=fm)
        assert entries[0].type == "cookbook"


class TestHeuristicFallback:
    """Without explicit type, heuristic still works as before."""

    def test_no_type_in_frontmatter_uses_heuristic_guide(self):
        md = {"page.md": "# Page\nContent"}
        fm = {"page.md": {"title": "Page"}}
        entries = _build_search_index(md, frontmatter=fm)
        assert entries[0].type == "guide"

    def test_no_frontmatter_at_all_uses_guide(self):
        md = {"page.md": "# Page\nContent"}
        entries = _build_search_index(md)
        assert entries[0].type == "guide"

    def test_changelog_heuristic_without_explicit_type(self):
        md = {"changelog.md": "# Changelog\nStuff"}
        entries = _build_search_index(md)
        assert entries[0].type == "changelog"

    def test_glossary_heuristic_without_explicit_type(self):
        md = {"glossary.md": "# Glossary\nTerms"}
        entries = _build_search_index(md)
        assert entries[0].type == "glossary"

    def test_empty_type_string_uses_heuristic(self):
        md = {"changelog.md": "# Changelog\nStuff"}
        fm = {"changelog.md": {"type": ""}}
        entries = _build_search_index(md, frontmatter=fm)
        assert entries[0].type == "changelog"

    def test_none_type_uses_heuristic(self):
        md = {"glossary.md": "# Glossary\nTerms"}
        fm = {"glossary.md": {"type": None}}
        entries = _build_search_index(md, frontmatter=fm)
        assert entries[0].type == "glossary"


class TestTypeWithOtherMetadata:
    """Type coexists with other frontmatter fields."""

    def test_type_and_tags_both_work(self):
        md = {"page.md": "# Page\nContent"}
        fm = {"page.md": {"type": "tutorial", "tags": ["python", "beginner"]}}
        entries = _build_search_index(md, frontmatter=fm)
        assert entries[0].type == "tutorial"
        assert entries[0].tags == ["python", "beginner"]

    def test_type_on_generated_page_without_matching_nav(self):
        md = {"api.md": "# API\nDocs"}
        fm = {"api.md": {"generated": True, "type": "reference"}}
        entries = _build_search_index(md, frontmatter=fm)
        assert entries[0].type == "reference"

    def test_all_sections_inherit_page_type(self):
        md = {"page.md": "# H1\nIntro\n## H2\nBody\n## H3\nMore"}
        fm = {"page.md": {"type": "tutorial"}}
        entries = _build_search_index(md, frontmatter=fm)
        assert len(entries) == 3
        for entry in entries:
            assert entry.type == "tutorial"
