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

    def test_current_version_is_stable_and_the_older_one_is_archived(
        self, make_versioned_project,
    ):
        """Two versions: the stable tree, plus one archive tree under v/."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        assert os.path.isfile(os.path.join(output_dir, "index.html"))
        assert os.path.isfile(
            os.path.join(output_dir, "v", "0.1.0", "index.html")
        )
        # The current version has no archive copy of its own.
        assert not os.path.isdir(os.path.join(output_dir, "v", "0.2.0"))

    def test_current_version_has_no_superseded_notice(self, make_versioned_project):
        """The current version has nothing to say about being superseded."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        latest_html = _read_html(output_dir, "index.html")
        assert "version-notice" not in latest_html

    def test_archive_has_a_dismissable_notice(self, make_versioned_project):
        """An archived page says so, keyed per version, and links the current one."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        old_html = _read_html(output_dir, "v/0.1.0/index.html")
        assert 'class="version-notice"' in old_html
        assert 'data-notice-key="0.1.0"' in old_html
        assert "version-notice-dismiss" in old_html
        # The link out is document-relative, back to the stable address.
        assert 'href="../../"' in old_html

    def test_old_version_content_from_tag(self, make_versioned_project):
        """Old version should contain content from its git tag, not HEAD."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        old_html = _read_html(output_dir, "v/0.1.0/index.html")
        # The make_versioned_project fixture writes "Documentation for version X"
        assert "0.1.0" in old_html

    def test_search_index_contains_both_versions(self, make_versioned_project):
        """Every built version is indexed, under its own version filter."""
        from test_pagefind_index import _fragments

        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        versions_in_index = {
            value
            for fragment in _fragments(output_dir)
            for value in fragment["filters"].get("version", [])
        }
        assert "0.1.0" in versions_in_index
        assert "0.2.0" in versions_in_index

    def test_archive_canonical_is_the_stable_address(self, make_versioned_project):
        """An archived page canonicalizes to the version-free address."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        old_html = _read_html(output_dir, "v/0.1.0/index.html")
        canonical_match = re.search(
            r'<link rel="canonical" href="([^"]+)"', old_html,
        )
        assert canonical_match is not None
        canonical_url = canonical_match.group(1)
        assert canonical_url == "https://example.com/"

    def test_root_index_is_the_current_version_itself(self, make_versioned_project):
        """With one locale the current version mounts at the output root.

        There is no redirect stub to write: the root index is the home page.
        """
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        root_html = _read_html(output_dir, "index.html")
        assert 'meta http-equiv="refresh"' not in root_html
        assert "0.2.0" in root_html

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


class TestArchivedVersion:
    """A superseded version is an archive: no noindex, and out of the sitemap.

    The per-version ``indexed`` flag is gone.  Whether a version is an
    archive answers the same question, and an archive carries a canonical
    pointing at the stable address -- never a canonical *and* a noindex,
    which would ask a crawler to both follow the canonical and drop the
    page it points from.
    """

    @staticmethod
    def _build(make_versioned_project):
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))
        return project_dir

    def test_archive_has_no_noindex(self, make_versioned_project):
        """An archived page is canonicalized away, never noindexed."""
        project_dir = self._build(make_versioned_project)
        output_dir = os.path.join(str(project_dir), "docs", "_build")
        old_html = _read_html(output_dir, "v/0.1.0/index.html")
        assert "noindex" not in old_html

    def test_archive_canonical_is_the_stable_address(self, make_versioned_project):
        project_dir = self._build(make_versioned_project)
        output_dir = os.path.join(str(project_dir), "docs", "_build")
        old_html = _read_html(output_dir, "v/0.1.0/index.html")
        current_html = _read_html(output_dir, "index.html")
        canonical = re.search(
            r'<link rel="canonical" href="([^"]*)">', old_html,
        )
        assert canonical, old_html[:400]
        assert canonical.group(1).endswith("/")
        assert "/v/0.1.0/" not in canonical.group(1)
        assert canonical.group(1) in current_html

    def test_sitemap_lists_only_stable_addresses(self, make_versioned_project):
        project_dir = self._build(make_versioned_project)
        output_dir = os.path.join(str(project_dir), "docs", "_build")
        with open(os.path.join(output_dir, "sitemap.xml"), encoding="utf-8") as f:
            sitemap = f.read()
        assert "/v/0.1.0" not in sitemap
        assert "<loc>" in sitemap


class TestVersionFilter:
    """Tests for the --version CLI flag / version_filter parameter."""

    def test_filter_builds_only_one_version(self, make_versioned_project):
        """version_filter should build only the specified version."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        written = build(str(project_dir), version_filter="0.2.0")

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        # The current version is at the stable address
        assert os.path.isfile(os.path.join(output_dir, "index.html"))
        # Old version should NOT exist (was filtered out)
        assert not os.path.exists(os.path.join(output_dir, "v", "0.1.0"))

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
        html = _read_html(output_dir, "index.html")
        assert "version-picker" in html
        assert "v0.1.0" in html
        assert "v0.2.0" in html

    def test_version_picker_links_come_from_the_build(self, make_versioned_project):
        """Each option carries its target address, computed server-side."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        html = _read_html(output_dir, "index.html")
        hrefs = dict(re.findall(
            r'<option value="([^"]*)" data-href="([^"]*)"', html,
        ))
        assert hrefs == {"0.1.0": "v/0.1.0/", "0.2.0": "./"}

    def test_version_picker_current_selected(self, make_versioned_project):
        """Version picker should have the current version selected."""
        project_dir = make_versioned_project(["0.1.0", "0.2.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        # The archived page has its own version selected
        old_html = _read_html(output_dir, "v/0.1.0/index.html")
        assert re.search(
            r'<option value="0\.1\.0"[^>]* selected>', old_html,
        )

        # The stable page has the current version selected
        latest_html = _read_html(output_dir, "index.html")
        assert re.search(
            r'<option value="0\.2\.0"[^>]* selected>', latest_html,
        )


class TestSingleVersion:
    """Tests ensuring single-version projects still work correctly."""

    def test_single_version_has_no_superseded_notice(self, make_versioned_project):
        """The only version there is has not been superseded."""
        project_dir = make_versioned_project(["1.0.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        html = _read_html(output_dir, "index.html")
        assert "version-notice" not in html

    def test_single_version_has_no_picker(self, make_versioned_project):
        """A control with one option is not offered at all.

        The picker used to be rendered disabled; now a picker exists only
        when it can take the reader somewhere.
        """
        project_dir = make_versioned_project(["1.0.0"])
        build(str(project_dir))

        output_dir = os.path.join(str(project_dir), "docs", "_build")
        html = _read_html(output_dir, "index.html")
        assert '<select class="version-picker"' not in html


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


def test_sitemap_excludes_archived_versions(make_versioned_project):
    """The sitemap lists stable addresses only; archives canonicalize away."""
    project_dir = make_versioned_project(["0.1.0", "0.2.0"])
    build(str(project_dir))

    output_dir = os.path.join(str(project_dir), "docs", "_build")
    sitemap_path = os.path.join(output_dir, "sitemap.xml")
    assert os.path.isfile(sitemap_path)
    with open(sitemap_path, "r", encoding="utf-8") as f:
        sitemap = f.read()

    # The current version is listed at its stable, version-free address.
    assert "<loc>" in sitemap
    assert "/0.2.0/" not in sitemap
    # The archived version is not listed at all.
    assert "/v/0.1.0" not in sitemap
