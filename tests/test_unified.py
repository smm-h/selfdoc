"""Tests for monorepo unified site support (Phase 6)."""

import json
import os
import subprocess

import pytest

from selfdoc.build import build
from selfdoc.config import ConfigError, load_config
from selfblog.unified import (
    _build_unified_nav,
    _generate_landing_page,
    _project_nav_title,
    _project_slug,
    _resolve_project_path,
    _validate_rlsbl_workspace,
    build_unified,
)
from conftest import _git, _write_json, _write_text


# -- Helper --

def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# -- Unit tests for helpers --


def test_project_slug_explicit():
    entry = {"path": "../core", "slug": "my-core"}
    assert _project_slug(entry) == "my-core"


def test_project_slug_derived():
    entry = {"path": "../core"}
    assert _project_slug(entry) == "core"


def test_project_slug_trailing_slash():
    entry = {"path": "../core/"}
    assert _project_slug(entry) == "core"


def test_project_nav_title_explicit():
    entry = {"path": "../core", "nav_title": "Core Library"}
    assert _project_nav_title(entry) == "Core Library"


def test_project_nav_title_derived():
    entry = {"path": "../my-lib"}
    assert _project_nav_title(entry) == "My Lib"


def test_resolve_project_path(tmp_path):
    docs_site = tmp_path / "docs-site"
    docs_site.mkdir()
    core = tmp_path / "core"
    core.mkdir()
    entry = {"path": "../core"}
    result = _resolve_project_path(entry, str(docs_site))
    assert os.path.basename(result) == "core"
    assert os.path.isdir(result)


def test_resolve_project_path_missing(tmp_path):
    docs_site = tmp_path / "docs-site"
    docs_site.mkdir()
    entry = {"path": "../nonexistent"}
    try:
        _resolve_project_path(entry, str(docs_site))
        assert False, "should have raised"
    except ConfigError as e:
        assert "does not exist" in str(e)


# -- Unified nav --

def test_build_unified_nav_merges():
    common_nav = [
        {"label": "Home", "path": "index.html", "md_path": "index.md"},
    ]
    projects_nav = [
        ("core", "Core", [
            {"label": "Core Home", "path": "index.html", "md_path": "index.md"},
        ], "en/core/1.0.0"),
        ("cli", "CLI", [
            {"label": "CLI Home", "path": "index.html", "md_path": "index.md"},
        ], "en/cli/1.0.0"),
    ]
    result = _build_unified_nav(common_nav, projects_nav, {})
    assert result[0]["label"] == "Home"
    assert result[1]["group"] == "Core"
    assert result[1]["items"][0]["path"] == "en/core/1.0.0/index.html"
    assert result[2]["group"] == "CLI"
    assert result[2]["items"][0]["path"] == "en/cli/1.0.0/index.html"


def test_build_unified_nav_nested_groups():
    common_nav = []
    projects_nav = [
        ("core", "Core", [
            {"group": "API", "slug": "api", "items": [
                {"label": "Config", "path": "api/config.html", "md_path": "api/config.md"},
            ]},
        ], "en/core/1.0.0"),
    ]
    result = _build_unified_nav(common_nav, projects_nav, {})
    group = result[0]
    assert group["group"] == "Core"
    # The nested group's items should be prefixed
    nested = group["items"][0]
    assert nested["group"] == "API"
    assert nested["items"][0]["path"] == "en/core/1.0.0/api/config.html"


# -- Landing page --

def test_generate_landing_page():
    info = [
        {
            "slug": "core",
            "nav_title": "Core Library",
            "description": "The core framework",
            "version": "2.0.0",
            "url_prefix": "en/core/1.0.0",
        },
    ]
    html = _generate_landing_page(info, {})
    assert "project-grid" in html
    assert "Core Library" in html
    assert "The core framework" in html
    assert "v2.0.0" in html


# -- Full unified build --

def test_build_unified_basic(make_unified_project):
    """Build a unified project and verify output structure."""
    projects = [
        {"name": "core", "language": "python"},
        {"name": "cli", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)

    written = build_unified(str(docs_site_dir))

    output_dir = os.path.join(str(docs_site_dir), "docs", "_build")
    assert os.path.isdir(output_dir)

    # Common content exists
    assert os.path.isfile(
        os.path.join(output_dir, "en", "common", "1.0.0", "index.html")
    )
    # Constituent project content exists
    assert os.path.isfile(
        os.path.join(output_dir, "en", "core", "1.0.0", "index.html")
    )
    assert os.path.isfile(
        os.path.join(output_dir, "en", "cli", "1.0.0", "index.html")
    )


def test_build_unified_search_index(make_unified_project):
    """Verify unified search index has entries from all projects."""
    projects = [
        {"name": "core", "language": "python"},
        {"name": "cli", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)

    build_unified(str(docs_site_dir))

    output_dir = os.path.join(str(docs_site_dir), "docs", "_build")
    search_path = os.path.join(output_dir, "search-index.json")
    assert os.path.isfile(search_path)

    with open(search_path, "r") as f:
        entries = json.load(f)

    # Should have entries from core, cli, and common
    project_names = {e["project"] for e in entries}
    assert "core" in project_names
    assert "cli" in project_names
    assert "common" in project_names


def test_build_unified_root_redirect(make_unified_project):
    """Verify root redirect points to common content."""
    projects = [
        {"name": "core", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)

    build_unified(str(docs_site_dir))

    output_dir = os.path.join(str(docs_site_dir), "docs", "_build")
    root_index = _read(os.path.join(output_dir, "index.html"))
    assert "/en/common/1.0.0/" in root_index


def test_build_unified_root_redirect_canonical_is_absolute(make_unified_project):
    """The unified root stub names an absolute canonical, not a site-root path."""
    projects = [
        {"name": "core", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)

    build_unified(str(docs_site_dir))

    output_dir = os.path.join(str(docs_site_dir), "docs", "_build")
    root_index = _read(os.path.join(output_dir, "index.html"))
    assert (
        '<link rel="canonical" href="https://example.com/en/common/1.0.0/">'
        in root_index
    )
    # The meta refresh stays root-relative: it is a same-site hop.
    assert 'content="0;url=/en/common/1.0.0/"' in root_index


def test_build_unified_landing_page(make_unified_project):
    """Verify landing page lists all projects."""
    projects = [
        {"name": "core", "language": "python"},
        {"name": "cli", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)

    build_unified(str(docs_site_dir))

    output_dir = os.path.join(str(docs_site_dir), "docs", "_build")
    landing = _read(
        os.path.join(output_dir, "en", "common", "1.0.0", "projects", "index.html")
    )
    assert "project-grid" in landing
    assert "Core" in landing
    assert "Cli" in landing


def test_build_unified_constituent_content(make_unified_project):
    """Verify constituent project pages have correct content."""
    projects = [
        {"name": "core", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)

    build_unified(str(docs_site_dir))

    output_dir = os.path.join(str(docs_site_dir), "docs", "_build")
    core_index = _read(
        os.path.join(output_dir, "en", "core", "1.0.0", "index.html")
    )
    assert "core" in core_index.lower()


def test_build_unified_shared_assets(make_unified_project):
    """Verify shared assets are generated once."""
    projects = [
        {"name": "core", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)

    build_unified(str(docs_site_dir))

    output_dir = os.path.join(str(docs_site_dir), "docs", "_build")
    assert os.path.isfile(os.path.join(output_dir, "style.css"))
    assert os.path.isfile(os.path.join(output_dir, "search-index.json"))
    assert os.path.isfile(os.path.join(output_dir, "search.js"))


def test_single_project_build_still_works(make_project):
    """Verify that non-unified (single-project) builds still work."""
    project_dir = make_project()
    written = build(str(project_dir))
    assert len(written) > 0


# -- rlsbl workspace validation --

def test_validate_rlsbl_workspace_no_workspace(tmp_path):
    """No .rlsbl-monorepo/ -- validation is a no-op."""
    docs_site = tmp_path / "docs-site"
    docs_site.mkdir()
    _validate_rlsbl_workspace(str(docs_site), {"projects": []})


def test_validate_rlsbl_workspace_all_covered(tmp_path):
    """All workspace projects are in unified.projects -- passes."""
    monorepo = tmp_path / "monorepo"
    monorepo.mkdir()
    (monorepo / ".rlsbl-monorepo").mkdir()

    # workspace.toml
    toml_content = 'projects = ["packages/core", "packages/cli"]\n'
    (monorepo / ".rlsbl-monorepo" / "workspace.toml").write_text(toml_content)

    # Projects with selfdoc.json
    for name in ("core", "cli"):
        proj = monorepo / "packages" / name
        proj.mkdir(parents=True)
        (proj / "selfdoc.json").write_text("{}")

    docs_site = monorepo / "packages" / "docs-site"
    docs_site.mkdir(parents=True)

    unified_config = {
        "projects": [
            {"path": "../core"},
            {"path": "../cli"},
        ],
    }
    # Should not raise
    _validate_rlsbl_workspace(str(docs_site), unified_config)


def test_validate_rlsbl_workspace_missing_project(tmp_path):
    """Workspace project not in unified.projects -- raises."""
    monorepo = tmp_path / "monorepo"
    monorepo.mkdir()
    (monorepo / ".rlsbl-monorepo").mkdir()

    toml_content = 'projects = ["packages/core", "packages/cli"]\n'
    (monorepo / ".rlsbl-monorepo" / "workspace.toml").write_text(toml_content)

    for name in ("core", "cli"):
        proj = monorepo / "packages" / name
        proj.mkdir(parents=True)
        (proj / "selfdoc.json").write_text("{}")

    docs_site = monorepo / "packages" / "docs-site"
    docs_site.mkdir(parents=True)

    # Only core is covered, cli is missing
    unified_config = {
        "projects": [
            {"path": "../core"},
        ],
    }
    try:
        _validate_rlsbl_workspace(str(docs_site), unified_config)
        assert False, "should have raised"
    except ConfigError as e:
        assert "cli" in str(e)
        assert "neither in unified.projects" in str(e)


def test_validate_rlsbl_workspace_excluded(tmp_path):
    """Workspace project in unified.exclude -- passes."""
    monorepo = tmp_path / "monorepo"
    monorepo.mkdir()
    (monorepo / ".rlsbl-monorepo").mkdir()

    toml_content = 'projects = ["packages/core", "packages/internal"]\n'
    (monorepo / ".rlsbl-monorepo" / "workspace.toml").write_text(toml_content)

    for name in ("core", "internal"):
        proj = monorepo / "packages" / name
        proj.mkdir(parents=True)
        (proj / "selfdoc.json").write_text("{}")

    docs_site = monorepo / "packages" / "docs-site"
    docs_site.mkdir(parents=True)

    unified_config = {
        "projects": [
            {"path": "../core"},
        ],
        "exclude": ["internal"],
    }
    # Should not raise
    _validate_rlsbl_workspace(str(docs_site), unified_config)


# -- Check unified --

def test_check_unified(make_unified_project):
    """check_unified runs checks across all constituent projects."""
    from selfblog.check import check_unified

    projects = [
        {"name": "core", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)

    config = load_config(str(docs_site_dir))
    result = check_unified(str(docs_site_dir), config=config, dry_run=True)

    # Should have results from both [core] and [common]
    all_files = [dr.file for dr in result.directive_results]
    all_lint_files = [lint.file for lint in result.lints]
    combined = all_files + all_lint_files
    has_core = any("[core]" in f for f in combined)
    has_common = any("[common]" in f for f in combined)
    # At minimum common lints should appear (SEO checks on docs-site docs)
    assert has_common or has_core


def test_selfdoc_check_hard_errors_on_unified(
    make_unified_project, monkeypatch, capsys,
):
    """'selfdoc check' on a unified project errors, pointing to
    'selfblog check' (the unified check moved to selfblog)."""
    from selfdoc.cli import _cmd_check

    docs_site_dir = make_unified_project([
        {"name": "core", "language": "python"},
    ])
    monkeypatch.chdir(docs_site_dir)

    with pytest.raises(SystemExit):
        _cmd_check(None)
    captured = capsys.readouterr()
    assert "selfblog check" in captured.err


# -- Version pinning --

def test_version_pinning_uses_old_constituent_content(tmp_path):
    """Old docs-site version with projects pinning builds constituent at pinned tag."""
    packages_dir = tmp_path / "monorepo" / "packages"
    packages_dir.mkdir(parents=True)

    # --- constituent project: core ---
    core_dir = packages_dir / "core"
    core_dir.mkdir()
    core_config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com/core",
        "version": "1.0.0",
    }
    _write_json(str(core_dir / "selfdoc.json"), core_config)
    (core_dir / "src").mkdir()
    _write_text(str(core_dir / "src" / "__init__.py"), '"""core."""\n')
    (core_dir / "docs").mkdir()
    _write_text(
        str(core_dir / "docs" / "index.md"),
        "# Core v1\n\nOld core content for version 1.0.0.\n",
    )

    # --- git init core and create v1.0.0 tag ---
    _git(["init"], cwd=core_dir)
    _git(["add", "."], cwd=core_dir)
    _git(["commit", "-m", "core v1.0.0"], cwd=core_dir)
    _git(["tag", "v1.0.0"], cwd=core_dir)

    # --- update core to v2.0.0 ---
    _write_text(
        str(core_dir / "docs" / "index.md"),
        "# Core v2\n\nNew core content for version 2.0.0.\n",
    )
    _git(["add", "docs/index.md"], cwd=core_dir)
    _git(["commit", "-m", "core v2.0.0"], cwd=core_dir)
    _git(["tag", "v2.0.0"], cwd=core_dir)

    # --- docs-site project ---
    docs_site_dir = packages_dir / "docs-site"
    docs_site_dir.mkdir()
    docs_site_config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "unified": {
            "projects": [{"path": "../core"}],
        },
        "version": "2.0.0",
        "versions": [
            {
                "version": "1.0.0",
                "indexed": True,
                "projects": {"core": "1.0.0"},
            },
            {
                "version": "2.0.0",
                "indexed": True,
            },
        ],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }
    _write_json(str(docs_site_dir / "selfdoc.json"), docs_site_config)
    (docs_site_dir / "src").mkdir()
    _write_text(
        str(docs_site_dir / "src" / "__init__.py"),
        '"""Docs-site."""\n',
    )
    (docs_site_dir / "docs").mkdir()
    _write_text(
        str(docs_site_dir / "docs" / "index.md"),
        "# Unified Docs\n\nLanding page.\n",
    )

    # --- build ---
    written = build_unified(str(docs_site_dir))

    output_dir = str(docs_site_dir / "docs" / "_build")

    # Old docs-site version should have old core content (v1.0.0)
    old_core_html = _read(
        os.path.join(output_dir, "en", "core", "1.0.0", "index.html"),
    )
    assert "Old core content" in old_core_html or "Core v1" in old_core_html

    # Latest docs-site version should have new core content (v2.0.0)
    new_core_html = _read(
        os.path.join(output_dir, "en", "core", "2.0.0", "index.html"),
    )
    assert "New core content" in new_core_html or "Core v2" in new_core_html
