"""Tests for multi-locale build support (Phase 3)."""

import json
import os
import re

import pytest

from selfdoc.build import build
from selfdoc.config import load_config


def _read_file(output_dir, rel_path):
    """Read a file from the build output directory."""
    path = os.path.join(output_dir, rel_path)
    assert os.path.isfile(path), f"Expected file not found: {rel_path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestMultiLocaleBuild:
    """Tests for building a project with multiple configured locales."""

    def test_both_locale_dirs_exist(self, make_localized_project):
        """Build with 2 locales produces output directories for both."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)
        written = build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        # Two locales keep the locale segment; the current version drops
        # the version segment.
        assert os.path.isdir(os.path.join(output_dir, "en"))
        assert os.path.isdir(os.path.join(output_dir, "fa"))
        assert os.path.isfile(os.path.join(output_dir, "en", "index.html"))
        assert os.path.isfile(os.path.join(output_dir, "fa", "index.html"))

    def test_locale_content_from_correct_source(self, make_localized_project):
        """Each locale's output contains content from its source directory."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        en_html = _read_file(output_dir, "en/index.html")
        fa_html = _read_file(output_dir, "fa/index.html")

        # English content should contain "English" label text
        assert "English" in en_html
        # Persian content should contain "Persian" label text
        assert "Persian" in fa_html

    def test_hreflang_tags_present(self, make_localized_project):
        """hreflang tags are present when multiple locales exist."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        en_html = _read_file(output_dir, "en/index.html")

        # Should have hreflang for each locale
        assert 'hreflang="en"' in en_html
        assert 'hreflang="fa"' in en_html

    def test_hreflang_xdefault_points_to_default(self, make_localized_project):
        """hreflang x-default points to the default locale."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        en_html = _read_file(output_dir, "en/index.html")

        # x-default should exist and point to the default locale (en)
        xdefault_match = re.search(
            r'hreflang="x-default" href="([^"]+)"', en_html,
        )
        assert xdefault_match is not None
        assert "/en/" in xdefault_match.group(1)

    def test_per_locale_sitemaps_exist(self, make_localized_project):
        """Per-locale sitemap.xml files exist when multiple locales."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        assert os.path.isfile(os.path.join(output_dir, "en", "sitemap.xml"))
        assert os.path.isfile(os.path.join(output_dir, "fa", "sitemap.xml"))

    def test_sitemap_index_exists(self, make_localized_project):
        """sitemap-index.xml exists at root when multiple locales."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        sitemap_index_path = os.path.join(output_dir, "sitemap-index.xml")
        assert os.path.isfile(sitemap_index_path)

        content = _read_file(output_dir, "sitemap-index.xml")
        assert "en/sitemap.xml" in content
        assert "fa/sitemap.xml" in content

    def test_robots_txt_references_sitemap_index(self, make_localized_project):
        """robots.txt references sitemap-index.xml when multiple locales."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        robots = _read_file(output_dir, "robots.txt")
        assert "sitemap-index.xml" in robots

    def test_search_index_contains_both_locales(self, make_localized_project):
        """Search index contains entries from all built locales."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        search_path = os.path.join(output_dir, "search-index.json")
        assert os.path.isfile(search_path)
        with open(search_path, "r", encoding="utf-8") as f:
            entries = json.load(f)

        locales_in_index = {e["locale"] for e in entries}
        assert "en" in locales_in_index
        assert "fa" in locales_in_index

    def test_locale_picker_has_both_options(self, make_localized_project):
        """Locale picker in the topbar has options for both locales."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        en_html = _read_file(output_dir, "en/index.html")
        assert "locale-picker" in en_html
        assert "English" in en_html
        assert "Persian" in en_html


class TestSingleLocaleBackwardCompat:
    """Tests ensuring single-locale projects without locale dirs still work."""

    def test_single_locale_no_locale_subdir(self, make_project):
        """Single-locale project with docs/ (no locale subdir) builds normally."""
        project_dir = make_project()
        written = build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        # One locale and one version: the page is the root index.
        assert os.path.isfile(os.path.join(output_dir, "index.html"))

    def test_single_locale_no_hreflang(self, make_project):
        """Single-locale project should not have hreflang tags."""
        project_dir = make_project()
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        html = _read_file(output_dir, "index.html")
        assert "hreflang" not in html

    def test_single_locale_no_sitemap_index(self, make_project):
        """Single-locale project should not have sitemap-index.xml."""
        project_dir = make_project()
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        assert not os.path.isfile(
            os.path.join(output_dir, "sitemap-index.xml")
        )

    def test_single_locale_robots_references_sitemap(self, make_project):
        """Single-locale project robots.txt references sitemap.xml (not index)."""
        project_dir = make_project()
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        robots = _read_file(output_dir, "robots.txt")
        assert "sitemap.xml" in robots
        assert "sitemap-index.xml" not in robots


class TestLocaleFilter:
    """Tests for the --locale build flag."""

    def test_filter_builds_only_one_locale(self, make_localized_project):
        """locale_filter should build only the specified locale."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)
        written = build(str(project_dir), locale_filter="en")

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        assert os.path.isfile(os.path.join(output_dir, "en", "index.html"))
        # Other locale should NOT exist
        assert not os.path.exists(os.path.join(output_dir, "fa"))

    def test_filter_invalid_locale_raises(self, make_localized_project):
        """locale_filter with non-existent locale should raise."""
        locales = [
            {"code": "en", "label": "English", "default": True},
        ]
        project_dir = make_localized_project(locales)
        with pytest.raises(RuntimeError, match="not found in config"):
            build(str(project_dir), locale_filter="xx")


class TestMissingLocaleDir:
    """Tests for declared-but-missing locale directories."""

    def test_missing_locale_dir_raises(self, make_localized_project):
        """Missing locale directory (declared but not created) is a hard error."""
        locales = [
            {"code": "en", "label": "English", "default": True},
            {"code": "fa", "label": "Persian"},
        ]
        project_dir = make_localized_project(locales)

        # Remove the Persian locale directory
        import shutil
        fa_dir = os.path.join(str(project_dir), "docs", "fa")
        if os.path.isdir(fa_dir):
            shutil.rmtree(fa_dir)

        with pytest.raises(RuntimeError, match="Locale directory"):
            build(str(project_dir))
