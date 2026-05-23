"""Tests for multi-version build support (Phase 2)."""

import json
import os
import re

import pytest

from selfdoc.build import build, _extract_version_content
from selfdoc.config import load_config


def _read_html(output_dir, rel_path):
    """Read an HTML file from the build output directory."""
    path = os.path.join(output_dir, rel_path)
    assert os.path.isfile(path), f"Expected file not found: {rel_path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestMultiVersionBuild:
    """Tests for building a project with multiple configured versions."""

    def test_both_version_dirs_exist(self, make_versioned_project):
        """Build with 2 versions produces output directories for both."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        written = build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        assert os.path.isdir(os.path.join(output_dir, "en", "0.1.0"))
        assert os.path.isdir(os.path.join(output_dir, "en", "0.2.0"))
        # Both should have index.html
        assert os.path.isfile(
            os.path.join(output_dir, "en", "0.1.0", "index.html")
        )
        assert os.path.isfile(
            os.path.join(output_dir, "en", "0.2.0", "index.html")
        )

    def test_latest_version_no_banner(self, make_versioned_project):
        """Latest version pages should NOT have a version banner."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        latest_html = _read_html(output_dir, "en/0.2.0/index.html")
        assert "version-banner" not in latest_html

    def test_old_version_has_banner(self, make_versioned_project):
        """Old version pages should have a version banner with correct link."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        old_html = _read_html(output_dir, "en/0.1.0/index.html")
        assert "version-banner" in old_html
        assert "v0.1.0" in old_html
        assert "/en/0.2.0/" in old_html

    def test_old_version_content_from_tag(self, make_versioned_project):
        """Old version should contain content from its git tag, not HEAD."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        old_html = _read_html(output_dir, "en/0.1.0/index.html")
        # The make_versioned_project fixture writes "Documentation for version X"
        assert "0.1.0" in old_html

    def test_search_index_contains_both_versions(self, make_versioned_project):
        """Search index should contain entries from all built versions."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        search_path = os.path.join(output_dir, "search-index.json")
        assert os.path.isfile(search_path)
        with open(search_path, "r", encoding="utf-8") as f:
            entries = json.load(f)

        versions_in_index = {e["version"] for e in entries}
        assert "0.1.0" in versions_in_index
        assert "0.2.0" in versions_in_index

    def test_old_version_canonical_points_to_latest(self, make_versioned_project):
        """Old version pages should have canonical URL pointing to latest."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        old_html = _read_html(output_dir, "en/0.1.0/index.html")
        # Canonical should point to latest version's URL
        canonical_match = re.search(
            r'<link rel="canonical" href="([^"]+)"', old_html,
        )
        assert canonical_match is not None
        canonical_url = canonical_match.group(1)
        assert "/en/0.2.0/" in canonical_url

    def test_root_redirect_points_to_latest(self, make_versioned_project):
        """Root index.html should redirect to the latest version."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        root_html = _read_html(output_dir, "index.html")
        assert "/en/0.2.0/" in root_html

    def test_cache_directory_created(self, make_versioned_project):
        """Cache directory should be created for extracted versions."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        cache_dir = os.path.join(str(project_dir), ".selfdoc", "cache")
        assert os.path.isdir(cache_dir)
        # Old version should have a cache entry
        assert os.path.isdir(os.path.join(cache_dir, "0.1.0"))
        # Latest version should NOT have a cache entry (uses working tree)
        assert not os.path.isdir(os.path.join(cache_dir, "0.2.0"))

    def test_cache_gitignore_exists(self, make_versioned_project):
        """Cache directory should have .gitignore with '*'."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        gitignore = os.path.join(
            str(project_dir), ".selfdoc", "cache", ".gitignore",
        )
        assert os.path.isfile(gitignore)
        with open(gitignore, "r", encoding="utf-8") as f:
            content = f.read()
        assert "*" in content


class TestNonIndexedVersion:
    """Tests for versions with indexed: false."""

    @staticmethod
    def _build_with_indexed_config(make_versioned_project):
        """Helper: create a project where v0.1.0 is not indexed."""
        # Create the versioned project with standard tags
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        # Overwrite selfdoc.json to set indexed: false on v0.1.0
        config_path = os.path.join(str(project_dir), "selfdoc.json")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        config["versions"] = [
            {"version": "0.1.0", "indexed": False},
            {"version": "0.2.0", "indexed": True},
        ]
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f)
        build(str(project_dir))
        return project_dir

    def test_noindex_meta_tag(self, make_versioned_project):
        """Non-indexed version pages should have noindex meta tag."""
        project_dir = self._build_with_indexed_config(make_versioned_project)
        output_dir = os.path.join(str(project_dir), "docs", "_build")
        old_html = _read_html(output_dir, "en/0.1.0/index.html")
        assert 'content="noindex, nofollow"' in old_html

    def test_indexed_version_no_noindex(self, make_versioned_project):
        """Indexed version pages should NOT have noindex meta tag."""
        project_dir = self._build_with_indexed_config(make_versioned_project)
        output_dir = os.path.join(str(project_dir), "docs", "_build")
        latest_html = _read_html(output_dir, "en/0.2.0/index.html")
        assert 'content="noindex, nofollow"' not in latest_html

    def test_sitemap_excludes_non_indexed(self, make_versioned_project):
        """Sitemap should only contain pages from indexed versions."""
        project_dir = self._build_with_indexed_config(make_versioned_project)
        output_dir = os.path.join(str(project_dir), "docs", "_build")
        sitemap_path = os.path.join(output_dir, "sitemap.xml")
        assert os.path.isfile(sitemap_path)
        with open(sitemap_path, "r", encoding="utf-8") as f:
            sitemap = f.read()
        assert "en/0.1.0" not in sitemap
        assert "en/0.2.0" in sitemap


class TestVersionFilter:
    """Tests for the --version CLI flag / version_filter parameter."""

    def test_filter_builds_only_one_version(self, make_versioned_project):
        """version_filter should build only the specified version."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        written = build(str(project_dir), version_filter="0.2.0")

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        # Latest version should exist
        assert os.path.isfile(
            os.path.join(output_dir, "en", "0.2.0", "index.html")
        )
        # Old version should NOT exist (was filtered out)
        assert not os.path.exists(
            os.path.join(output_dir, "en", "0.1.0")
        )

    def test_filter_invalid_version_raises(self, make_versioned_project):
        """version_filter with non-existent version should raise."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        with pytest.raises(RuntimeError, match="not found in config"):
            build(str(project_dir), version_filter="9.9.9")


class TestExtractVersionContent:
    """Tests for the _extract_version_content helper."""

    def test_extracts_docs_from_tag(self, make_versioned_project):
        """Extraction should populate cache with docs from the tag."""
        project_dir = make_versioned_project(["0.1.0"])
        config = load_config(str(project_dir))
        cache_dir = _extract_version_content(
            "0.1.0", config, str(project_dir),
        )

        assert os.path.isdir(cache_dir)
        index_md = os.path.join(cache_dir, "docs", "index.md")
        assert os.path.isfile(index_md)
        with open(index_md, "r", encoding="utf-8") as f:
            content = f.read()
        assert "0.1.0" in content

    def test_cache_reuse_on_same_hash(self, make_versioned_project):
        """Second extraction should skip if tag points to same commit."""
        project_dir = make_versioned_project(["0.1.0"])
        config = load_config(str(project_dir))

        # First extraction
        cache_dir = _extract_version_content(
            "0.1.0", config, str(project_dir),
        )
        hash_file = os.path.join(cache_dir, ".hash")
        mtime1 = os.path.getmtime(hash_file)

        # Second extraction -- should reuse cache
        cache_dir2 = _extract_version_content(
            "0.1.0", config, str(project_dir),
        )
        mtime2 = os.path.getmtime(hash_file)

        assert cache_dir == cache_dir2
        assert mtime1 == mtime2  # hash file not rewritten

    def test_missing_tag_raises(self, make_versioned_project):
        """Extraction with non-existent tag should raise RuntimeError."""
        project_dir = make_versioned_project(["0.1.0"])
        config = load_config(str(project_dir))

        with pytest.raises(RuntimeError, match="not found"):
            _extract_version_content("9.9.9", config, str(project_dir))


class TestVersionPicker:
    """Tests for the version picker in the topbar."""

    def test_version_picker_has_options(self, make_versioned_project):
        """Version picker should list all configured versions."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        html = _read_html(output_dir, "en/0.2.0/index.html")
        assert "version-picker" in html
        assert "v0.1.0" in html
        assert "v0.2.0" in html

    def test_version_picker_current_selected(self, make_versioned_project):
        """Version picker should have the current version selected."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        # Check old version page
        old_html = _read_html(output_dir, "en/0.1.0/index.html")
        # The 0.1.0 option should be selected
        assert re.search(
            r'<option value="0\.1\.0" selected>',
            old_html,
        )

        # Check latest version page
        latest_html = _read_html(output_dir, "en/0.2.0/index.html")
        assert re.search(
            r'<option value="0\.2\.0" selected>',
            latest_html,
        )


class TestSingleVersion:
    """Tests ensuring single-version projects still work correctly."""

    def test_single_version_no_banner(self, make_versioned_project):
        """Single-version project should have no version banner."""
        project_dir = make_versioned_project(["1.0.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        html = _read_html(output_dir, "en/1.0.0/index.html")
        assert "version-banner" not in html

    def test_single_version_picker_disabled(self, make_versioned_project):
        """Single-version project should have a disabled version picker."""
        project_dir = make_versioned_project(["1.0.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        html = _read_html(output_dir, "en/1.0.0/index.html")
        assert "version-picker" in html
        assert "disabled" in html


class TestCheckValidatesAllVersions:
    """Tests for check_docs validating old versions."""

    def test_check_validates_all_versions(self, make_versioned_project):
        """check_docs should validate directives in old versions too."""
        from selfdoc.check import check_docs

        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        config = load_config(str(project_dir))

        result = check_docs(str(project_dir), config=config, dry_run=True)

        # Lints from the old version should be prefixed with [0.1.0]
        all_files = (
            [dr.file for dr in result.directive_results]
            + [lint.file for lint in result.lints]
        )
        has_old_version = any("[0.1.0]" in f for f in all_files)
        assert has_old_version, (
            f"Expected results from [0.1.0] but got: {all_files}"
        )


def test_sitemap_excludes_non_indexed_version(make_versioned_project):
    """Sitemap should exclude pages from non-indexed versions."""
    project_dir = make_versioned_project(["0.1.0", "0.2.0"])

    # Overwrite config to set indexed: false on v0.1.0
    config_path = os.path.join(str(project_dir), "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["versions"] = [
        {"version": "0.1.0", "indexed": False},
        {"version": "0.2.0", "indexed": True},
    ]
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(str(project_dir), "docs", "_build")
    sitemap_path = os.path.join(output_dir, "sitemap.xml")
    assert os.path.isfile(sitemap_path)
    with open(sitemap_path, "r", encoding="utf-8") as f:
        sitemap = f.read()

    # Pages from the indexed version ARE in the sitemap
    assert "en/0.2.0" in sitemap
    # Pages from the non-indexed version are NOT in the sitemap
    assert "en/0.1.0" not in sitemap
