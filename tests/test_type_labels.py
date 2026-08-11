"""Tests for type-aware labeling (Phase 1, Task 1.4)."""

from selfdoc.html import _wrap_page, _render_search_dialog


def _render_archived_page(page_type=None, archived=True):
    """Render a page as an archived version, where the notice belongs."""
    return _wrap_page(
        "<p>Test content</p>",
        "<li>Nav</li>",
        "Test Page",
        "TestProject",
        "1.0.0",
        prefix="",
        asset_prefix="../../../",
        page_path="guide/index.html",
        page_type=page_type,
        is_latest=not archived,
        current_version="0.9.0" if archived else "1.0.0",
        available_versions=[
            {"version": "0.9.0"},
            {"version": "1.0.0"},
        ],
        mount_locale="en",
        mount_version="0.9.0" if archived else "1.0.0",
        mount_archived=archived,
    )


class TestSupersededNotice:
    """Whether a page is an archive decides the notice -- not its type.

    The old version banner carried a list of "doc types" that were allowed
    to show it, so that a post would not be told it was out of date.  A
    post is now a site-level page with no version at all, so it cannot be
    an archive and the type list has nothing left to decide.
    """

    def test_archived_page_shows_the_notice(self):
        html = _render_archived_page(page_type="guide")
        assert 'class="version-notice"' in html
        assert "has been superseded" in html

    def test_notice_is_keyed_to_this_version(self):
        html = _render_archived_page(page_type="guide")
        assert 'data-notice-key="0.9.0"' in html

    def test_notice_is_dismissable(self):
        html = _render_archived_page(page_type="guide")
        assert "version-notice-dismiss" in html
        assert "selfdoc-version-notice-" in html

    def test_notice_links_the_current_version_of_this_page(self):
        html = _render_archived_page(page_type="guide")
        # From en/v/0.9.0/guide/ out to the output root and back in to
        # en/guide/ -- the same two-step every cross-mount link takes.
        assert 'href="../../../../en/guide/"' in html

    def test_every_doc_type_shows_the_notice_when_archived(self):
        for page_type in (
            "guide", "tutorial", "api", "cli", "reference", "changelog",
            "glossary", None,
        ):
            html = _render_archived_page(page_type=page_type)
            assert 'class="version-notice"' in html, page_type

    def test_current_version_never_shows_the_notice(self):
        html = _render_archived_page(page_type="guide", archived=False)
        assert 'class="version-notice"' not in html

    def test_a_page_with_no_address_shows_no_notice(self):
        """The 404 page has no address of its own, so it has no version."""
        html = _wrap_page(
            "<p>Test</p>", "", "Test", "TestProject", "1.0.0",
            prefix="",
            page_type="guide",
            is_latest=False,
            current_version="0.9.0",
            available_versions=[{"version": "0.9.0"}, {"version": "1.0.0"}],
        )
        assert 'class="version-notice"' not in html


class TestSearchPlaceholder:
    """Search placeholder uses generic text."""

    def test_search_placeholder_is_generic(self):
        dialog_html = _render_search_dialog("")
        assert 'placeholder="Search... (Cmd+K)"' in dialog_html

    def test_search_placeholder_not_docs_specific(self):
        dialog_html = _render_search_dialog("")
        assert "Search docs" not in dialog_html
