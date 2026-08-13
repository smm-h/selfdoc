"""The Pagefind search UI every generated page ships."""

from selfdoc.html import _wrap_page


def _page(**kwargs):
    return _wrap_page(
        "<p>test</p>", "", "Test", "Project", "1.0.0",
        prefix="", **kwargs,
    )


class TestPagefindUI:
    """The UI bundle, the dialog, and the shortcut that opens it."""

    def test_pagefind_css_loaded(self):
        assert "pagefind/pagefind-ui.css" in _page()

    def test_pagefind_js_loaded(self):
        assert "pagefind/pagefind-ui.js" in _page()

    def test_no_builtin_search_js(self):
        """Nothing references the deleted builtin bundle."""
        assert "search.js" not in _page()

    def test_no_cdn_assets(self):
        """The UI is served from the indexer's own output, never a CDN."""
        html = _page()
        assert "cdn.jsdelivr.net" not in html
        assert "fuse" not in html.lower()
        assert "minisearch" not in html.lower()

    def test_cmd_k_shortcut_present(self):
        html = _page()
        assert "metaKey" in html and "ctrlKey" in html
        assert '"k"' in html

    def test_shortcut_focuses_the_pagefind_input(self):
        """The focus call names the class the Pagefind UI actually renders."""
        assert "pagefind-ui__search-input" in _page()

    def test_pagefind_container_present(self):
        assert 'id="pagefind-container"' in _page()

    def test_pagefind_ui_initialized(self):
        html = _page()
        assert "PagefindUI" in html
        assert "#pagefind-container" in html

    def test_search_dialog_is_a_dialog(self):
        assert '<dialog class="search-dialog"' in _page()

    def test_close_button_present(self):
        assert 'class="search-close"' in _page()

    def test_no_builtin_dialog_leftovers(self):
        """The builtin input, results list and index base attribute are gone."""
        html = _page()
        assert 'class="search-input"' not in html
        assert 'id="search-results"' not in html
        assert "data-search-base" not in html
        assert "search-index.json" not in html

    def test_asset_paths_use_the_page_hop(self):
        """The bundle's own assets resolve from the page's own address."""
        html = _page(asset_prefix="../../")
        assert "../../pagefind/pagefind-ui.css" in html
        assert "../../pagefind/pagefind-ui.js" in html

    def test_no_bundle_path_is_ever_written_into_the_page(self):
        """The UI derives the index location; the build must not guess it.

        The UI reads ``document.currentScript.src`` and takes the
        directory it was loaded from -- a root-absolute path, correct at
        every depth and under every mount. A build-time value cannot be:
        the dynamic ``import()`` that loads the index resolves relative
        specifiers against the *bundle's* URL rather than the page's, so
        the hop that is right for the ``<script src>`` is wrong for the
        import. Written as ``asset_prefix + "pagefind/"``, a page at the
        output root produced the bare specifier ``"pagefind/pagefind.js"``
        (refused outright, so search returned nothing on every front page
        and every project landing page) and a page two levels inside a
        mount climbed one level too far and fetched another project's
        index.
        """
        for prefix in ("", "../", "../../", "../../../../"):
            assert "bundlePath" not in _page(asset_prefix=prefix), (
                f"asset_prefix={prefix!r} wrote a bundlePath into the page; "
                f"the only correct value is the one the UI computes at "
                f"runtime from its own script location"
            )
