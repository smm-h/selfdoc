"""Tests for version_filter parameter on check_docs (VER001 skip)."""

import json
import os
import subprocess

import pytest

from selfdoc.check import check_docs


# -- Helpers ---------------------------------------------------------------

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _git(args, cwd):
    env = {**os.environ, **_GIT_ENV}
    subprocess.run(
        ["git"] + args, cwd=str(cwd), env=env,
        check=True, capture_output=True,
    )


def _make_multiversion_project(tmp_path):
    """Create a project with two versions where the old tag is missing docs.

    This ensures VER001 fires when multi-version validation runs: the
    old version's tag has no docs/ directory, so _extract_version_content
    raises RuntimeError.
    """
    project = tmp_path / "proj"
    project.mkdir()

    config = {
        "source": [{"path": "src/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "version": "0.2.0",
        "versions": [
            {"version": "0.1.0", "indexed": True},
            {"version": "0.2.0", "indexed": True},
        ],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }
    config_path = project / "selfdoc.json"
    with open(config_path, "w") as f:
        json.dump(config, f)

    src_dir = project / "src"
    src_dir.mkdir()
    with open(src_dir / "__init__.py", "w") as f:
        f.write('"""Pkg."""\n')

    # Init git with just source (no docs yet) and tag v0.1.0
    _git(["init"], cwd=project)
    _git(["add", "."], cwd=project)
    _git(["commit", "-m", "initial"], cwd=project)
    _git(["tag", "v0.1.0"], cwd=project)

    # Now create docs and commit for v0.2.0
    docs_dir = project / "docs"
    docs_dir.mkdir()
    with open(docs_dir / "index.md", "w") as f:
        f.write("# Project\n\nWelcome.\n")

    _git(["add", "docs/"], cwd=project)
    _git(["commit", "-m", "add docs"], cwd=project)
    _git(["tag", "v0.2.0"], cwd=project)

    return project


# -- Tests -----------------------------------------------------------------


class TestVer001Filter:
    """version_filter controls whether multi-version validation runs."""

    def test_without_filter_ver001_fires(self, tmp_path):
        """Without version_filter, multi-version validation runs and
        VER001 fires for versions that can't be extracted."""
        project = _make_multiversion_project(tmp_path)

        result = check_docs(str(project), dry_run=True)

        ver001_lints = [l for l in result.lints if l.code == "VER001"]
        assert len(ver001_lints) >= 1
        assert "0.1.0" in ver001_lints[0].message

    def test_with_filter_ver001_skipped(self, tmp_path):
        """With version_filter set, multi-version validation is skipped
        entirely -- no VER001 lint is emitted."""
        project = _make_multiversion_project(tmp_path)

        result = check_docs(
            str(project), version_filter="0.2.0", dry_run=True,
        )

        ver001_lints = [l for l in result.lints if l.code == "VER001"]
        assert len(ver001_lints) == 0

    def test_other_checks_still_run_with_filter(self, tmp_path):
        """When version_filter is set, other checks (directives, SEO,
        coverage, staleness) still run normally."""
        project = _make_multiversion_project(tmp_path)

        # Add a doc with a broken directive to verify directive
        # validation still runs.
        docs_dir = project / "docs"
        with open(docs_dir / "api.md", "w") as f:
            f.write(
                "# API\n\n"
                ':-: ref path="nonexistent_module"\n'
            )
        _git(["add", "docs/api.md"], cwd=project)
        _git(["commit", "-m", "add broken directive"], cwd=project)

        result = check_docs(
            str(project), version_filter="0.2.0", dry_run=True,
        )

        # Directive validation should have run -- the broken directive
        # should produce a FAILED result.
        failed = [
            dr for dr in result.directive_results if dr.status == "FAILED"
        ]
        assert len(failed) >= 1

        # VER001 should still be absent.
        ver001_lints = [l for l in result.lints if l.code == "VER001"]
        assert len(ver001_lints) == 0
