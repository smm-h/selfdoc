"""Tests for Pagefind HTML metadata attributes (Phase 8.3)."""

import pytest


class TestPagefindMeta:
    """Test Pagefind data attributes on the article element."""

    def test_pagefind_body_on_article(self):
        """data-pagefind-body is on the article element when pagefind."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert "data-pagefind-body" in html
        # Verify it's on the article tag specifically
        assert "<article" in html
        idx = html.index("<article")
        end = html.index(">", idx)
        article_tag = html[idx:end + 1]
        assert "data-pagefind-body" in article_tag

    def test_pagefind_meta_project(self):
        """data-pagefind-meta for project name is present."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "MyProject", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert 'data-pagefind-meta="project:MyProject"' in html

    def test_pagefind_meta_type(self):
        """data-pagefind-meta for page type is present when page_type set."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind", page_type="guide",
        )
        assert 'data-pagefind-meta="type:guide"' in html

    def test_pagefind_meta_type_absent_when_none(self):
        """data-pagefind-meta for type is absent when page_type is None."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind", page_type=None,
        )
        assert 'data-pagefind-meta="type:' not in html

    def test_pagefind_meta_date(self):
        """data-pagefind-meta for date is present when date_published set."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind", date_published="2024-01-15",
        )
        assert 'data-pagefind-meta="date:2024-01-15"' in html

    def test_pagefind_meta_date_absent_when_none(self):
        """data-pagefind-meta for date is absent when no date available."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind", date_published=None,
        )
        assert 'data-pagefind-meta="date:' not in html

    def test_pagefind_filter_version(self):
        """data-pagefind-filter for version is present."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "2.3.1",
            prefix="", search_engine="pagefind",
        )
        assert 'data-pagefind-filter="version:2.3.1"' in html

    def test_no_pagefind_attrs_for_builtin(self):
        """No pagefind attributes when search_engine is builtin (None)."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine=None,
        )
        assert "data-pagefind-body" not in html
        assert "data-pagefind-meta" not in html
        assert "data-pagefind-filter" not in html

    def test_no_pagefind_attrs_for_fuse(self):
        """No pagefind attributes when search_engine is fuse."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="fuse",
        )
        assert "data-pagefind-body" not in html
        assert "data-pagefind-meta" not in html
        assert "data-pagefind-filter" not in html

    def test_no_pagefind_attrs_for_minisearch(self):
        """No pagefind attributes when search_engine is minisearch."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="minisearch",
        )
        assert "data-pagefind-body" not in html
        assert "data-pagefind-meta" not in html
        assert "data-pagefind-filter" not in html

    def test_no_locale_filter(self):
        """No data-pagefind-filter for locale (Pagefind auto-partitions by lang)."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
            lang="fr", current_locale="fr",
        )
        assert 'data-pagefind-filter="locale' not in html
        assert 'data-pagefind-filter="lang' not in html
        # But version filter should still be there
        assert 'data-pagefind-filter="version:1.0.0"' in html

    def test_all_attrs_on_article_tag(self):
        """All pagefind attributes appear on the article element."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
            page_type="reference", date_published="2024-06-01",
        )
        idx = html.index("<article")
        end = html.index(">", idx)
        article_tag = html[idx:end + 1]
        assert "data-pagefind-body" in article_tag
        assert 'data-pagefind-meta="project:Project"' in article_tag
        assert 'data-pagefind-meta="type:reference"' in article_tag
        assert 'data-pagefind-meta="date:2024-06-01"' in article_tag
        assert 'data-pagefind-filter="version:1.0.0"' in article_tag

    def test_html_escaping_in_project_name(self):
        """Special characters in project name are HTML-escaped."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", 'My "Project" <1>', "1.0.0",
            prefix="", search_engine="pagefind",
        )
        # _escape_html should have escaped the special characters
        assert 'data-pagefind-meta="project:My &quot;Project&quot; &lt;1&gt;"' in html
