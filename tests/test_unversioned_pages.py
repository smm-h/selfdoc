"""Tests for Phase 2 Task 2.1: unversioned page partitioning."""

import json
import os

import pytest

from selfdoc.build import (
    build,
    build_single,
    _partition_pages,
    _check_unversioned_collisions,
    _check_reserved_paths,
)
from conftest import default_config, DEFAULT_PREFIX


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
    versioned, unversioned, uv_md, uv_fm = _partition_pages(
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
    versioned, unversioned, uv_md, uv_fm = _partition_pages(
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
    versioned, unversioned, uv_md, uv_fm = _partition_pages(
        config, docs_dir, str(project_dir),
    )

    assert "guide.md" in versioned
    assert "guide.md" not in unversioned


# --- build() output path tests ---


def test_unversioned_page_output_path(tmp_path):
    """Unversioned page outputs to en/about/, versioned to en/1.0.0/."""
    project_dir, _config = _setup_project(tmp_path)
    _write_md(
        project_dir,
        "about.md",
        "---\ntitle: About\nversioned: false\n---\n\n# About\n\nUnversioned.\n",
    )

    written = build(str(project_dir))
    output_dir = str(project_dir / "docs" / "_build")

    # Versioned page at en/1.0.0/index.html
    versioned_path = os.path.join(output_dir, "en", "1.0.0", "index.html")
    assert versioned_path in written, f"Expected versioned path {versioned_path} in written"
    assert os.path.isfile(versioned_path)

    # Unversioned page at en/about/index.html (no version segment)
    unversioned_path = os.path.join(output_dir, "en", "about", "index.html")
    assert unversioned_path in written, f"Expected unversioned path {unversioned_path} in written"
    assert os.path.isfile(unversioned_path)


def test_versioned_page_not_at_unversioned_path(tmp_path):
    """Versioned pages do NOT output to en/page/ (only en/1.0.0/page/)."""
    project_dir, _config = _setup_project(tmp_path)
    _write_md(
        project_dir,
        "guide.md",
        "---\ntitle: Guide\n---\n\n# Guide\n\nVersioned guide.\n",
    )

    written = build(str(project_dir))
    output_dir = str(project_dir / "docs" / "_build")

    # Versioned page exists at en/1.0.0/guide/index.html
    versioned_path = os.path.join(output_dir, "en", "1.0.0", "guide", "index.html")
    assert versioned_path in written

    # Should NOT exist at en/guide/index.html (that would be an unversioned path)
    unversioned_path = os.path.join(output_dir, "en", "guide", "index.html")
    assert unversioned_path not in written
    assert not os.path.isfile(unversioned_path)


# --- collision detection tests ---


def test_collision_error(tmp_path):
    """Unversioned page in a version-named directory triggers collision error."""
    unversioned_paths = {"1.0.0/guide.md"}
    version_strs = ["1.0.0"]

    with pytest.raises(RuntimeError, match="collide"):
        _check_unversioned_collisions(unversioned_paths, version_strs)


def test_no_collision_when_different_dir(tmp_path):
    """Unversioned pages not in version-named dirs do not collide."""
    unversioned_paths = {"about.md", "help/faq.md"}
    version_strs = ["1.0.0"]

    # Should not raise
    _check_unversioned_collisions(unversioned_paths, version_strs)


# --- reserved path tests ---


def test_reserved_path_collision():
    """Version string matching posts listing_path triggers reserved path error."""
    config = {"posts": {"listing_path": "posts"}}
    version_strs = ["posts"]

    with pytest.raises(RuntimeError, match="reserved URL"):
        _check_reserved_paths(version_strs, config)


def test_reserved_path_no_collision():
    """Normal version strings do not conflict with posts."""
    config = {"posts": {"listing_path": "posts"}}
    version_strs = ["1.0.0", "2.0.0"]

    # Should not raise
    _check_reserved_paths(version_strs, config)


# --- full build edge cases ---


def test_all_pages_unversioned(tmp_path):
    """When ALL pages have 'versioned: false', versioned build returns empty."""
    project_dir, _config = _setup_project(tmp_path)
    # Overwrite default index.md to be unversioned
    _write_md(
        project_dir,
        "index.md",
        "---\ntitle: Home\nversioned: false\n---\n\n# Home\n\nUnversioned home.\n",
    )

    written = build(str(project_dir))
    output_dir = str(project_dir / "docs" / "_build")

    # Unversioned page at en/index.html
    unversioned_index = os.path.join(output_dir, "en", "index.html")
    assert unversioned_index in written

    # There should be no content at en/1.0.0/index.html (versioned build
    # returned empty because all pages are unversioned)
    versioned_index = os.path.join(output_dir, "en", "1.0.0", "index.html")
    assert versioned_index not in written


def test_build_with_no_unversioned_pages_unchanged(tmp_path):
    """With no unversioned pages, output is identical to pre-Phase-2."""
    project_dir, _config = _setup_project(tmp_path)
    _write_md(
        project_dir,
        "guide.md",
        "---\ntitle: Guide\n---\n\n# Guide\n\nVersioned guide.\n",
    )

    written = build(str(project_dir))
    output_dir = str(project_dir / "docs" / "_build")

    # All pages at en/1.0.0/
    versioned_index = os.path.join(output_dir, "en", "1.0.0", "index.html")
    versioned_guide = os.path.join(output_dir, "en", "1.0.0", "guide", "index.html")
    assert versioned_index in written
    assert versioned_guide in written

    # No unversioned outputs (no en/<page> without version segment,
    # except shared assets like style.css and the root redirect)
    html_paths = [p for p in written if p.endswith(".html")]
    for p in html_paths:
        rel = os.path.relpath(p, output_dir)
        parts = rel.split(os.sep)
        # Every HTML page should be under en/1.0.0/ or be a root redirect
        if parts[0] == "en" and len(parts) > 1:
            assert parts[1] == "1.0.0" or rel == os.path.join("en", "index.html"), (
                f"Unexpected HTML at non-versioned path: {rel}"
            )


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
