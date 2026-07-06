"""Tests for post injection in unified and single-project builds.

Verifies that:
1. Constituent project posts are injected in unified builds.
2. Cleanup happens even if the build fails (try/finally).
"""

import json
import os
from unittest.mock import MagicMock, call, patch

import pytest

from conftest import _git, _write_json, _write_text


# -- Helpers --

def _minimal_config(docs="docs/", output="site/", **extra):
    """Return a minimal selfdoc.json config dict."""
    cfg = {
        "source": [{"path": "src/", "language": "python"}],
        "docs": docs,
        "output": output,
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0", "indexed": True}],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }
    cfg.update(extra)
    return cfg


def _setup_constituent_project(path, has_posts_dir=False):
    """Create a minimal constituent project directory with selfdoc.json."""
    os.makedirs(os.path.join(path, "docs"), exist_ok=True)
    os.makedirs(os.path.join(path, "src"), exist_ok=True)
    _write_text(
        os.path.join(path, "src", "lib.py"),
        "def hello():\n    pass\n",
    )
    _write_text(
        os.path.join(path, "docs", "index.md"),
        "---\ntitle: Index\n---\n# Hello\n",
    )
    config = _minimal_config()
    del config["versions"]
    del config["locales"]
    del config["base_url"]
    config["version"] = "0.1.0"
    if has_posts_dir:
        config["posts"] = {"dir": ".selfdoc/posts/"}
        posts_dir = os.path.join(path, ".selfdoc", "posts")
        os.makedirs(posts_dir, exist_ok=True)
    _write_json(os.path.join(path, "selfdoc.json"), config)
    return config


# -- Tests for constituent project post injection in unified builds --


@patch("selfblog.unified._build_unified_body")
@patch("selfblog.unified._cleanup_injected_posts")
@patch("selfblog.unified._inject_posts_into_docs")
@patch("selfblog.unified._partition_pages")
@patch("selfblog.unified.load_config")
def test_constituent_posts_injected(
    mock_load_config, mock_partition, mock_inject, mock_cleanup,
    mock_body, tmp_path,
):
    """_inject_posts_into_docs is called for each constituent project."""
    from selfdoc.unified import build_unified

    # Set up docs-site
    docs_site = tmp_path / "docs-site"
    docs_site.mkdir()
    os.makedirs(str(docs_site / "docs"), exist_ok=True)
    _write_text(str(docs_site / "docs" / "index.md"), "# Main\n")
    os.makedirs(str(docs_site / "site"), exist_ok=True)
    os.makedirs(str(docs_site / "src"), exist_ok=True)
    _write_text(str(docs_site / "src" / "lib.py"), "")

    # Set up constituent project
    proj_a = tmp_path / "proj-a"
    proj_a.mkdir()
    _setup_constituent_project(str(proj_a), has_posts_dir=True)

    proj_b = tmp_path / "proj-b"
    proj_b.mkdir()
    _setup_constituent_project(str(proj_b), has_posts_dir=False)

    # Docs-site config
    config = _minimal_config(
        unified={
            "projects": [
                {"path": "../proj-a"},
                {"path": "../proj-b"},
            ],
        },
    )

    # Mock load_config to return real configs
    proj_a_config = _minimal_config()
    proj_b_config = _minimal_config()

    def fake_load_config(path):
        path = os.path.normpath(path)
        if path == os.path.normpath(str(proj_a)):
            return proj_a_config
        if path == os.path.normpath(str(proj_b)):
            return proj_b_config
        return None

    mock_load_config.side_effect = fake_load_config

    # Mock _inject_posts_into_docs to return dummy files
    def fake_inject(dir_path, cfg, docs_dir, include_drafts):
        dir_path = os.path.normpath(dir_path)
        if dir_path == os.path.normpath(str(proj_a)):
            return [os.path.join(docs_dir, "posts", "post1.md")]
        if dir_path == os.path.normpath(str(proj_b)):
            return []
        # docs-site itself
        return [os.path.join(docs_dir, "posts", "main-post.md")]

    mock_inject.side_effect = fake_inject

    # Mock _partition_pages to return empty partitions
    mock_partition.return_value = (set(), set(), {}, {})

    # Mock body to return empty dict
    mock_body.return_value = {}

    build_unified(str(docs_site), config=config, include_drafts=False)

    # Verify _inject_posts_into_docs was called for proj-a
    inject_calls = mock_inject.call_args_list
    called_dirs = [
        os.path.normpath(c[0][0]) for c in inject_calls
    ]
    assert os.path.normpath(str(proj_a)) in called_dirs, (
        f"Expected proj-a inject call, got dirs: {called_dirs}"
    )
    # Verify _inject_posts_into_docs was called for proj-b
    assert os.path.normpath(str(proj_b)) in called_dirs, (
        f"Expected proj-b inject call, got dirs: {called_dirs}"
    )
    # Verify _inject_posts_into_docs was called for docs-site
    assert os.path.normpath(str(docs_site)) in called_dirs, (
        f"Expected docs-site inject call, got dirs: {called_dirs}"
    )
    # 3 calls total: proj-a, proj-b, docs-site
    assert len(inject_calls) == 3


@patch("selfblog.unified._build_unified_body")
@patch("selfblog.unified._cleanup_injected_posts")
@patch("selfblog.unified._inject_posts_into_docs")
@patch("selfblog.unified._partition_pages")
@patch("selfblog.unified.load_config")
def test_constituent_posts_cleaned_up(
    mock_load_config, mock_partition, mock_inject, mock_cleanup,
    mock_body, tmp_path,
):
    """Cleanup is called for all projects with injected files."""
    from selfdoc.unified import build_unified

    docs_site = tmp_path / "docs-site"
    docs_site.mkdir()
    os.makedirs(str(docs_site / "docs"), exist_ok=True)
    os.makedirs(str(docs_site / "site"), exist_ok=True)
    os.makedirs(str(docs_site / "src"), exist_ok=True)
    _write_text(str(docs_site / "src" / "lib.py"), "")

    proj_a = tmp_path / "proj-a"
    proj_a.mkdir()
    _setup_constituent_project(str(proj_a))

    config = _minimal_config(
        unified={
            "projects": [{"path": "../proj-a"}],
        },
    )

    proj_a_config = _minimal_config()

    def fake_load_config(path):
        path = os.path.normpath(path)
        if path == os.path.normpath(str(proj_a)):
            return proj_a_config
        return None

    mock_load_config.side_effect = fake_load_config

    proj_a_docs = os.path.join(str(proj_a), "docs")
    ds_docs = os.path.join(str(docs_site), "docs")

    def fake_inject(dir_path, cfg, docs_dir, include_drafts):
        dir_path = os.path.normpath(dir_path)
        if dir_path == os.path.normpath(str(proj_a)):
            return [os.path.join(proj_a_docs, "posts", "p1.md")]
        return [os.path.join(ds_docs, "posts", "main.md")]

    mock_inject.side_effect = fake_inject
    mock_partition.return_value = (set(), set(), {}, {})
    mock_body.return_value = {}

    build_unified(str(docs_site), config=config)

    # Cleanup should have been called for both proj-a and docs-site
    cleanup_calls = mock_cleanup.call_args_list
    assert len(cleanup_calls) == 2

    cleaned_dirs = [os.path.normpath(c[0][1]) for c in cleanup_calls]
    assert os.path.normpath(proj_a_docs) in cleaned_dirs
    assert os.path.normpath(ds_docs) in cleaned_dirs


# -- Tests for try/finally cleanup on build failure --


@patch("selfblog.unified._build_unified_body")
@patch("selfblog.unified._cleanup_injected_posts")
@patch("selfblog.unified._inject_posts_into_docs")
@patch("selfblog.unified._partition_pages")
@patch("selfblog.unified.load_config")
def test_unified_cleanup_on_build_failure(
    mock_load_config, mock_partition, mock_inject, mock_cleanup,
    mock_body, tmp_path,
):
    """Cleanup happens even when the build body raises an exception."""
    from selfdoc.unified import build_unified

    docs_site = tmp_path / "docs-site"
    docs_site.mkdir()
    os.makedirs(str(docs_site / "docs"), exist_ok=True)
    os.makedirs(str(docs_site / "site"), exist_ok=True)
    os.makedirs(str(docs_site / "src"), exist_ok=True)
    _write_text(str(docs_site / "src" / "lib.py"), "")

    config = _minimal_config(
        unified={"projects": []},
    )

    ds_docs = os.path.join(str(docs_site), "docs")

    def fake_inject(dir_path, cfg, docs_dir, include_drafts):
        return [os.path.join(ds_docs, "posts", "post.md")]

    mock_inject.side_effect = fake_inject
    mock_partition.return_value = (set(), set(), {}, {})

    # Make the build body raise
    mock_body.side_effect = RuntimeError("Build failed!")

    with pytest.raises(RuntimeError, match="Build failed!"):
        build_unified(str(docs_site), config=config)

    # Cleanup MUST still be called despite the exception
    assert mock_cleanup.call_count == 1
    cleanup_files, cleanup_dir = mock_cleanup.call_args[0]
    assert cleanup_files == [os.path.join(ds_docs, "posts", "post.md")]
    assert os.path.normpath(cleanup_dir) == os.path.normpath(ds_docs)


@patch("selfdoc_core.build._build_body")
@patch("selfdoc_core.build._cleanup_injected_posts")
@patch("selfdoc_core.build._inject_posts_into_docs")
@patch("selfdoc_core.build._partition_pages")
@patch("selfdoc_core.build._check_unversioned_collisions")
@patch("selfdoc_core.build._check_reserved_paths")
def test_build_cleanup_on_failure(
    mock_reserved, mock_collisions, mock_partition, mock_inject,
    mock_cleanup, mock_body, tmp_path,
):
    """build() cleans up injected posts even when _build_body raises."""
    from selfdoc.build import build

    project = tmp_path / "project"
    project.mkdir()
    os.makedirs(str(project / "docs"), exist_ok=True)
    os.makedirs(str(project / "site"), exist_ok=True)
    os.makedirs(str(project / "src"), exist_ok=True)
    _write_text(str(project / "src" / "lib.py"), "")

    config = _minimal_config()

    latest_docs = os.path.join(str(project), "docs")

    def fake_inject(dir_path, cfg, docs_dir, include_drafts):
        return [os.path.join(latest_docs, "posts", "post.md")]

    mock_inject.side_effect = fake_inject
    mock_partition.return_value = (set(), set(), {}, {})
    mock_body.side_effect = RuntimeError("Build exploded!")

    with pytest.raises(RuntimeError, match="Build exploded!"):
        build(str(project), config=config)

    # Cleanup MUST still be called
    assert mock_cleanup.call_count == 1
    cleanup_files, cleanup_dir = mock_cleanup.call_args[0]
    assert cleanup_files == [os.path.join(latest_docs, "posts", "post.md")]


@patch("selfdoc_core.build._build_body")
@patch("selfdoc_core.build._cleanup_injected_posts")
@patch("selfdoc_core.build._inject_posts_into_docs")
@patch("selfdoc_core.build._partition_pages")
@patch("selfdoc_core.build._check_unversioned_collisions")
@patch("selfdoc_core.build._check_reserved_paths")
def test_build_cleanup_on_success(
    mock_reserved, mock_collisions, mock_partition, mock_inject,
    mock_cleanup, mock_body, tmp_path,
):
    """build() cleans up injected posts on successful build too."""
    from selfdoc.build import build

    project = tmp_path / "project"
    project.mkdir()
    os.makedirs(str(project / "docs"), exist_ok=True)
    os.makedirs(str(project / "site"), exist_ok=True)
    os.makedirs(str(project / "src"), exist_ok=True)
    _write_text(str(project / "src" / "lib.py"), "")

    config = _minimal_config()

    latest_docs = os.path.join(str(project), "docs")

    def fake_inject(dir_path, cfg, docs_dir, include_drafts):
        return [os.path.join(latest_docs, "posts", "post.md")]

    mock_inject.side_effect = fake_inject
    mock_partition.return_value = (set(), set(), {}, {})
    mock_body.return_value = {"some_file": True}

    result = build(str(project), config=config)

    assert result == {"some_file": True}
    assert mock_cleanup.call_count == 1


@patch("selfblog.unified._build_unified_body")
@patch("selfblog.unified._cleanup_injected_posts")
@patch("selfblog.unified._inject_posts_into_docs")
@patch("selfblog.unified._partition_pages")
@patch("selfblog.unified.load_config")
def test_unified_no_cleanup_when_no_injected_files(
    mock_load_config, mock_partition, mock_inject, mock_cleanup,
    mock_body, tmp_path,
):
    """Cleanup is not called when no files were injected."""
    from selfdoc.unified import build_unified

    docs_site = tmp_path / "docs-site"
    docs_site.mkdir()
    os.makedirs(str(docs_site / "docs"), exist_ok=True)
    os.makedirs(str(docs_site / "site"), exist_ok=True)
    os.makedirs(str(docs_site / "src"), exist_ok=True)
    _write_text(str(docs_site / "src" / "lib.py"), "")

    config = _minimal_config(
        unified={"projects": []},
    )

    # No posts injected anywhere
    mock_inject.return_value = []
    mock_partition.return_value = (set(), set(), {}, {})
    mock_body.return_value = {}

    build_unified(str(docs_site), config=config)

    # Cleanup should not be called since no files were injected
    assert mock_cleanup.call_count == 0
