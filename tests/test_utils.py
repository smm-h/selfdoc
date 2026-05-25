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
