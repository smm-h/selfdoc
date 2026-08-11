"""Tests for the version-override handshake and version-match check.

Covers three coupled behaviours:

1. ``resolve_var("project.version")`` honours a runtime override injected
   into the config object (``_version_override``), so ``selfdoc gen
   --version-override X`` stamps the about-to-be-released version into
   generated root files instead of the pre-bump one.
2. The generated CLI index page carries a ``var`` DIRECTIVE for the
   version rather than a baked literal, so its raw content hash is stable
   across version bumps (no STALE001 churn) while the built site still
   shows the current version.
3. ``selfdoc check`` reports VER004 when version-bearing generated content
   embeds a version that is not the expected one.
"""

import json
import os

import pytest

from selfdoc.check import _check_version_match
from selfdoc.gen import generate_root_files
from selfdoc_core.content import VERSION_OVERRIDE_KEY, resolve_var
from selfdoc_core.staleness import compute_content_hash


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _make_project(tmp_path, version="1.0.0", root_files=None):
    """Create a minimal Python project with a version-bearing root template."""
    _write(
        os.path.join(tmp_path, "pyproject.toml"),
        f'[project]\nname = "mylib"\nversion = "{version}"\n',
    )
    _write(os.path.join(tmp_path, "mylib", "__init__.py"), '"""My library."""\n')

    config = {
        "source": [{"path": "mylib/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "versions": [{"version": version}],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }
    if root_files is not None:
        config["root_files"] = root_files
    _write(os.path.join(tmp_path, "selfdoc.json"), json.dumps(config))
    _write(os.path.join(tmp_path, "docs", "index.md"), "# Index\n\nHello.\n")
    return config


def _set_project_version(tmp_path, version):
    _write(
        os.path.join(tmp_path, "pyproject.toml"),
        f'[project]\nname = "mylib"\nversion = "{version}"\n',
    )


# -- resolve_var override ------------------------------------------------------


class TestResolveVarOverride:
    def test_reads_manifest_without_override(self, tmp_path):
        _make_project(tmp_path, version="1.2.3")
        result = resolve_var({"key": "project.version"}, {}, str(tmp_path))
        assert result == "1.2.3"

    def test_override_wins(self, tmp_path):
        _make_project(tmp_path, version="1.2.3")
        config = {VERSION_OVERRIDE_KEY: "2.0.0"}
        result = resolve_var({"key": "project.version"}, config, str(tmp_path))
        assert result == "2.0.0"

    def test_empty_override_falls_back_to_manifest(self, tmp_path):
        _make_project(tmp_path, version="1.2.3")
        config = {VERSION_OVERRIDE_KEY: ""}
        result = resolve_var({"key": "project.version"}, config, str(tmp_path))
        assert result == "1.2.3"

    def test_override_does_not_affect_other_keys(self, tmp_path):
        _make_project(tmp_path, version="1.2.3")
        config = {VERSION_OVERRIDE_KEY: "2.0.0"}
        assert resolve_var(
            {"key": "project.name"}, config, str(tmp_path),
        ) == "mylib"


# -- gen --version-override ----------------------------------------------------


class TestGenVersionOverride:
    def test_root_file_stamps_override(self, tmp_path):
        _make_project(tmp_path, version="1.0.0", root_files=["docs/_NOTES.md"])
        _write(
            os.path.join(tmp_path, "docs", "_NOTES.md"),
            '# Notes\n\nVersion: :-: var key="project.version"\n',
        )

        from selfdoc.cli import _cmd_gen

        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            _cmd_gen(None, auto_commit=False, version_override="2.0.0")
        finally:
            os.chdir(cwd)

        with open(os.path.join(tmp_path, "NOTES.md"), encoding="utf-8") as f:
            content = f.read()
        assert "Version: 2.0.0" in content
        assert "1.0.0" not in content

    def test_root_file_without_override_uses_manifest(self, tmp_path):
        _make_project(tmp_path, version="1.0.0", root_files=["docs/_NOTES.md"])
        _write(
            os.path.join(tmp_path, "docs", "_NOTES.md"),
            '# Notes\n\nVersion: :-: var key="project.version"\n',
        )

        from selfdoc.cli import _cmd_gen

        cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            _cmd_gen(None, auto_commit=False, version_override="")
        finally:
            os.chdir(cwd)

        with open(os.path.join(tmp_path, "NOTES.md"), encoding="utf-8") as f:
            content = f.read()
        assert "Version: 1.0.0" in content

    def test_generate_root_files_honours_config_key(self, tmp_path):
        config = _make_project(
            tmp_path, version="1.0.0", root_files=["docs/_NOTES.md"],
        )
        _write(
            os.path.join(tmp_path, "docs", "_NOTES.md"),
            '# Notes\n\nVersion: :-: var key="project.version"\n',
        )
        config[VERSION_OVERRIDE_KEY] = "3.1.4"
        generate_root_files(config, base_dir=str(tmp_path))

        with open(os.path.join(tmp_path, "NOTES.md"), encoding="utf-8") as f:
            assert "Version: 3.1.4" in f.read()


# -- cli-index version line is a directive, not a literal ---------------------


def _cli_structure(version):
    return {
        "app_name": "mytool",
        "app_help": "A tool.",
        "app_version": version,
        "commands": [{"name": "run", "help": "Run it."}],
        "groups": [],
    }


class TestCliIndexVersionDirective:
    """Reproduces stale001-volatile-generated-lines.md and
    version-bump-content-trips-stale001-every-release.md."""

    def test_index_carries_var_directive(self, tmp_path):
        from selfdoc.strictcli_support import generate_cli_pages

        docs = os.path.join(tmp_path, "docs")
        generate_cli_pages(_cli_structure("1.0.0"), docs)
        with open(os.path.join(docs, "cli-index.md"), encoding="utf-8") as f:
            content = f.read()
        assert 'Version: :-: var key="project.version"' in content
        assert "Version: 1.0.0" not in content

    def test_content_hash_stable_across_version_bump(self, tmp_path):
        """The whole point: a version bump must not move the content hash."""
        from selfdoc.strictcli_support import generate_cli_pages

        docs_a = os.path.join(tmp_path, "a", "docs")
        docs_b = os.path.join(tmp_path, "b", "docs")
        generate_cli_pages(_cli_structure("1.0.0"), docs_a)
        generate_cli_pages(_cli_structure("2.0.0"), docs_b)

        with open(os.path.join(docs_a, "cli-index.md"), encoding="utf-8") as f:
            body_a = f.read()
        with open(os.path.join(docs_b, "cli-index.md"), encoding="utf-8") as f:
            body_b = f.read()

        assert compute_content_hash(body_a) == compute_content_hash(body_b)

    def test_no_version_line_when_schema_has_no_version(self, tmp_path):
        from selfdoc.strictcli_support import generate_cli_pages

        docs = os.path.join(tmp_path, "docs")
        generate_cli_pages(_cli_structure(""), docs)
        with open(os.path.join(docs, "cli-index.md"), encoding="utf-8") as f:
            assert "Version:" not in f.read()

    def test_directive_resolves_at_build_time(self, tmp_path):
        """The built site shows the CURRENT version, not the gen-time one."""
        from selfdoc.strictcli_support import generate_cli_pages

        _make_project(tmp_path, version="2.0.0")
        generate_cli_pages(_cli_structure("1.0.0"), os.path.join(tmp_path, "docs"))

        from selfdoc.build import build

        build(dir_path=str(tmp_path))
        out = os.path.join(
            tmp_path, "docs", "_build", "en", "2.0.0", "cli-index", "index.html",
        )
        with open(out, encoding="utf-8") as f:
            html = f.read()
        assert "2.0.0" in html


# -- version-match check (VER004) ---------------------------------------------


class TestVersionMatchCheck:
    def _project_with_generated_root(self, tmp_path, gen_version, project_version):
        config = _make_project(
            tmp_path, version=gen_version, root_files=["docs/_NOTES.md"],
        )
        _write(
            os.path.join(tmp_path, "docs", "_NOTES.md"),
            '# Notes\n\nVersion: :-: var key="project.version"\n',
        )
        generate_root_files(config, base_dir=str(tmp_path))
        _set_project_version(tmp_path, project_version)
        return config

    def test_passes_when_versions_match(self, tmp_path):
        config = self._project_with_generated_root(tmp_path, "1.0.0", "1.0.0")
        assert _check_version_match(config, str(tmp_path)) == []

    def test_fails_when_generated_version_is_stale(self, tmp_path):
        config = self._project_with_generated_root(tmp_path, "1.0.0", "2.0.0")
        lints = _check_version_match(config, str(tmp_path))
        assert len(lints) == 1
        assert lints[0].code == "VER004"
        assert lints[0].severity == "error"
        assert "2.0.0" in lints[0].message
        assert "NOTES.md" in lints[0].file

    def test_override_defines_the_expected_version(self, tmp_path):
        """During a release, gen stamps the NEW version before the bump lands."""
        config = self._project_with_generated_root(tmp_path, "2.0.0", "1.0.0")
        # Without the override the check sees 2.0.0 embedded, 1.0.0 detected.
        assert _check_version_match(config, str(tmp_path)) != []
        # With the override the embedded 2.0.0 is exactly what is expected.
        assert _check_version_match(
            config, str(tmp_path), version_override="2.0.0",
        ) == []

    def test_fails_when_override_required_but_absent(self, tmp_path):
        """gen ran WITHOUT the override; the release expects the new version."""
        config = self._project_with_generated_root(tmp_path, "1.0.0", "1.0.0")
        lints = _check_version_match(
            config, str(tmp_path), version_override="2.0.0",
        )
        assert len(lints) == 1
        assert lints[0].code == "VER004"

    def test_skips_templates_without_a_version_directive(self, tmp_path):
        config = _make_project(
            tmp_path, version="1.0.0", root_files=["docs/_NOTES.md"],
        )
        _write(os.path.join(tmp_path, "docs", "_NOTES.md"), "# Notes\n\nNo version.\n")
        generate_root_files(config, base_dir=str(tmp_path))
        _set_project_version(tmp_path, "2.0.0")
        assert _check_version_match(config, str(tmp_path)) == []

    def test_skips_when_root_file_not_generated_yet(self, tmp_path):
        config = _make_project(
            tmp_path, version="1.0.0", root_files=["docs/_NOTES.md"],
        )
        _write(
            os.path.join(tmp_path, "docs", "_NOTES.md"),
            '# Notes\n\nVersion: :-: var key="project.version"\n',
        )
        assert _check_version_match(config, str(tmp_path)) == []

    def test_no_root_files_is_a_no_op(self, tmp_path):
        config = _make_project(tmp_path, version="1.0.0")
        assert _check_version_match(config, str(tmp_path)) == []


# -- end-to-end release-shaped scenario ---------------------------------------


def test_release_cycle_is_hash_stable_and_version_correct(tmp_path):
    """Generate at A, bump to B, regenerate with --version-override B.

    The committed docs template content hash must not move (no STALE001
    from version churn), the generated root file must carry B, and the
    version-match check must pass.
    """
    from selfdoc.cli import _cmd_gen
    from selfdoc.strictcli_support import generate_cli_pages

    config = _make_project(tmp_path, version="1.0.0", root_files=["docs/_NOTES.md"])
    _write(
        os.path.join(tmp_path, "docs", "_NOTES.md"),
        '# Notes\n\nVersion: :-: var key="project.version"\n',
    )
    cli_index = os.path.join(tmp_path, "docs", "cli-index.md")
    generate_cli_pages(_cli_structure("1.0.0"), os.path.join(tmp_path, "docs"))
    with open(cli_index, encoding="utf-8") as f:
        hash_before = compute_content_hash(f.read())

    # Bump, then regenerate the way the release pipeline would.
    _set_project_version(tmp_path, "2.0.0")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        _cmd_gen(None, auto_commit=False, version_override="2.0.0")
    finally:
        os.chdir(cwd)

    generate_cli_pages(_cli_structure("2.0.0"), os.path.join(tmp_path, "docs"))
    with open(cli_index, encoding="utf-8") as f:
        hash_after = compute_content_hash(f.read())
    assert hash_before == hash_after

    with open(os.path.join(tmp_path, "NOTES.md"), encoding="utf-8") as f:
        assert "Version: 2.0.0" in f.read()

    assert _check_version_match(config, str(tmp_path)) == []
