"""Tests for page type resolution -- the ``type`` search facet."""

from selfdoc_core.html import derive_page_type


class TestFrontmatterTypeOverride:
    """Explicit frontmatter 'type' overrides the heuristic."""

    def test_explicit_type_overrides_guide_default(self):
        assert derive_page_type("intro.md", {"type": "tutorial"}) == "tutorial"

    def test_explicit_type_overrides_changelog_heuristic(self):
        assert derive_page_type("changelog.md", {"type": "post"}) == "post"

    def test_explicit_type_overrides_glossary_heuristic(self):
        assert derive_page_type(
            "glossary.md", {"type": "reference"},
        ) == "reference"

    def test_explicit_type_overrides_api_heuristic(self):
        assert derive_page_type(
            "api.md", {"generated": True, "type": "reference"},
            "API Reference",
        ) == "reference"

    def test_explicit_type_overrides_cli_heuristic(self):
        assert derive_page_type(
            "cli.md", {"generated": True, "type": "tutorial"},
            "CLI Reference",
        ) == "tutorial"

    def test_arbitrary_type_value(self):
        assert derive_page_type("blog.md", {"type": "post"}) == "post"

    def test_custom_type_preserved_exactly(self):
        assert derive_page_type("page.md", {"type": "cookbook"}) == "cookbook"


class TestHeuristicFallback:
    """Without explicit type, the page's own shape decides."""

    def test_no_type_in_frontmatter_uses_heuristic_guide(self):
        assert derive_page_type("page.md", {"title": "Page"}) == "guide"

    def test_no_frontmatter_at_all_uses_guide(self):
        assert derive_page_type("page.md", {}) == "guide"

    def test_changelog_heuristic_without_explicit_type(self):
        assert derive_page_type("changelog.md", {}) == "changelog"

    def test_glossary_heuristic_without_explicit_type(self):
        assert derive_page_type("glossary.md", {}) == "glossary"

    def test_generated_api_page(self):
        assert derive_page_type(
            "api.md", {"generated": True}, "API Reference",
        ) == "api"

    def test_generated_cli_page(self):
        assert derive_page_type(
            "cli.md", {"generated": True}, "CLI Reference",
        ) == "cli"

    def test_empty_type_string_uses_heuristic(self):
        assert derive_page_type("changelog.md", {"type": ""}) == "changelog"

    def test_none_type_uses_heuristic(self):
        assert derive_page_type("glossary.md", {"type": None}) == "glossary"


class TestTypeWithOtherMetadata:
    """Type coexists with other frontmatter fields."""

    def test_type_and_tags_both_work(self):
        meta = {"type": "tutorial", "tags": ["python", "beginner"]}
        assert derive_page_type("page.md", meta) == "tutorial"

    def test_type_on_generated_page_without_matching_nav(self):
        assert derive_page_type(
            "api.md", {"generated": True, "type": "reference"},
        ) == "reference"

    def test_generated_page_outside_a_reference_group_is_a_guide(self):
        assert derive_page_type(
            "api.md", {"generated": True}, "Guides",
        ) == "guide"


class TestTypeOnBuiltPages:
    """The derived type reaches the page as a Pagefind filter."""

    def test_every_page_carries_a_type_filter(self, make_project):
        from selfdoc.build import build

        project = make_project()
        (project / "docs" / "changelog.md").write_text(
            "# Changelog\n\nWhat changed.\n",
        )
        build(str(project))

        page = project / "docs" / "_build" / "changelog" / "index.html"
        assert 'data-pagefind-filter="type:changelog"' in page.read_text()
