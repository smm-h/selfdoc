"""Tests for selfdoc.utils -- shared utility functions."""

import json
import os

import pytest

from selfdoc.utils import detect_project_version


class TestDetectProjectVersion:
    """Tests for detect_project_version()."""

    def test_pyproject_toml(self, tmp_path):
        """Reads version from pyproject.toml [project].version."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "foo"\nversion = "1.2.3"\n'
        )
        assert detect_project_version(str(tmp_path)) == "1.2.3"

    def test_package_json(self, tmp_path):
        """Reads version from package.json when no pyproject.toml."""
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "foo", "version": "4.5.6"}))
        assert detect_project_version(str(tmp_path)) == "4.5.6"

    def test_version_file(self, tmp_path):
        """Reads version from VERSION file when no other manifests."""
        version_file = tmp_path / "VERSION"
        version_file.write_text("7.8.9\n")
        assert detect_project_version(str(tmp_path)) == "7.8.9"

    def test_version_file_strips_whitespace(self, tmp_path):
        """VERSION file content is stripped of whitespace."""
        version_file = tmp_path / "VERSION"
        version_file.write_text("  2.0.0  \n")
        assert detect_project_version(str(tmp_path)) == "2.0.0"

    def test_priority_pyproject_over_package_json(self, tmp_path):
        """pyproject.toml takes priority over package.json."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "foo"\nversion = "1.0.0"\n'
        )
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "foo", "version": "2.0.0"}))
        assert detect_project_version(str(tmp_path)) == "1.0.0"

    def test_priority_package_json_over_version_file(self, tmp_path):
        """package.json takes priority over VERSION file."""
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "foo", "version": "3.0.0"}))
        version_file = tmp_path / "VERSION"
        version_file.write_text("4.0.0\n")
        assert detect_project_version(str(tmp_path)) == "3.0.0"

    def test_fallback_when_no_files(self, tmp_path):
        """Returns fallback when no manifest files exist."""
        assert detect_project_version(str(tmp_path)) == ""

    def test_custom_fallback(self, tmp_path):
        """Returns custom fallback value when specified."""
        assert detect_project_version(str(tmp_path), fallback="0.0.0") == "0.0.0"

    def test_malformed_pyproject_toml(self, tmp_path):
        """Falls through to next source on malformed pyproject.toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("this is not valid toml [[[")
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "foo", "version": "5.0.0"}))
        assert detect_project_version(str(tmp_path)) == "5.0.0"

    def test_malformed_package_json(self, tmp_path):
        """Falls through to next source on malformed package.json."""
        pkg = tmp_path / "package.json"
        pkg.write_text("{invalid json")
        version_file = tmp_path / "VERSION"
        version_file.write_text("6.0.0\n")
        assert detect_project_version(str(tmp_path)) == "6.0.0"

    def test_pyproject_without_version(self, tmp_path):
        """Falls through when pyproject.toml has no version field."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "foo"\n')
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "foo", "version": "8.0.0"}))
        assert detect_project_version(str(tmp_path)) == "8.0.0"

    def test_package_json_without_version(self, tmp_path):
        """Falls through when package.json has no version field."""
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "foo"}))
        version_file = tmp_path / "VERSION"
        version_file.write_text("9.0.0\n")
        assert detect_project_version(str(tmp_path)) == "9.0.0"

    def test_empty_version_file(self, tmp_path):
        """Returns fallback when VERSION file is empty."""
        version_file = tmp_path / "VERSION"
        version_file.write_text("")
        assert detect_project_version(str(tmp_path), fallback="x") == "x"

    def test_declared_go_language_reads_version_file(self, tmp_path):
        """A declared Go source language picks VERSION over an incidental package.json.

        A polyglot Go repository often carries a private package.json at its
        root (a browser-test harness), whose version field is conventionally
        0.0.0 and is never the project's version. The declared source language
        in selfdoc.json picks the manifest, exactly as it does for the project
        name.
        """
        (tmp_path / "selfdoc.json").write_text(
            json.dumps({"source": [{"language": "go", "path": "."}]})
        )
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "harness", "private": True, "version": "0.0.0"})
        )
        (tmp_path / "VERSION").write_text("0.3.0\n")
        assert detect_project_version(str(tmp_path)) == "0.3.0"

    def test_declared_python_language_reads_pyproject(self, tmp_path):
        """A declared Python source language picks pyproject.toml."""
        (tmp_path / "selfdoc.json").write_text(
            json.dumps({"source": [{"language": "python", "path": "."}]})
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "foo"\nversion = "1.2.3"\n'
        )
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "foo", "version": "9.9.9"})
        )
        assert detect_project_version(str(tmp_path)) == "1.2.3"

    def test_declared_js_language_reads_package_json(self, tmp_path):
        """A declared JS source language picks package.json over pyproject.toml."""
        (tmp_path / "selfdoc.json").write_text(
            json.dumps({"source": [{"language": "javascript", "path": "."}]})
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "foo"\nversion = "1.2.3"\n'
        )
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "foo", "version": "9.9.9"})
        )
        assert detect_project_version(str(tmp_path)) == "9.9.9"

    def test_declared_language_without_its_manifest_falls_through(self, tmp_path):
        """A declared language whose manifest is absent uses the original chain."""
        (tmp_path / "selfdoc.json").write_text(
            json.dumps({"source": [{"language": "go", "path": "."}]})
        )
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "foo", "version": "9.9.9"})
        )
        assert detect_project_version(str(tmp_path)) == "9.9.9"
