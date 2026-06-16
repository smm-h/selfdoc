"""Tests for type-aware labeling (Phase 1, Task 1.4)."""

from selfdoc.html import _wrap_page, _render_search_dialog


def _render_old_version_page(page_type=None):
    """Render a page as a non-latest version to trigger version banner logic."""
    return _wrap_page(
        "<p>Test content</p>",
        "<li>Nav</li>",
        "Test Page",
        "TestProject",
        "1.0.0",
        prefix="",
        page_type=page_type,
        is_latest=False,
        current_version="0.9.0",
        available_versions=[
            {"version": "0.9.0", "indexed": True},
            {"version": "1.0.0", "indexed": True},
        ],
        url_prefix="en/0.9.0",
    )


class TestVersionBannerSuppression:
    """Non-doc types suppress the version banner."""

    def test_post_page_has_no_version_banner(self):
        html = _render_old_version_page(page_type="post")
        assert "version-banner" not in html

    def test_essay_page_has_no_version_banner(self):
        html = _render_old_version_page(page_type="essay")
        assert "version-banner" not in html

    def test_guide_page_retains_version_banner(self):
        html = _render_old_version_page(page_type="guide")
        assert "version-banner" in html
        assert "You are viewing docs for" in html

    def test_tutorial_page_retains_version_banner(self):
        html = _render_old_version_page(page_type="tutorial")
        assert "version-banner" in html

    def test_api_page_retains_version_banner(self):
        html = _render_old_version_page(page_type="api")
        assert "version-banner" in html

    def test_cli_page_retains_version_banner(self):
        html = _render_old_version_page(page_type="cli")
        assert "version-banner" in html

    def test_reference_page_retains_version_banner(self):
        html = _render_old_version_page(page_type="reference")
        assert "version-banner" in html

    def test_changelog_page_retains_version_banner(self):
        html = _render_old_version_page(page_type="changelog")
        assert "version-banner" in html

    def test_glossary_page_retains_version_banner(self):
        html = _render_old_version_page(page_type="glossary")
        assert "version-banner" in html

    def test_none_type_defaults_to_doc_and_shows_banner(self):
        """When page_type is None, defaults to guide behavior (doc type)."""
        html = _render_old_version_page(page_type=None)
        assert "version-banner" in html

    def test_latest_version_never_shows_banner(self):
        """Even doc types don't show banner when is_latest=True."""
        html = _wrap_page(
            "<p>Test</p>", "", "Test", "TestProject", "1.0.0",
            prefix="",
            page_type="guide",
            is_latest=True,
            current_version="1.0.0",
            available_versions=[{"version": "1.0.0", "indexed": True}],
        )
        assert "version-banner" not in html


class TestSearchPlaceholder:
    """Search placeholder uses generic text."""

    def test_search_placeholder_is_generic(self):
        dialog_html = _render_search_dialog("")
        assert 'placeholder="Search... (Cmd+K)"' in dialog_html

    def test_search_placeholder_not_docs_specific(self):
        dialog_html = _render_search_dialog("")
        assert "Search docs" not in dialog_html
