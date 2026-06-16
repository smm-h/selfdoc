"""Tests for per-type layout control (Phase 1, Task 1.3)."""

from selfdoc.html import _wrap_page


def _render_page(page_type=None, toc_html=""):
    """Render a page with _wrap_page and return the full HTML."""
    return _wrap_page(
        "<p>Test content</p>",
        "<li>Nav</li>",
        "Test Page",
        "TestProject",
        "1.0.0",
        prefix="",
        page_type=page_type,
        toc_html=toc_html,
    )


class TestPostPageLayout:
    """Post-type pages use narrow layout without TOC."""

    def test_post_page_has_layout_narrow_class(self):
        html = _render_page(page_type="post")
        assert 'class="layout layout--narrow"' in html

    def test_post_page_no_toc_aside_even_with_toc_html(self):
        toc = '<nav class="toc-nav"><a href="#sec">Section</a></nav>'
        html = _render_page(page_type="post", toc_html=toc)
        assert '<aside class="toc">' not in html

    def test_post_page_no_toc_aside_without_toc_html(self):
        html = _render_page(page_type="post", toc_html="")
        assert '<aside class="toc">' not in html


class TestNonPostPageLayout:
    """Non-post pages retain the standard three-column layout."""

    def test_guide_page_has_standard_layout_class(self):
        html = _render_page(page_type="guide")
        assert 'class="layout"' in html
        assert "layout--narrow" not in html

    def test_guide_page_retains_toc_when_present(self):
        toc = '<nav class="toc-nav"><a href="#sec">Section</a></nav>'
        html = _render_page(page_type="guide", toc_html=toc)
        assert '<aside class="toc">' in html

    def test_tutorial_page_retains_toc(self):
        toc = '<nav class="toc-nav"><a href="#sec">Section</a></nav>'
        html = _render_page(page_type="tutorial", toc_html=toc)
        assert '<aside class="toc">' in html
        assert "layout--narrow" not in html

    def test_none_type_uses_standard_layout(self):
        html = _render_page(page_type=None)
        assert 'class="layout"' in html
        assert "layout--narrow" not in html

    def test_changelog_page_uses_standard_layout(self):
        html = _render_page(page_type="changelog")
        assert "layout--narrow" not in html

    def test_no_toc_aside_when_toc_html_empty_regardless_of_type(self):
        """Even non-post pages omit TOC aside when toc_html is empty."""
        html = _render_page(page_type="guide", toc_html="")
        assert '<aside class="toc">' not in html
