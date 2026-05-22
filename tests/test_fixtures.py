"""Tests for the shared fixture factories in conftest.py."""

import json
import os
import subprocess

from selfdoc.config import load_config


# -- make_project --


def test_make_project_creates_selfdoc_json(make_project):
    project_dir = make_project()
    assert os.path.isfile(str(project_dir / "selfdoc.json"))


def test_make_project_creates_source_dir(make_project):
    project_dir = make_project()
    init_py = project_dir / "src" / "__init__.py"
    assert os.path.isfile(str(init_py))


def test_make_project_creates_docs(make_project):
    project_dir = make_project()
    index_md = project_dir / "docs" / "index.md"
    assert os.path.isfile(str(index_md))


def test_make_project_config_loads(make_project):
    project_dir = make_project()
    cfg = load_config(str(project_dir))
    assert cfg is not None
    assert cfg["language"] == "python"
    assert cfg["base_url"] == "https://example.com"


def test_make_project_accepts_overrides(make_project):
    project_dir = make_project(language="go")
    cfg = load_config(str(project_dir))
    assert cfg["language"] == "go"


# -- make_versioned_project --


def test_versioned_creates_git_tags(make_versioned_project):
    versions = ["0.1.0", "0.2.0"]
    project_dir = make_versioned_project(versions)
    result = subprocess.run(
        ["git", "tag", "-l"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        check=True,
    )
    tags = sorted(result.stdout.strip().splitlines())
    assert tags == ["v0.1.0", "v0.2.0"]


def test_versioned_different_content_per_tag(make_versioned_project):
    versions = ["0.1.0", "0.2.0"]
    project_dir = make_versioned_project(versions)

    def _read_index_at_tag(tag):
        result = subprocess.run(
            ["git", "show", f"{tag}:docs/index.md"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    content_v1 = _read_index_at_tag("v0.1.0")
    content_v2 = _read_index_at_tag("v0.2.0")
    assert "0.1.0" in content_v1
    assert "0.2.0" in content_v2
    assert content_v1 != content_v2


def test_versioned_config_loads(make_versioned_project):
    project_dir = make_versioned_project(["1.0.0"])
    cfg = load_config(str(project_dir))
    assert cfg is not None
    assert cfg["versions"] is not None
    assert len(cfg["versions"]) == 1
    assert cfg["versions"][0]["version"] == "1.0.0"
    assert cfg["locales"] is not None


# -- make_localized_project --


def test_localized_creates_locale_dirs(make_localized_project):
    locales = [
        {"code": "en", "label": "English", "default": True},
        {"code": "fa", "label": "Farsi"},
    ]
    project_dir = make_localized_project(locales)
    assert os.path.isdir(str(project_dir / "docs" / "en"))
    assert os.path.isdir(str(project_dir / "docs" / "fa"))
    assert os.path.isfile(str(project_dir / "docs" / "en" / "index.md"))
    assert os.path.isfile(str(project_dir / "docs" / "fa" / "index.md"))


def test_localized_content_per_locale(make_localized_project):
    locales = [
        {"code": "en", "label": "English", "default": True},
        {"code": "fa", "label": "Farsi"},
    ]
    project_dir = make_localized_project(locales)
    with open(str(project_dir / "docs" / "en" / "index.md")) as f:
        en_content = f.read()
    with open(str(project_dir / "docs" / "fa" / "index.md")) as f:
        fa_content = f.read()
    assert "English" in en_content
    assert "Farsi" in fa_content


def test_localized_config_loads(make_localized_project):
    locales = [
        {"code": "en", "label": "English", "default": True},
        {"code": "fa", "label": "Farsi"},
    ]
    project_dir = make_localized_project(locales)
    cfg = load_config(str(project_dir))
    assert cfg is not None
    assert len(cfg["locales"]) == 2
    assert cfg["versions"] is not None


# -- make_unified_project --


def test_unified_creates_monorepo_structure(make_unified_project):
    projects = [
        {"name": "core", "language": "python"},
        {"name": "cli", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)

    # Constituent projects exist alongside docs-site
    packages_dir = docs_site_dir.parent
    assert os.path.isfile(str(packages_dir / "core" / "selfdoc.json"))
    assert os.path.isfile(str(packages_dir / "cli" / "selfdoc.json"))
    assert os.path.isfile(str(packages_dir / "core" / "docs" / "index.md"))
    assert os.path.isfile(str(packages_dir / "cli" / "docs" / "index.md"))


def test_unified_docs_site_has_unified_config(make_unified_project):
    projects = [
        {"name": "core", "language": "python"},
        {"name": "cli", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)
    cfg = load_config(str(docs_site_dir))
    assert cfg is not None
    assert cfg["unified"] is not None
    assert len(cfg["unified"]["projects"]) == 2


def test_unified_constituent_configs_load(make_unified_project):
    projects = [
        {"name": "core", "language": "python"},
        {"name": "cli", "language": "python"},
    ]
    docs_site_dir = make_unified_project(projects)
    packages_dir = docs_site_dir.parent

    for proj in projects:
        cfg = load_config(str(packages_dir / proj["name"]))
        assert cfg is not None
        assert cfg["language"] == proj["language"]
