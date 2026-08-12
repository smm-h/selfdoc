"""Tests for BuildResult dataclass."""

import pytest

from selfdoc.build import BuildResult


def _make_build_result(**overrides):
    """Create a BuildResult with default values, allowing overrides."""
    defaults = {
        "html_files": {},
        "markdown_files": {},
        "frontmatter": {},
        "page_dates": {},
        "nav_items": [],
        "project_name": "test-project",
        "version": "1.0.0",
        "config": {},
        "docs_dir": "/tmp/docs",
        "other_files": [],
        "has_custom_css": False,
        "raw_theme_css": "",
        "theme_meta": {},
        "critical_css": "",
        "config_description": "",
        "base_url": None,
        "feed_url": "",
        "lang": "en",
    }
    defaults.update(overrides)
    return BuildResult(**defaults)


class TestBuildResultConstruction:
    """Test that BuildResult can be constructed with all fields."""

    def test_all_fields(self):
        result = _make_build_result(
            html_files={"index.html": "<h1>Hi</h1>"},
            markdown_files={"index.md": "# Hi"},
            frontmatter={"index.md": {"title": "Hi"}},
            page_dates={"index.md": "2024-01-01"},
            nav_items=[{"title": "Home", "url": "/"}],
            project_name="my-project",
            version="2.5.0",
            config={"name": "my-project"},
            docs_dir="/home/user/docs",
            other_files=["logo.png"],
            has_custom_css=True,
            raw_theme_css="body { color: red; }",
            theme_meta={"name": "default"},
            critical_css="h1 { font-size: 2em; }",
            config_description="A test project",
            base_url="https://example.com",
            feed_url="https://example.com/feed.xml",
            lang="fr",
        )
        assert result.html_files == {"index.html": "<h1>Hi</h1>"}
        assert result.markdown_files == {"index.md": "# Hi"}
        assert result.frontmatter == {"index.md": {"title": "Hi"}}
        assert result.page_dates == {"index.md": "2024-01-01"}
        assert result.nav_items == [{"title": "Home", "url": "/"}]
        assert result.project_name == "my-project"
        assert result.version == "2.5.0"
        assert result.config == {"name": "my-project"}
        assert result.docs_dir == "/home/user/docs"
        assert result.other_files == ["logo.png"]
        assert result.has_custom_css is True
        assert result.raw_theme_css == "body { color: red; }"
        assert result.theme_meta == {"name": "default"}
        assert result.critical_css == "h1 { font-size: 2em; }"
        assert result.config_description == "A test project"
        assert result.base_url == "https://example.com"
        assert result.feed_url == "https://example.com/feed.xml"
        assert result.lang == "fr"

    def test_minimal_construction(self):
        result = _make_build_result()
        assert result.project_name == "test-project"
        assert result.version == "1.0.0"
        assert result.html_files == {}
        assert result.lang == "en"


class TestBuildResultFrozen:
    """Test that BuildResult is frozen (assignment raises)."""

    def test_cannot_set_attribute(self):
        result = _make_build_result()
        with pytest.raises(AttributeError):
            result.project_name = "changed"

    def test_cannot_set_html_files(self):
        result = _make_build_result()
        with pytest.raises(AttributeError):
            result.html_files = {"new.html": "content"}

    def test_cannot_set_version(self):
        result = _make_build_result()
        with pytest.raises(AttributeError):
            result.version = "9.9.9"

    def test_cannot_set_url_builder(self):
        result = _make_build_result()
        with pytest.raises(AttributeError):
            result.url_builder = object()


class TestBuildResultUrlBuilderDefault:
    """Test that url_builder defaults to None."""

    def test_url_builder_default_none(self):
        result = _make_build_result()
        assert result.url_builder is None

    def test_url_builder_explicit_value(self):
        sentinel = object()
        result = _make_build_result(url_builder=sentinel)
        assert result.url_builder is sentinel

    def test_url_builder_explicit_none(self):
        result = _make_build_result(url_builder=None)
        assert result.url_builder is None


class TestBuildResultFieldCount:
    """Verify field count matches the expected 20 fields."""

    def test_has_20_fields(self):
        import dataclasses
        fields = dataclasses.fields(BuildResult)
        assert len(fields) == 19

    def test_field_names(self):
        import dataclasses
        names = [f.name for f in dataclasses.fields(BuildResult)]
        assert names == [
            "html_files",
            "markdown_files",
            "frontmatter",
            "page_dates",
            "nav_items",
            "project_name",
            "version",
            "config",
            "docs_dir",
            "other_files",
            "has_custom_css",
            "raw_theme_css",
            "theme_meta",
            "critical_css",
            "config_description",
            "base_url",
            "feed_url",
            "lang",
            "url_builder",
        ]
