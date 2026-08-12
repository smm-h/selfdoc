"""Tests for schema.org @type resolution from page type (Phase 1, Task 1.2)."""

import json
import re

from selfdoc.html import _render_seo_tags
from conftest import TEST_AUTHOR


def _extract_ld_json(seo_tags):
    """Extract JSON-LD object from SEO tags HTML."""
    match = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        seo_tags,
        re.DOTALL,
    )
    assert match, "No JSON-LD script tag found"
    return json.loads(match.group(1))


def _render_with_page_type(page_type, schema_types=None, page_tags=None):
    """Call _render_seo_tags with minimal args and a given page_type."""
    seo_tags, _security = _render_seo_tags(
        title="Test Page",
        base_url="https://example.com",
        page_path="test/index.html",
        description="A test page",
        body_html="<p>Hello</p>",
        author=TEST_AUTHOR,
        project_name="TestProject",
        repo=None,
        date_published=None,
        date_modified=None,
        lang="en",
        breadcrumbs=None,
        schema=None,
        twitter_site=None,
        deploy_target=None,
        page_type=page_type,
        schema_types=schema_types,
        page_tags=page_tags,
    )
    return _extract_ld_json(seo_tags)


class TestDefaultSchemaTypeMapping:
    """Default schema_types mapping resolves page types to schema.org @type."""

    def test_guide_resolves_to_tech_article(self):
        ld = _render_with_page_type("guide")
        assert ld["@type"] == "TechArticle"

    def test_tutorial_resolves_to_tech_article(self):
        ld = _render_with_page_type("tutorial")
        assert ld["@type"] == "TechArticle"

    def test_post_resolves_to_blog_posting(self):
        ld = _render_with_page_type("post")
        assert ld["@type"] == "BlogPosting"

    def test_changelog_resolves_to_web_page(self):
        ld = _render_with_page_type("changelog")
        assert ld["@type"] == "WebPage"

    def test_unknown_type_resolves_to_article(self):
        ld = _render_with_page_type("fieldnote")
        assert ld["@type"] == "Article"

    def test_none_type_defaults_to_guide_then_tech_article(self):
        """When page_type is None, it falls back to 'guide' key -> TechArticle."""
        ld = _render_with_page_type(None)
        assert ld["@type"] == "TechArticle"


class TestCustomSchemaTypesOverride:
    """Custom schema_types from config override the default mapping."""

    def test_override_guide_type(self):
        ld = _render_with_page_type("guide", schema_types={"guide": "HowTo"})
        assert ld["@type"] == "HowTo"

    def test_override_post_type(self):
        ld = _render_with_page_type("post", schema_types={"post": "Article"})
        assert ld["@type"] == "Article"

    def test_add_new_type(self):
        ld = _render_with_page_type("recipe", schema_types={"recipe": "Recipe"})
        assert ld["@type"] == "Recipe"

    def test_partial_override_preserves_defaults(self):
        """Overriding one key doesn't affect other defaults."""
        ld = _render_with_page_type("tutorial", schema_types={"post": "Article"})
        assert ld["@type"] == "TechArticle"

    def test_empty_schema_types_uses_defaults(self):
        ld = _render_with_page_type("guide", schema_types={})
        assert ld["@type"] == "TechArticle"


class TestBlogPostingKeywords:
    """BlogPosting pages get 'keywords' from frontmatter tags."""

    def test_blog_posting_with_tags_has_keywords(self):
        ld = _render_with_page_type("post", page_tags=["python", "testing", "ci"])
        assert ld["@type"] == "BlogPosting"
        assert ld["keywords"] == "python, testing, ci"

    def test_blog_posting_without_tags_has_no_keywords(self):
        ld = _render_with_page_type("post", page_tags=None)
        assert ld["@type"] == "BlogPosting"
        assert "keywords" not in ld

    def test_blog_posting_with_empty_tags_has_no_keywords(self):
        ld = _render_with_page_type("post", page_tags=[])
        assert ld["@type"] == "BlogPosting"
        assert "keywords" not in ld

    def test_non_blog_posting_with_tags_has_no_keywords(self):
        """Keywords are only added for BlogPosting type, not others."""
        ld = _render_with_page_type("guide", page_tags=["python", "testing"])
        assert ld["@type"] == "TechArticle"
        assert "keywords" not in ld

    def test_blog_posting_single_tag(self):
        ld = _render_with_page_type("post", page_tags=["release"])
        assert ld["keywords"] == "release"

    def test_custom_type_resolving_to_blog_posting_gets_keywords(self):
        """If custom schema_types maps a type to BlogPosting, keywords still work."""
        ld = _render_with_page_type(
            "news",
            schema_types={"news": "BlogPosting"},
            page_tags=["breaking", "update"],
        )
        assert ld["@type"] == "BlogPosting"
        assert ld["keywords"] == "breaking, update"
