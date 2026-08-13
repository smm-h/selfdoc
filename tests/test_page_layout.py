"""Tests for per-type layout control (Phase 1, Task 1.3)."""

from selfdoc.html import _wrap_page


def _render_page(page_type=None, toc_html="", date_modified=""):
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
        date_modified=date_modified,
    )


class TestPostPageLayout:
    """Post-type pages use narrow layout without TOC."""

    def test_post_page_has_layout_narrow_class(self):
        html = _render_page(page_type="post")
        assert 'class="docs-layout docs-layout--narrow"' in html

    def test_post_page_no_toc_aside_even_with_toc_html(self):
        toc = ('<nav class="docs-toc" aria-label="On this page">'
               '<a class="docs-toc-item" href="#sec">Section</a></nav>')
        html = _render_page(page_type="post", toc_html=toc)
        assert '<nav class="docs-toc"' not in html

    def test_post_page_no_toc_aside_without_toc_html(self):
        html = _render_page(page_type="post", toc_html="")
        assert '<nav class="docs-toc"' not in html


class TestNonPostPageLayout:
    """Non-post pages retain the standard three-column layout."""

    def test_guide_page_has_standard_layout_class(self):
        html = _render_page(page_type="guide")
        assert 'class="docs-layout"' in html
        assert "layout--narrow" not in html

    def test_guide_page_retains_toc_when_present(self):
        toc = ('<nav class="docs-toc" aria-label="On this page">'
               '<a class="docs-toc-item" href="#sec">Section</a></nav>')
        html = _render_page(page_type="guide", toc_html=toc)
        assert '<nav class="docs-toc"' in html

    def test_tutorial_page_retains_toc(self):
        toc = ('<nav class="docs-toc" aria-label="On this page">'
               '<a class="docs-toc-item" href="#sec">Section</a></nav>')
        html = _render_page(page_type="tutorial", toc_html=toc)
        assert '<nav class="docs-toc"' in html
        assert "layout--narrow" not in html

    def test_none_type_uses_standard_layout(self):
        html = _render_page(page_type=None)
        assert 'class="docs-layout"' in html
        assert "layout--narrow" not in html

    def test_changelog_page_uses_standard_layout(self):
        html = _render_page(page_type="changelog")
        assert "layout--narrow" not in html

    def test_no_toc_aside_when_toc_html_empty_regardless_of_type(self):
        """Even non-post pages omit TOC aside when toc_html is empty."""
        html = _render_page(page_type="guide", toc_html="")
        assert '<nav class="docs-toc"' not in html


class TestPostTocSuppression:
    """A post has no table of contents at any viewport.

    The desktop aside is suppressed by design; the mobile disclosure is the
    same decision at a narrower width, so it is suppressed with it.  Shipping
    only one of the two produced a table of contents that appeared when the
    page was zoomed and nowhere else.
    """

    TOC = ('<nav class="docs-toc" aria-label="On this page">'
               '<a class="docs-toc-item" href="#sec">Section</a></nav>')

    def test_post_page_has_no_mobile_toc(self):
        html = _render_page(page_type="post", toc_html=self.TOC)
        assert '<details class="mobile-toc">' not in html

    def test_post_page_has_neither_toc_element(self):
        html = _render_page(page_type="post", toc_html=self.TOC)
        assert '<nav class="docs-toc"' not in html
        assert "mobile-toc" not in html

    def test_docs_page_still_has_both_toc_elements(self):
        html = _render_page(page_type="guide", toc_html=self.TOC)
        assert '<nav class="docs-toc"' in html
        assert '<details class="mobile-toc">' in html


class TestSingleLastUpdated:
    """The page states when it was last updated exactly once.

    The styled page footer carries it in a readable form.  A second emitter
    put a raw ISO date outside the article, under classes no stylesheet
    defines, and a script prepended an "Updated" badge with no separator --
    the live "UpdatedLast updated: 2026-06-29".
    """

    def test_post_page_has_one_last_updated_element(self):
        html = _render_page(page_type="post", date_modified="2026-06-29")
        assert html.count("Last updated") == 1

    def test_post_page_footer_carries_the_readable_date(self):
        html = _render_page(page_type="post", date_modified="2026-06-29")
        assert '<time datetime="2026-06-29">June 29, 2026</time>' in html

    def test_post_page_has_no_read_indicator_block(self):
        html = _render_page(page_type="post", date_modified="2026-06-29")
        assert "post-read-indicator" not in html
        assert "post-last-updated" not in html
        assert "post-updated-badge" not in html
        assert 'class="post-meta"' not in html
