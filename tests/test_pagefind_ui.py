"""Tests for Pagefind search UI integration (Phase 8.2)."""

import pytest


class TestPagefindUI:
    """Test Pagefind UI rendering in HTML output."""

    def test_pagefind_css_loaded(self):
        """Pagefind CSS is included when search_engine is 'pagefind'."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert "pagefind/pagefind-ui.css" in html

    def test_pagefind_js_loaded(self):
        """Pagefind JS is included when search_engine is 'pagefind'."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert "pagefind/pagefind-ui.js" in html

    def test_builtin_js_not_loaded_for_pagefind(self):
        """search.js is NOT included when pagefind is selected."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert 'src="search.js"' not in html

    def test_fuse_cdn_not_loaded_for_pagefind(self):
        """Fuse.js CDN is NOT loaded when pagefind is selected."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert "fuse.js" not in html
        assert "fuse.min.js" not in html

    def test_minisearch_cdn_not_loaded_for_pagefind(self):
        """MiniSearch CDN is NOT loaded when pagefind is selected."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert "minisearch" not in html.lower()
        assert "pagefind" in html

    def test_cmd_k_shortcut_present(self):
        """Cmd+K keyboard shortcut handler is present for pagefind."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert "metaKey" in html or "ctrlKey" in html
        assert '"k"' in html or "'k'" in html

    def test_pagefind_container_present(self):
        """Pagefind UI container div is present in the dialog."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert 'id="pagefind-container"' in html

    def test_pagefind_ui_initialized(self):
        """Pagefind UI is initialized with the correct container."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert "PagefindUI" in html
        assert "#pagefind-container" in html

    def test_builtin_search_dialog_unchanged(self):
        """Builtin search engine still uses the original dialog with input."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine=None,
        )
        assert 'class="search-input"' in html
        assert 'id="search-results"' in html
        assert 'id="pagefind-container"' not in html

    def test_fuse_search_dialog_unchanged(self):
        """Fuse search engine still uses the original dialog."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="fuse",
        )
        assert 'class="search-input"' in html
        assert 'id="pagefind-container"' not in html

    def test_search_dialog_still_a_dialog(self):
        """Pagefind search still uses a dialog element."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert '<dialog class="search-dialog"' in html

    def test_close_button_present_for_pagefind(self):
        """Close button is present in the pagefind search dialog."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", search_engine="pagefind",
        )
        assert 'class="search-close"' in html

    def test_pagefind_prefix_paths(self):
        """Pagefind assets use the correct prefix path."""
        from selfdoc.html import _wrap_page
        html = _wrap_page(
            "<p>test</p>", "", "Test", "Project", "1.0.0",
            prefix="", asset_prefix="../../", search_engine="pagefind",
        )
        assert '../../pagefind/pagefind-ui.css' in html
        assert '../../pagefind/pagefind-ui.js' in html
