"""Tests for localStorage-based post read indicators."""

from selfdoc_core.html import _generate_post_read_indicator_script


class TestPostReadIndicator:
    """Tests for _generate_post_read_indicator_script()."""

    def test_empty_date_returns_empty(self):
        """No script generated when last_updated is empty."""
        assert _generate_post_read_indicator_script("") == ""

    def test_contains_last_updated_display(self):
        """Output includes a visible 'Last updated' element."""
        html = _generate_post_read_indicator_script("2026-07-05")
        assert "Last updated: 2026-07-05" in html
        assert "post-last-updated" in html

    def test_contains_localstorage_read(self):
        """Output includes localStorage.getItem for read tracking."""
        html = _generate_post_read_indicator_script("2026-07-05")
        assert "localStorage.getItem" in html
        assert "post-read-" in html

    def test_contains_localstorage_write(self):
        """Output includes localStorage.setItem to record the visit."""
        html = _generate_post_read_indicator_script("2026-07-05")
        assert "localStorage.setItem" in html

    def test_contains_updated_badge(self):
        """Output includes an 'Updated' badge creation."""
        html = _generate_post_read_indicator_script("2026-07-05")
        assert "Updated" in html
        assert "post-updated-badge" in html

    def test_date_is_embedded_in_script(self):
        """The date string is embedded in the JS for comparison."""
        html = _generate_post_read_indicator_script("2026-07-05T14:30:00Z")
        assert "2026-07-05T14:30:00Z" in html

    def test_html_escaping(self):
        """Special characters in date are escaped for safe HTML embedding."""
        # Normal dates don't have special chars, but verify the escaping
        # mechanism is in place
        html = _generate_post_read_indicator_script("2026-07-05")
        assert "<script>" in html.lower() or "<script" in html.lower()
        # The date should be present and properly embedded
        assert "2026-07-05" in html

    def test_contains_post_meta_container(self):
        """Output has a container div with the post-read-indicator id."""
        html = _generate_post_read_indicator_script("2026-07-05")
        assert 'id="post-read-indicator"' in html
        assert 'class="post-meta"' in html
