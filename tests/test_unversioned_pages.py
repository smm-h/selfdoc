"""Tests for Phase 2 Task 2.1: unversioned page partitioning."""

import json
import os

import pytest

from selfdoc.build import (
    build,
    build_single,
    _partition_pages,
    _check_reserved_page_paths,
)
from conftest import default_config


def _write_md(project_dir, rel_path, content):
    """Write a markdown file under docs/."""
    full_path = project_dir / "docs" / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)


def _make_config(project_dir, **overrides):
    """Load config dict from a project directory, applying overrides."""
    cfg = default_config(docs="docs/", output="docs/_build/", **overrides)
    config_path = project_dir / "selfdoc.json"
    config_path.write_text(json.dumps(cfg, indent=2))
    return cfg


def _setup_project(tmp_path, **config_overrides):
    """Create a minimal selfdoc project and return (project_dir, config)."""
    project_dir = tmp_path / "project"
    project_dir.mkdir(exist_ok=True)

    # Minimal Python source file (needed by resolver)
    src_dir = project_dir / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "__init__.py").write_text('"""Example package."""\n')

    # Default docs/index.md
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "index.md").write_text("# Test Project\n\nWelcome.\n")

    config = _make_config(project_dir, **config_overrides)
    return project_dir, config


# --- _partition_pages tests ---


def test_partition_pages_default_versioned(tmp_path):
    """All pages without 'versioned: false' go into the versioned set."""
    project_dir, config = _setup_project(tmp_path)
    _write_md(project_dir, "guide.md", "# Guide\n\nSome guide.\n")

    docs_dir = str(project_dir / "docs")
    versioned, unversioned, uv_md, uv_fm, _site = _partition_pages(
        config, docs_dir, str(project_dir),
    )

    assert len(versioned) == 2  # index.md + guide.md
    assert len(unversioned) == 0
    assert uv_md == {}
    assert uv_fm == {}


def test_partition_pages_with_unversioned(tmp_path):
    """A page with 'versioned: false' goes into the unversioned set."""
    project_dir, config = _setup_project(tmp_path)
    _write_md(
        project_dir,
        "about.md",
        "---\ntitle: About\nversioned: false\n---\n\n# About\n\nUnversioned.\n",
    )

    docs_dir = str(project_dir / "docs")
    versioned, unversioned, uv_md, uv_fm, _site = _partition_pages(
        config, docs_dir, str(project_dir),
    )

    assert "about.md" in unversioned
    assert "about.md" not in versioned
    assert "index.md" in versioned
    assert "index.md" not in unversioned
    # Unversioned markdown and frontmatter are populated
    assert "about.md" in uv_md
    assert uv_fm["about.md"]["versioned"] is False


def test_partition_pages_explicit_true(tmp_path):
    """A page with 'versioned: true' is versioned (same as default)."""
    project_dir, config = _setup_project(tmp_path)
    _write_md(
        project_dir,
        "guide.md",
        "---\ntitle: Guide\nversioned: true\n---\n\n# Guide\n\nVersioned.\n",
    )

    docs_dir = str(project_dir / "docs")
    versioned, unversioned, uv_md, uv_fm, _site = _partition_pages(
        config, docs_dir, str(project_dir),
    )

    assert "guide.md" in versioned
    assert "guide.md" not in unversioned


# --- build() output path tests ---


def test_unversioned_page_output_path(tmp_path):
    """Both the current version and an unversioned page sit at the stable mount.

    With one locale there is no locale segment and the current version
    carries no version segment, so a single-locale project's pages are at
    the output root.
    """
    project_dir, _config = _setup_project(tmp_path)
    _write_md(
        project_dir,
        "about.md",
        "---\ntitle: About\nversioned: false\n---\n\n# About\n\nUnversioned.\n",
    )

    written = build(str(project_dir))
    output_dir = str(project_dir / "docs" / "_build")

    current_path = os.path.join(output_dir, "index.html")
    assert current_path in written, f"Expected {current_path} in written"
    assert os.path.isfile(current_path)

    unversioned_path = os.path.join(output_dir, "about", "index.html")
    assert unversioned_path in written, f"Expected {unversioned_path} in written"
    assert os.path.isfile(unversioned_path)


def test_versioned_page_is_not_also_emitted_under_the_archive_prefix(tmp_path):
    """The only version in the project is the current one: no archive tree."""
    project_dir, _config = _setup_project(tmp_path)
    _write_md(
        project_dir,
        "guide.md",
        "---\ntitle: Guide\n---\n\n# Guide\n\nVersioned guide.\n",
    )

    written = build(str(project_dir))
    output_dir = str(project_dir / "docs" / "_build")

    stable_path = os.path.join(output_dir, "guide", "index.html")
    assert stable_path in written
    assert not os.path.isdir(os.path.join(output_dir, "v"))


# --- reserved page path tests ---


def test_archive_prefix_is_reserved():
    """A top-level page named `v` would collide with the archive tree."""
    with pytest.raises(RuntimeError, match="reserved top-level path 'v'"):
        _check_reserved_page_paths({"v.md"})
    with pytest.raises(RuntimeError, match="reserved top-level path 'v'"):
        _check_reserved_page_paths({"v/notes.md"})


def test_posts_prefix_is_reserved():
    """A top-level page named `blog` would collide with the post tree."""
    with pytest.raises(RuntimeError, match="reserved top-level path 'blog'"):
        _check_reserved_page_paths({"blog.md"})


def test_ordinary_pages_are_not_reserved():
    """A version-shaped directory name is fine: versions live under v/."""
    _check_reserved_page_paths({
        "about.md", "help/faq.md", "1.0.0/guide.md", "versions.md",
    })


# --- full build edge cases ---


def test_all_pages_unversioned(tmp_path):
    """When ALL pages have 'versioned: false', the versioned build is empty."""
    project_dir, _config = _setup_project(tmp_path)
    # Overwrite default index.md to be unversioned
    _write_md(
        project_dir,
        "index.md",
        "---\ntitle: Home\nversioned: false\n---\n\n# Home\n\nUnversioned home.\n",
    )

    written = build(str(project_dir))
    output_dir = str(project_dir / "docs" / "_build")

    # The unversioned page is at the stable mount, which for a
    # single-locale project is the output root.
    assert os.path.join(output_dir, "index.html") in written
    # No archive tree: the only version is the current one.
    assert not os.path.isdir(os.path.join(output_dir, "v"))


def test_no_version_segment_anywhere_for_a_single_version_project(tmp_path):
    """The current version's pages carry no version segment at all."""
    project_dir, _config = _setup_project(tmp_path)
    _write_md(
        project_dir,
        "guide.md",
        "---\ntitle: Guide\n---\n\n# Guide\n\nVersioned guide.\n",
    )

    written = build(str(project_dir))
    output_dir = str(project_dir / "docs" / "_build")

    assert os.path.join(output_dir, "index.html") in written
    assert os.path.join(output_dir, "guide", "index.html") in written

    for path in (p for p in written if p.endswith(".html")):
        rel = os.path.relpath(path, output_dir)
        parts = rel.split(os.sep)
        assert "1.0.0" not in parts, f"version segment in {rel}"
        assert "en" not in parts, f"locale segment in {rel}"


# --- build_single page_filter tests ---


def test_page_filter_in_build_single(tmp_path):
    """build_single with page_filter only includes filtered pages."""
    project_dir, config = _setup_project(tmp_path)
    _write_md(
        project_dir,
        "guide.md",
        "---\ntitle: Guide\n---\n\n# Guide\n\nFiltered guide.\n",
    )

    result = build_single(
        dir_path=str(project_dir),
        config=config,
        page_filter={"index.md"},
    )

    assert "index.md" in result.markdown_files
    assert "guide.md" not in result.markdown_files
    # html_files should only contain the filtered page
    html_keys = set(result.html_files.keys())
    for k in html_keys:
        assert "guide" not in k, f"Filtered-out page appeared in html_files: {k}"


def test_page_filter_empty_set(tmp_path):
    """build_single with empty page_filter returns empty BuildResult."""
    project_dir, config = _setup_project(tmp_path)

    result = build_single(
        dir_path=str(project_dir),
        config=config,
        page_filter=set(),
    )

    assert result.html_files == {}
    assert result.markdown_files == {}
    assert result.frontmatter == {}
    assert result.nav_items == []
    assert result.search_entries == []
