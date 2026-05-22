"""Shared test fixture factories for selfdoc test suite."""

import json
import os
import subprocess

import pytest

# Git env vars to avoid reliance on global git config in test environments.
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _git(args, cwd):
    """Run a git command with deterministic author identity."""
    env = {**os.environ, **_GIT_ENV}
    subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        env=env,
        check=True,
        capture_output=True,
    )


def _write_json(path, data):
    """Write *data* as JSON to *path*."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _write_text(path, text):
    """Write *text* to *path*, creating parent directories if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def default_config(**overrides):
    """Minimal valid selfdoc config with required versions and locales."""
    config = {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "versions": [{"version": "1.0.0", "indexed": True}],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }
    config.update(overrides)
    return config


# Default locale/version prefix used in output paths for test assertions
DEFAULT_PREFIX = "en/1.0.0"


@pytest.fixture()
def make_project(tmp_path):
    """Factory fixture: create a minimal selfdoc project directory.

    Returns a callable that accepts keyword arguments merged into
    selfdoc.json.  Required keys (language, source, base_url) are
    supplied with sensible defaults if omitted.
    """

    def _factory(**overrides):
        project_dir = tmp_path / "project"
        project_dir.mkdir(exist_ok=True)

        # Merge defaults with caller overrides
        config = default_config(**overrides)

        _write_json(str(project_dir / "selfdoc.json"), config)

        # Minimal Python source file
        src_dir = project_dir / "src"
        src_dir.mkdir(exist_ok=True)
        _write_text(
            str(src_dir / "__init__.py"),
            '"""Example package."""\n',
        )

        # Minimal docs
        docs_dir = project_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        _write_text(
            str(docs_dir / "index.md"),
            "# Test Project\n\nWelcome to the docs.\n",
        )

        return project_dir

    return _factory


@pytest.fixture()
def make_versioned_project(tmp_path):
    """Factory fixture: create a selfdoc project with git tags for each version.

    Returns a callable accepting ``versions`` (list of version strings,
    e.g. ``["0.1.0", "0.2.0"]``) plus optional config overrides.
    """

    def _factory(versions, **overrides):
        project_dir = tmp_path / "versioned"
        project_dir.mkdir(exist_ok=True)

        # --- base config ---
        versions_config = [
            {"version": v, "indexed": True} for v in versions
        ]
        locales_config = [
            {"code": "en", "label": "English", "default": True},
        ]
        config = {
            "language": "python",
            "source": ["src/"],
            "base_url": "https://example.com",
            "versions": versions_config,
            "locales": locales_config,
        }
        config.update(overrides)

        _write_json(str(project_dir / "selfdoc.json"), config)

        # Minimal source
        src_dir = project_dir / "src"
        src_dir.mkdir(exist_ok=True)
        _write_text(
            str(src_dir / "__init__.py"),
            '"""Example package."""\n',
        )

        # Initial docs
        docs_dir = project_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        _write_text(
            str(docs_dir / "index.md"),
            "# Test Project\n\nInitial content.\n",
        )

        # --- git init + initial commit ---
        _git(["init"], cwd=project_dir)
        _git(["add", "."], cwd=project_dir)
        _git(["commit", "-m", "initial"], cwd=project_dir)

        # --- create a tagged commit per version ---
        for v in versions:
            _write_text(
                str(docs_dir / "index.md"),
                f"# Test Project\n\nDocumentation for version {v}.\n",
            )
            _git(["add", "docs/index.md"], cwd=project_dir)
            _git(["commit", "-m", f"docs for {v}"], cwd=project_dir)
            _git(["tag", f"v{v}"], cwd=project_dir)

        return project_dir

    return _factory


@pytest.fixture()
def make_localized_project(tmp_path):
    """Factory fixture: create a selfdoc project with per-locale doc directories.

    Returns a callable accepting ``locales`` (list of locale dicts with
    ``code``, ``label``, and optionally ``default`` / ``rtl``) plus
    optional config overrides.
    """

    def _factory(locales, **overrides):
        project_dir = tmp_path / "localized"
        project_dir.mkdir(exist_ok=True)

        config = {
            "language": "python",
            "source": ["src/"],
            "base_url": "https://example.com",
            "locales": locales,
            "versions": [{"version": "1.0.0", "indexed": True}],
        }
        config.update(overrides)

        _write_json(str(project_dir / "selfdoc.json"), config)

        # Minimal source
        src_dir = project_dir / "src"
        src_dir.mkdir(exist_ok=True)
        _write_text(
            str(src_dir / "__init__.py"),
            '"""Example package."""\n',
        )

        # Per-locale docs directories
        docs_dir = project_dir / "docs"
        for loc in locales:
            code = loc["code"]
            label = loc["label"]
            _write_text(
                str(docs_dir / code / "index.md"),
                f"# Test Project ({label})\n\nWelcome — {label}.\n",
            )

        return project_dir

    return _factory


@pytest.fixture()
def make_unified_project(tmp_path):
    """Factory fixture: create a monorepo with a docs-site that unifies sub-projects.

    Returns a callable accepting ``projects`` (list of dicts with
    ``name`` and ``language``) plus optional config overrides applied
    to the docs-site's selfdoc.json.
    """

    def _factory(projects, **overrides):
        packages_dir = tmp_path / "monorepo" / "packages"
        packages_dir.mkdir(parents=True, exist_ok=True)

        # --- constituent projects ---
        unified_entries = []
        for proj in projects:
            name = proj["name"]
            lang = proj.get("language", "python")
            proj_dir = packages_dir / name

            proj_config = {
                "language": lang,
                "source": ["src/"],
                "base_url": f"https://example.com/{name}",
            }
            proj_dir.mkdir(exist_ok=True)
            _write_json(str(proj_dir / "selfdoc.json"), proj_config)

            src_dir = proj_dir / "src"
            src_dir.mkdir(exist_ok=True)
            _write_text(
                str(src_dir / "__init__.py"),
                f'"""{name} package."""\n',
            )

            docs_sub = proj_dir / "docs"
            docs_sub.mkdir(exist_ok=True)
            _write_text(
                str(docs_sub / "index.md"),
                f"# {name}\n\nDocs for {name}.\n",
            )

            unified_entries.append({"path": f"../{name}"})

        # --- docs-site project ---
        docs_site_dir = packages_dir / "docs-site"
        docs_site_dir.mkdir(exist_ok=True)

        docs_site_config = {
            "language": "python",
            "source": ["src/"],
            "base_url": "https://example.com",
            "unified": {"projects": unified_entries},
            "versions": [{"version": "1.0.0", "indexed": True}],
            "locales": [
                {"code": "en", "label": "English", "default": True},
            ],
        }
        docs_site_config.update(overrides)

        _write_json(str(docs_site_dir / "selfdoc.json"), docs_site_config)

        # docs-site needs its own minimal source (config requires it)
        src_dir = docs_site_dir / "src"
        src_dir.mkdir(exist_ok=True)
        _write_text(
            str(src_dir / "__init__.py"),
            '"""Docs-site placeholder."""\n',
        )

        docs_dir = docs_site_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        _write_text(
            str(docs_dir / "index.md"),
            "# Unified Docs\n\nLanding page for the monorepo.\n",
        )

        return docs_site_dir

    return _factory
