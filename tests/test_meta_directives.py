"""Tests for meta directives (list-modules, table-commands, table-directives,
table-config-schema, var)."""

import os

from selfdoc.content import (
    resolve_content,
    resolve_list_modules,
    resolve_table_commands,
    resolve_table_config_schema,
    resolve_table_directives,
    resolve_var,
)

# Base dir for selfdoc's own project (repo root; source paths in
# _SELFDOC_CONFIG are relative to it)
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dir containing a pyproject.toml with a real [project] table. The repo
# root pyproject is a virtual uv workspace (no [project]), so project.*
# var resolution must be exercised against the selfdoc package dir.
_PKG_DIR = os.path.join(_PROJECT_DIR, "selfdoc")

# Minimal config matching selfdoc's own selfdoc.json
_SELFDOC_CONFIG = {
    "source": [{"path": "selfdoc/", "language": "python"}],
    "base_url": "https://selfdoc.pages.dev",
    "description": "Code-aware static site generator.",
}


# -- list-modules --------------------------------------------------------------


class TestListModules:
    def test_lists_selfdoc_modules(self):
        result = resolve_list_modules(
            {"path": "selfdoc/"},
            _SELFDOC_CONFIG,
            _PROJECT_DIR,
        )
        # Should contain known modules
        assert "**selfdoc.config**" in result
        assert "**selfdoc.build**" in result
        assert "**selfdoc.html**" in result

    def test_module_entries_have_file_paths(self):
        result = resolve_list_modules(
            {"path": "selfdoc/"},
            _SELFDOC_CONFIG,
            _PROJECT_DIR,
        )
        assert "`selfdoc/config.py`" in result
        assert "`selfdoc/build.py`" in result

    def test_modules_have_docstrings(self):
        """At least some modules should include their docstring first line."""
        result = resolve_list_modules(
            {"path": "selfdoc/"},
            _SELFDOC_CONFIG,
            _PROJECT_DIR,
        )
        # config.py has docstring "Config loader for selfdoc.json."
        assert "Config loader" in result

    def test_missing_path_attribute(self):
        result = resolve_list_modules({}, _SELFDOC_CONFIG, _PROJECT_DIR)
        assert "requires a path attribute" in result

    def test_nonexistent_directory(self):
        result = resolve_list_modules(
            {"path": "nonexistent/"},
            _SELFDOC_CONFIG,
            _PROJECT_DIR,
        )
        assert "not found" in result

    def test_via_resolve_content(self):
        """list-modules should work through the dispatcher."""
        result = resolve_content(
            "list-modules", {"path": "selfdoc/"}, [],
            _PROJECT_DIR, config=_SELFDOC_CONFIG,
        )
        assert result is not None
        assert "**selfdoc.config**" in result

    def test_list_modules_with_multi_language(self, tmp_path):
        """list-modules uses the correct extractor for the path's source entry."""
        # Set up a Go source directory
        go_dir = tmp_path / "cmd"
        go_dir.mkdir()
        (go_dir / "main.go").write_text(
            '// Package main provides the entry point.\npackage main\n'
            '\nfunc main() {}\n'
        )
        # Set up a Python source directory
        py_dir = tmp_path / "lib"
        py_dir.mkdir()
        (py_dir / "__init__.py").write_text('"""Library module."""\n')
        (py_dir / "util.py").write_text('"""Utility functions."""\n')

        config = {
            "source": [
                {"path": "lib/", "language": "python"},
                {"path": "cmd/", "language": "go"},
            ],
        }

        # list-modules on the Go path should group by package (directory)
        result = resolve_list_modules(
            {"path": "cmd/"}, config, str(tmp_path),
        )
        assert "**cmd**" in result
        assert "Package main provides the entry point." in result
        # Should NOT find Python files
        assert ".py" not in result

        # list-modules on the Python path should find .py files
        result = resolve_list_modules(
            {"path": "lib/"}, config, str(tmp_path),
        )
        assert "util.py" in result
        assert ".go" not in result

    def test_go_package_grouping(self, tmp_path):
        """Go projects group by package directory with package doc summaries."""
        # Create 7 Go packages
        packages = {
            "cmd/server": ("server", "Package server provides the HTTP server."),
            "cmd/cli": ("cli", "Package cli is the command-line interface."),
            "internal/config": ("config", "Package config handles configuration loading."),
            "internal/db": ("db", "Package db provides database access."),
            "internal/auth": ("auth", "Package auth handles authentication."),
            "pkg/api": ("api", "Package api defines the public API types."),
            "pkg/middleware": ("middleware", "Package middleware provides HTTP middleware."),
        }
        for pkg_path, (pkg_name, doc) in packages.items():
            pkg_dir = tmp_path / pkg_path
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "main.go").write_text(
                f"// {doc}\npackage {pkg_name}\n\nfunc init() {{}}\n"
            )
            # Add a test file that should be excluded
            (pkg_dir / "main_test.go").write_text(
                f"package {pkg_name}\n\nimport \"testing\"\n\n"
                f"func TestMain(t *testing.T) {{}}\n"
            )

        config = {
            "source": [
                {"path": "cmd/", "language": "go"},
                {"path": "internal/", "language": "go"},
                {"path": "pkg/", "language": "go"},
            ],
        }

        # Test cmd/ path -- should show 2 packages
        result = resolve_list_modules(
            {"path": "cmd/"}, config, str(tmp_path),
        )
        lines = [l for l in result.split("\n") if l.startswith("- ")]
        assert len(lines) == 2
        assert "**cmd/cli**" in result
        assert "**cmd/server**" in result
        assert "HTTP server." in result
        assert "command-line interface." in result

        # Test internal/ path -- should show 3 packages
        result = resolve_list_modules(
            {"path": "internal/"}, config, str(tmp_path),
        )
        lines = [l for l in result.split("\n") if l.startswith("- ")]
        assert len(lines) == 3
        assert "**internal/auth**" in result
        assert "**internal/config**" in result
        assert "**internal/db**" in result

        # Test pkg/ path -- should show 2 packages
        result = resolve_list_modules(
            {"path": "pkg/"}, config, str(tmp_path),
        )
        lines = [l for l in result.split("\n") if l.startswith("- ")]
        assert len(lines) == 2

    def test_go_test_files_excluded(self, tmp_path):
        """Go _test.go files are excluded from package grouping."""
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "handler.go").write_text(
            "// Package pkg handles things.\npackage pkg\n"
        )
        (pkg_dir / "handler_test.go").write_text(
            "package pkg\n\nimport \"testing\"\n\n"
            "func TestHandler(t *testing.T) {}\n"
        )

        config = {"source": [{"path": "pkg/", "language": "go"}]}
        result = resolve_list_modules(
            {"path": "pkg/"}, config, str(tmp_path),
        )
        assert "_test.go" not in result
        assert "**pkg**" in result

    def test_python_test_files_excluded(self, tmp_path):
        """Python test files (test_*.py, *_test.py) are excluded."""
        pkg_dir = tmp_path / "mylib"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text('"""My library."""\n')
        (pkg_dir / "core.py").write_text('"""Core module."""\n')
        (pkg_dir / "test_core.py").write_text('"""Tests for core."""\n')
        (pkg_dir / "core_test.py").write_text('"""More tests."""\n')

        config = {"source": [{"path": "mylib/", "language": "python"}]}
        result = resolve_list_modules(
            {"path": "mylib/"}, config, str(tmp_path),
        )
        assert "core.py" in result
        assert "test_core" not in result
        assert "core_test" not in result

    def test_python_per_file_behavior_preserved(self):
        """Python projects still get per-file listing with docstrings."""
        result = resolve_list_modules(
            {"path": "selfdoc/"},
            _SELFDOC_CONFIG,
            _PROJECT_DIR,
        )
        # Should still have per-file entries with file paths
        assert "**selfdoc.config**" in result
        assert "`selfdoc/config.py`" in result
        assert "Config loader" in result

    def test_unsupported_language_hard_error(self, tmp_path):
        """Unsupported language raises ValueError mentioning files=true."""
        pkg_dir = tmp_path / "src"
        pkg_dir.mkdir()
        (pkg_dir / "main.rs").write_text("fn main() {}\n")

        config = {"source": [{"path": "src/", "language": "rust"}]}
        import pytest
        with pytest.raises(ValueError, match="language 'rust' has no module extractor"):
            resolve_list_modules(
                {"path": "src/"}, config, str(tmp_path),
            )

    def test_unsupported_language_error_mentions_files_true(self, tmp_path):
        """The hard error message tells users about files=true escape hatch."""
        pkg_dir = tmp_path / "src"
        pkg_dir.mkdir()
        (pkg_dir / "main.rs").write_text("fn main() {}\n")

        config = {"source": [{"path": "src/", "language": "rust"}]}
        import pytest
        with pytest.raises(ValueError, match="files=true"):
            resolve_list_modules(
                {"path": "src/"}, config, str(tmp_path),
            )

    def test_files_true_old_behavior(self, tmp_path):
        """files=true gives per-file listing for any language."""
        # Go project with files=true should show individual files
        pkg_dir = tmp_path / "cmd"
        pkg_dir.mkdir()
        (pkg_dir / "main.go").write_text(
            "// Package main provides entry point.\npackage main\n"
            "\nfunc main() {}\n"
        )
        (pkg_dir / "util.go").write_text(
            "package main\n\nfunc helper() {}\n"
        )

        config = {"source": [{"path": "cmd/", "language": "go"}]}
        result = resolve_list_modules(
            {"path": "cmd/", "files": "true"}, config, str(tmp_path),
        )
        # files=true should show individual file paths
        assert "main.go" in result
        assert "util.go" in result

    def test_files_true_unsupported_language_no_crash(self, tmp_path):
        """files=true with unsupported language does not raise (no hard error)."""
        pkg_dir = tmp_path / "src"
        pkg_dir.mkdir()
        (pkg_dir / "main.rs").write_text("fn main() {}\n")

        config = {"source": [{"path": "src/", "language": "rust"}]}
        # Should NOT raise -- files=true bypasses the hard error
        # StubExtractor has no file_extensions so no files match,
        # but it gracefully returns "no modules found" instead of crashing.
        result = resolve_list_modules(
            {"path": "src/", "files": "true"}, config, str(tmp_path),
        )
        assert "no modules found" in result

    def test_without_config_returns_error(self):
        result = resolve_content(
            "list-modules", {"path": "selfdoc/"}, [],
            _PROJECT_DIR, config=None,
        )
        assert "requires project config" in result


# -- table-commands ------------------------------------------------------------


def _write_schema(dir_path, *, name="testcli", project_id="test-app"):
    """Write a minimal .strictcli/schema.json under *dir_path*."""
    import json

    schema_dir = dir_path / ".strictcli"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "project_id": project_id,
        "name": name,
        "version": "1.0.0",
        "help": "A test CLI",
        "commands": {"hello": {"help": "Say hello", "arguments": [], "options": []}},
        "groups": {},
    }
    (schema_dir / "schema.json").write_text(json.dumps(schema))


class TestTableCommands:
    def test_lists_selfdoc_commands_via_schema_dir(self):
        # The repo root has three schemas (root, selfdoc/, selfblog/); the
        # root schema is the selfdoc CLI, selected explicitly with schema-dir.
        result = resolve_table_commands(
            {"schema-dir": "."},
            _SELFDOC_CONFIG,
            _PROJECT_DIR,
        )
        assert "| Command | Description |" in result
        assert "`init`" in result
        assert "`build`" in result
        assert "`serve`" in result

    def test_ambiguous_discovery_is_hard_error_listing_candidates(self):
        import pytest

        from selfdoc.strictcli_support import SchemaDiscoveryError

        with pytest.raises(SchemaDiscoveryError) as exc:
            resolve_table_commands({}, _SELFDOC_CONFIG, _PROJECT_DIR)
        msg = str(exc.value)
        assert "multiple" in msg
        assert "schema-dir" in msg
        # Candidate directories are listed.
        assert "selfdoc" in msg
        assert "selfblog" in msg

    def test_absent_schema_is_hard_error(self, tmp_path):
        import pytest

        from selfdoc.strictcli_support import SchemaDiscoveryError

        with pytest.raises(SchemaDiscoveryError) as exc:
            resolve_table_commands({}, _SELFDOC_CONFIG, str(tmp_path))
        assert "no .strictcli/schema.json" in str(exc.value)

    def test_root_unique_discovery(self, tmp_path):
        _write_schema(tmp_path)
        result = resolve_table_commands({}, _SELFDOC_CONFIG, str(tmp_path))
        assert "`hello`" in result
        assert "Say hello" in result

    def test_subdir_unique_discovery(self, tmp_path):
        _write_schema(tmp_path / "myapp")
        result = resolve_table_commands({}, _SELFDOC_CONFIG, str(tmp_path))
        assert "`hello`" in result

    def test_schema_dir_override(self, tmp_path):
        _write_schema(tmp_path / "myapp")
        # A second schema elsewhere would make discovery ambiguous, but the
        # explicit override pins the choice regardless.
        _write_schema(tmp_path / "other")
        result = resolve_table_commands(
            {"schema-dir": "myapp"}, _SELFDOC_CONFIG, str(tmp_path),
        )
        assert "`hello`" in result

    def test_schema_dir_override_missing_is_hard_error(self, tmp_path):
        import pytest

        from selfdoc.strictcli_support import SchemaDiscoveryError

        with pytest.raises(SchemaDiscoveryError) as exc:
            resolve_table_commands(
                {"schema-dir": "nope"}, _SELFDOC_CONFIG, str(tmp_path),
            )
        assert "schema-dir" in str(exc.value)

    def test_via_resolve_content(self):
        result = resolve_content(
            "table-commands", {"schema-dir": "."}, [],
            _PROJECT_DIR, config=_SELFDOC_CONFIG,
        )
        assert result is not None
        assert "`build`" in result


# -- table-directives ---------------------------------------------------------


class TestTableDirectives:
    def test_lists_all_core_directives(self):
        result = resolve_table_directives()
        assert "| Directive | Description |" in result
        assert "`ref`" in result
        assert "`table-schema`" in result
        assert "`callout-note`" in result
        assert "`list-modules`" in result
        assert "`var`" in result

    def test_sorted_alphabetically(self):
        result = resolve_table_directives()
        lines = [l for l in result.split("\n") if l.startswith("| `")]
        names = []
        for line in lines:
            # Extract directive name from "| `name` | ... |"
            name = line.split("`")[1]
            names.append(name)
        assert names == sorted(names)

    def test_via_resolve_content(self):
        result = resolve_content("table-directives", {}, [], _PROJECT_DIR)
        assert result is not None
        assert "`ref`" in result


# -- table-config-schema -------------------------------------------------------


class TestTableConfigSchema:
    def test_lists_config_fields(self):
        result = resolve_table_config_schema()
        assert "| Field | Required | Description |" in result
        assert "`source`" in result
        assert "`base_url`" in result

    def test_required_fields_marked(self):
        result = resolve_table_config_schema()
        # base_url is required (source is not: a codeless project has none)
        for line in result.split("\n"):
            if "`base_url`" in line:
                assert "| yes |" in line
                break
        else:
            raise AssertionError("base_url field not found")

    def test_optional_fields_marked(self):
        result = resolve_table_config_schema()
        # docs is optional
        for line in result.split("\n"):
            if "`docs`" in line:
                assert "| no |" in line
                break
        else:
            raise AssertionError("docs field not found")

    def test_internal_fields_excluded(self):
        result = resolve_table_config_schema()
        # twitter is internal
        assert "`twitter`" not in result

    def test_via_resolve_content(self):
        result = resolve_content("table-config-schema", {}, [], _PROJECT_DIR)
        assert result is not None
        assert "`source`" in result


# -- var -----------------------------------------------------------------------


class TestVar:
    def test_project_language(self):
        result = resolve_var(
            {"key": "project.language"},
            _SELFDOC_CONFIG,
            _PROJECT_DIR,
        )
        assert result == "python"

    def test_project_description_from_config(self):
        result = resolve_var(
            {"key": "project.description"},
            _SELFDOC_CONFIG,
            _PROJECT_DIR,
        )
        assert result == "Code-aware static site generator."

    def test_project_description_falls_back_to_pyproject(self):
        config_no_desc = {
            "source": [{"path": "selfdoc/", "language": "python"}],
            "base_url": "https://example.com",
        }
        result = resolve_var(
            {"key": "project.description"},
            config_no_desc,
            _PKG_DIR,
        )
        # Should read from pyproject.toml
        assert "static site generator" in result.lower()

    def test_project_name(self):
        result = resolve_var(
            {"key": "project.name"},
            _SELFDOC_CONFIG,
            _PKG_DIR,
        )
        assert result == "selfdoc"

    def test_project_version(self):
        result = resolve_var(
            {"key": "project.version"},
            _SELFDOC_CONFIG,
            _PKG_DIR,
        )
        # Should be a semver-like string
        assert "." in result
        assert result != "unknown"

    def test_unknown_key(self):
        result = resolve_var(
            {"key": "nonexistent.field"},
            _SELFDOC_CONFIG,
            _PROJECT_DIR,
        )
        assert "unknown var key" in result

    def test_missing_key_attribute(self):
        result = resolve_var({}, _SELFDOC_CONFIG, _PROJECT_DIR)
        assert "requires a key attribute" in result

    def test_via_resolve_content(self):
        result = resolve_content(
            "var", {"key": "project.language"}, [],
            _PROJECT_DIR, config=_SELFDOC_CONFIG,
        )
        assert result == "python"

    def test_var_project_language_single(self):
        """Single-language project returns just the language name."""
        config = {
            "source": [{"path": "selfdoc/", "language": "python"}],
        }
        result = resolve_var(
            {"key": "project.language"}, config, _PROJECT_DIR,
        )
        assert result == "python"

    def test_var_project_language_multi(self):
        """Multi-language project returns comma-separated languages."""
        config = {
            "source": [
                {"path": "selfdoc/", "language": "python"},
                {"path": "cmd/", "language": "go"},
            ],
        }
        result = resolve_var(
            {"key": "project.language"}, config, _PROJECT_DIR,
        )
        assert result == "python, go"

    def test_var_project_language_multi_deduplicates(self):
        """Duplicate languages are deduplicated."""
        config = {
            "source": [
                {"path": "pkg_a/", "language": "python"},
                {"path": "pkg_b/", "language": "python"},
            ],
        }
        result = resolve_var(
            {"key": "project.language"}, config, _PROJECT_DIR,
        )
        assert result == "python"

    def test_without_config_returns_error(self):
        result = resolve_content(
            "var", {"key": "project.name"}, [],
            _PROJECT_DIR, config=None,
        )
        assert "requires project config" in result
