"""Tests for selfdoc.urls -- URLBuilder protocol and SimpleURLBuilder."""

from selfdoc.urls import SimpleURLBuilder, URLBuilder


class TestSimpleURLBuilderPageUrl:
    """Test SimpleURLBuilder.page_url() with various paths."""

    def test_simple_path(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.page_url("guide/") == "https://example.com/guide/"

    def test_nested_path(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.page_url("en/1.0.0/guide/") == "https://example.com/en/1.0.0/guide/"

    def test_html_path(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.page_url("index.html") == "https://example.com/index.html"

    def test_empty_path(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.page_url("") == "https://example.com/"

    def test_path_with_leading_slash(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.page_url("/guide/") == "https://example.com/guide/"

    def test_base_url_with_trailing_slash(self):
        b = SimpleURLBuilder("https://example.com/")
        assert b.page_url("guide/") == "https://example.com/guide/"

    def test_base_url_with_multiple_trailing_slashes(self):
        b = SimpleURLBuilder("https://example.com///")
        assert b.page_url("guide/") == "https://example.com/guide/"

    def test_path_is_just_slash(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.page_url("/") == "https://example.com/"


class TestSimpleURLBuilderAssetUrl:
    """Test SimpleURLBuilder.asset_url()."""

    def test_og_image(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.asset_url("og-index.png") == "https://example.com/og-index.png"

    def test_css_asset(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.asset_url("style.css") == "https://example.com/style.css"

    def test_empty_asset(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.asset_url("") == "https://example.com/"

    def test_nested_asset(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.asset_url("en/sitemap.xml") == "https://example.com/en/sitemap.xml"


class TestSimpleURLBuilderFeedUrl:
    """Test SimpleURLBuilder.feed_url()."""

    def test_feed_url(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.feed_url() == "https://example.com/feed.xml"

    def test_feed_url_trailing_slash(self):
        b = SimpleURLBuilder("https://example.com/")
        assert b.feed_url() == "https://example.com/feed.xml"


class TestSimpleURLBuilderBase:
    """Test SimpleURLBuilder.base()."""

    def test_base_no_trailing_slash(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.base() == "https://example.com"

    def test_base_strips_trailing_slash(self):
        b = SimpleURLBuilder("https://example.com/")
        assert b.base() == "https://example.com"

    def test_base_preserves_path(self):
        b = SimpleURLBuilder("https://example.com/docs")
        assert b.base() == "https://example.com/docs"

    def test_base_strips_trailing_but_preserves_path(self):
        b = SimpleURLBuilder("https://example.com/docs/")
        assert b.base() == "https://example.com/docs"


class TestURLBuilderProtocol:
    """Test that SimpleURLBuilder satisfies the URLBuilder protocol."""

    def test_isinstance_check(self):
        b = SimpleURLBuilder("https://example.com")
        assert isinstance(b, URLBuilder)

    def test_custom_implementation(self):
        """A custom class implementing the protocol should also pass isinstance."""

        class CustomBuilder:
            def page_url(self, path: str) -> str:
                return f"custom/{path}"

            def asset_url(self, path: str) -> str:
                return f"custom/{path}"

            def feed_url(self) -> str:
                return "custom/feed.xml"

            def base(self) -> str:
                return "custom"

        assert isinstance(CustomBuilder(), URLBuilder)


class TestEdgeCases:
    """Edge cases for URL building."""

    def test_no_double_slash_in_page_url(self):
        b = SimpleURLBuilder("https://example.com/")
        url = b.page_url("/guide/")
        assert "//" not in url.split("://")[1]

    def test_query_string_preserved(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.page_url("?q=test") == "https://example.com/?q=test"

    def test_fragment_preserved(self):
        b = SimpleURLBuilder("https://example.com")
        assert b.page_url("#section") == "https://example.com/#section"

    def test_http_scheme(self):
        b = SimpleURLBuilder("http://localhost:8080")
        assert b.page_url("guide/") == "http://localhost:8080/guide/"
        assert b.base() == "http://localhost:8080"
