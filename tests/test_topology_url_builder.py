"""Tests for TopologyURLBuilder -- topology-aware URL generation."""

from selfdoc.urls import TopologyURLBuilder, URLBuilder


class TestTopologyURLBuilderPageUrl:
    """Test TopologyURLBuilder.page_url()."""

    def test_simple_path(self):
        b = TopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
        assert b.page_url("guide/") == "https://docs.smmh.dev/selfdoc/guide/"

    def test_nested_path(self):
        b = TopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
        assert b.page_url("en/1.0.0/guide/") == "https://docs.smmh.dev/selfdoc/en/1.0.0/guide/"

    def test_empty_path(self):
        b = TopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
        assert b.page_url("") == "https://docs.smmh.dev/selfdoc/"

    def test_leading_slash_stripped(self):
        b = TopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
        assert b.page_url("/guide/") == "https://docs.smmh.dev/selfdoc/guide/"

    def test_base_trailing_slash_stripped(self):
        b = TopologyURLBuilder("https://docs.smmh.dev/", "selfdoc")
        assert b.page_url("guide/") == "https://docs.smmh.dev/selfdoc/guide/"


class TestTopologyURLBuilderAssetUrl:
    """Test TopologyURLBuilder.asset_url()."""

    def test_asset(self):
        b = TopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
        assert b.asset_url("og-index.png") == "https://docs.smmh.dev/selfdoc/og-index.png"

    def test_empty_asset(self):
        b = TopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
        assert b.asset_url("") == "https://docs.smmh.dev/selfdoc/"


class TestTopologyURLBuilderFeedUrl:
    """Test TopologyURLBuilder.feed_url()."""

    def test_feed(self):
        b = TopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
        assert b.feed_url() == "https://docs.smmh.dev/selfdoc/feed.xml"


class TestTopologyURLBuilderBase:
    """Test TopologyURLBuilder.base()."""

    def test_base(self):
        b = TopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
        assert b.base() == "https://docs.smmh.dev/selfdoc"

    def test_base_strips_trailing(self):
        b = TopologyURLBuilder("https://docs.smmh.dev/", "selfdoc")
        assert b.base() == "https://docs.smmh.dev/selfdoc"


class TestTopologyURLBuilderProtocol:
    """TopologyURLBuilder satisfies URLBuilder protocol."""

    def test_isinstance(self):
        b = TopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
        assert isinstance(b, URLBuilder)


class TestTopologyURLBuilderCrossProject:
    """Test cross_project_url for linking to other projects."""

    def test_known_project(self):
        b = TopologyURLBuilder(
            "https://docs.smmh.dev", "selfdoc",
            projects={"rlsbl": "https://docs.smmh.dev/rlsbl"},
        )
        assert b.cross_project_url("rlsbl", "guide/") == "https://docs.smmh.dev/rlsbl/guide/"

    def test_known_project_empty_path(self):
        b = TopologyURLBuilder(
            "https://docs.smmh.dev", "selfdoc",
            projects={"rlsbl": "https://docs.smmh.dev/rlsbl"},
        )
        assert b.cross_project_url("rlsbl") == "https://docs.smmh.dev/rlsbl/"

    def test_unknown_project_fallback(self):
        b = TopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
        assert b.cross_project_url("unknown", "page/") == "https://docs.smmh.dev/unknown/page/"

    def test_known_project_trailing_slash_stripped(self):
        b = TopologyURLBuilder(
            "https://docs.smmh.dev", "selfdoc",
            projects={"rlsbl": "https://docs.smmh.dev/rlsbl/"},
        )
        assert b.cross_project_url("rlsbl", "guide/") == "https://docs.smmh.dev/rlsbl/guide/"


class TestMakeUrlBuilder:
    """Test the _make_url_builder helper function in build.py."""

    def test_topology_creates_topology_builder(self):
        from selfdoc.build import _make_url_builder
        config = {
            "base_url": "https://example.com",
            "author": {"name": "Test Author", "url": "https://author.example"},
            "topology": {
                "docs_base": "https://docs.smmh.dev",
                "slug": "selfdoc",
            },
        }
        builder = _make_url_builder(config)
        assert isinstance(builder, TopologyURLBuilder)
        assert builder.base() == "https://docs.smmh.dev/selfdoc"

    def test_no_topology_creates_simple_builder(self):
        from selfdoc.build import _make_url_builder
        from selfdoc.urls import SimpleURLBuilder
        config = {"base_url": "https://example.com"}
        builder = _make_url_builder(config)
        assert isinstance(builder, SimpleURLBuilder)
        assert builder.base() == "https://example.com"

    def test_topology_without_docs_base_falls_back(self):
        from selfdoc.build import _make_url_builder
        from selfdoc.urls import SimpleURLBuilder
        config = {
            "base_url": "https://example.com",
            "author": {"name": "Test Author", "url": "https://author.example"},
            "topology": {"slug": "selfdoc"},
        }
        builder = _make_url_builder(config)
        assert isinstance(builder, SimpleURLBuilder)

    def test_topology_without_slug_falls_back(self):
        from selfdoc.build import _make_url_builder
        from selfdoc.urls import SimpleURLBuilder
        config = {
            "base_url": "https://example.com",
            "author": {"name": "Test Author", "url": "https://author.example"},
            "topology": {"docs_base": "https://docs.smmh.dev"},
        }
        builder = _make_url_builder(config)
        assert isinstance(builder, SimpleURLBuilder)

    def test_no_base_url_no_topology_returns_none(self):
        from selfdoc.build import _make_url_builder
        config = {}
        builder = _make_url_builder(config)
        assert builder is None

    def test_topology_with_projects(self):
        from selfdoc.build import _make_url_builder
        config = {
            "base_url": "https://example.com",
            "author": {"name": "Test Author", "url": "https://author.example"},
            "topology": {
                "docs_base": "https://docs.smmh.dev",
                "slug": "selfdoc",
                "projects": {"rlsbl": "https://docs.smmh.dev/rlsbl"},
            },
        }
        builder = _make_url_builder(config)
        assert isinstance(builder, TopologyURLBuilder)
        assert builder.cross_project_url("rlsbl", "guide/") == "https://docs.smmh.dev/rlsbl/guide/"


class TestTopologyVarDirective:
    """Test topology-aware var directive keys."""

    def test_docs_url_with_topology(self):
        from selfdoc.content import resolve_var
        config = {
            "topology": {
                "docs_base": "https://docs.smmh.dev",
                "slug": "selfdoc",
            },
        }
        result = resolve_var({"key": "topology.docs_url"}, config, ".")
        assert result == "https://docs.smmh.dev/selfdoc"

    def test_docs_url_without_topology(self):
        from selfdoc.content import resolve_var
        result = resolve_var({"key": "topology.docs_url"}, {}, ".")
        assert result == ""

    def test_docs_url_missing_slug(self):
        from selfdoc.content import resolve_var
        config = {"topology": {"docs_base": "https://docs.smmh.dev"}}
        result = resolve_var({"key": "topology.docs_url"}, config, ".")
        assert result == ""

    def test_posts_url_with_topology(self):
        from selfdoc.content import resolve_var
        config = {
            "topology": {"posts_base": "https://docs.smmh.dev/blog"},
        }
        result = resolve_var({"key": "topology.posts_url"}, config, ".")
        assert result == "https://docs.smmh.dev/blog"

    def test_posts_url_without_topology(self):
        from selfdoc.content import resolve_var
        result = resolve_var({"key": "topology.posts_url"}, {}, ".")
        assert result == ""

    def test_slug_with_topology(self):
        from selfdoc.content import resolve_var
        config = {"topology": {"slug": "selfdoc"}}
        result = resolve_var({"key": "topology.slug"}, config, ".")
        assert result == "selfdoc"

    def test_slug_without_topology(self):
        from selfdoc.content import resolve_var
        result = resolve_var({"key": "topology.slug"}, {}, ".")
        assert result == ""
