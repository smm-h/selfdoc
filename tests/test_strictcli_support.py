"""Tests for selfdoc.strictcli_support -- strictcli detection, introspection, and page generation."""

import json
import os
import stat
import textwrap

import pytest

from selfdoc.strictcli_support import (
    uses_strictcli,
    extract_cli_structure,
    read_schema_json,
    generate_cli_pages,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def src_dir(tmp_path):
    """Create a source directory for detection tests."""
    d = os.path.join(tmp_path, "src")
    os.makedirs(d)
    return d


@pytest.fixture()
def schema_json():
    """Return a realistic schema.json dict for a strictcli app."""
    return {
        "name": "testapp",
        "project_id": "testapp",
        "version": "1.0",
        "help": "A test app",
        "env_prefix": None,
        "config": False,
        "global_flags": [],
        "commands": {
            "deploy": {
                "name": "deploy",
                "help": "deploy stuff",
                "flags": [
                    {
                        "name": "target",
                        "type": "str",
                        "help": "deploy target",
                        "short": None,
                        "default": "prod",
                        "env": None,
                        "choices": None,
                        "repeatable": False,
                        "negatable": None,
                        "hidden": False,
                    },
                    {
                        "name": "dry-run",
                        "type": "bool",
                        "help": "dry run mode",
                        "short": "n",
                        "default": False,
                        "env": None,
                        "choices": None,
                        "repeatable": False,
                        "negatable": True,
                        "hidden": False,
                    },
                ],
                "args": [],
                "passthrough": False,
            },
        },
        "groups": {
            "config": {
                "name": "config",
                "help": "configuration",
                "commands": {
                    "show": {
                        "name": "show",
                        "help": "show config",
                        "flags": [
                            {
                                "name": "format",
                                "type": "str",
                                "help": "output format",
                                "short": None,
                                "default": "text",
                                "env": None,
                                "choices": ["text", "json"],
                                "repeatable": False,
                                "negatable": None,
                                "hidden": False,
                            },
                        ],
                        "args": [],
                        "passthrough": False,
                    },
                },
                "deprecated": {},
                "groups": {},
            },
        },
        "deprecated": {},
    }


def _write_schema(tmp_path, schema):
    """Write a schema.json file into .strictcli/ under tmp_path."""
    schema_dir = os.path.join(tmp_path, ".strictcli")
    os.makedirs(schema_dir, exist_ok=True)
    schema_path = os.path.join(schema_dir, "schema.json")
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema, f)
    return schema_path


# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------


class TestUsesStrictcli:
    """Test detection of strictcli via .strictcli/schema.json."""

    def test_schema_json_exists(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        assert uses_strictcli(["src/"], str(tmp_path)) is True

    def test_no_schema_json(self, tmp_path):
        assert uses_strictcli(["src/"], str(tmp_path)) is False

    def test_empty_source_paths(self, tmp_path, schema_json):
        """source_paths is ignored; only schema.json matters."""
        _write_schema(tmp_path, schema_json)
        assert uses_strictcli([], str(tmp_path)) is True

    def test_nonexistent_base_dir(self):
        assert uses_strictcli(["src/"], "/nonexistent/path") is False


# ---------------------------------------------------------------------------
# Schema reader tests
# ---------------------------------------------------------------------------


class TestReadSchemaJson:
    """Test reading and translating .strictcli/schema.json."""

    def test_returns_none_when_missing(self, tmp_path):
        result = read_schema_json(str(tmp_path))
        assert result is None

    def test_translates_app_fields(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        result = read_schema_json(str(tmp_path))

        assert result is not None
        assert result["app_name"] == "testapp"
        assert result["app_version"] == "1.0"
        assert result["app_help"] == "A test app"

    def test_commands_are_list(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        result = read_schema_json(str(tmp_path))

        assert isinstance(result["commands"], list)
        assert len(result["commands"]) == 1
        deploy = result["commands"][0]
        assert deploy["name"] == "deploy"
        assert deploy["help"] == "deploy stuff"

    def test_groups_are_list(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        result = read_schema_json(str(tmp_path))

        assert isinstance(result["groups"], list)
        assert len(result["groups"]) == 1
        config_grp = result["groups"][0]
        assert config_grp["name"] == "config"
        assert config_grp["help"] == "configuration"

    def test_group_commands_are_list(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        result = read_schema_json(str(tmp_path))

        config_grp = result["groups"][0]
        assert isinstance(config_grp["commands"], list)
        assert len(config_grp["commands"]) == 1
        show = config_grp["commands"][0]
        assert show["name"] == "show"
        assert show["help"] == "show config"

    def test_preserves_new_fields(self, tmp_path, schema_json):
        """New schema fields (choices, hidden, passthrough, etc.) are preserved."""
        _write_schema(tmp_path, schema_json)
        result = read_schema_json(str(tmp_path))

        deploy = result["commands"][0]
        assert deploy["passthrough"] is False

        dry_run_flag = next(f for f in deploy["flags"] if f["name"] == "dry-run")
        assert dry_run_flag["negatable"] is True
        assert dry_run_flag["hidden"] is False
        assert dry_run_flag["repeatable"] is False

        config_grp = result["groups"][0]
        show = config_grp["commands"][0]
        format_flag = show["flags"][0]
        assert format_flag["choices"] == ["text", "json"]

    def test_flags_extracted(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        result = read_schema_json(str(tmp_path))

        deploy = result["commands"][0]
        assert len(deploy["flags"]) == 2

        target_flag = next(f for f in deploy["flags"] if f["name"] == "target")
        assert target_flag["type"] == "str"
        assert target_flag["help"] == "deploy target"
        assert target_flag["default"] == "prod"
        assert target_flag["short"] is None

        dry_run_flag = next(f for f in deploy["flags"] if f["name"] == "dry-run")
        assert dry_run_flag["type"] == "bool"
        assert dry_run_flag["help"] == "dry run mode"
        assert dry_run_flag["short"] == "n"

    def test_malformed_json_raises(self, tmp_path):
        schema_dir = os.path.join(tmp_path, ".strictcli")
        os.makedirs(schema_dir)
        with open(os.path.join(schema_dir, "schema.json"), "w") as f:
            f.write("not valid json{{{")

        with pytest.raises(json.JSONDecodeError):
            read_schema_json(str(tmp_path))

    def test_empty_schema(self, tmp_path):
        """Minimal schema with no commands or groups."""
        _write_schema(tmp_path, {"name": "empty", "project_id": "empty", "version": "0.1", "help": ""})
        result = read_schema_json(str(tmp_path))

        assert result["app_name"] == "empty"
        assert result["commands"] == []
        assert result["groups"] == []


# ---------------------------------------------------------------------------
# project_id validation tests
# ---------------------------------------------------------------------------


def _write_pyproject(tmp_path, name):
    """Write a minimal pyproject.toml with the given project name."""
    content = f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
    with open(os.path.join(tmp_path, "pyproject.toml"), "w", encoding="utf-8") as f:
        f.write(content)


class TestProjectIdValidation:
    """Test that read_schema_json validates the project_id field."""

    def test_schema_project_id_missing(self, tmp_path):
        """Schema without project_id raises ValueError."""
        _write_schema(tmp_path, {
            "name": "testapp",
            "version": "1.0",
            "help": "test",
            "commands": {},
            "groups": {},
        })
        with pytest.raises(ValueError, match="Schema missing project_id field"):
            read_schema_json(str(tmp_path))

    def test_schema_project_id_mismatch(self, tmp_path):
        """Schema project_id that doesn't match project name raises ValueError."""
        _write_pyproject(tmp_path, "testapp")
        _write_schema(tmp_path, {
            "name": "testapp",
            "project_id": "wrong",
            "version": "1.0",
            "help": "test",
            "commands": {},
            "groups": {},
        })
        with pytest.raises(ValueError, match="does not match project name"):
            read_schema_json(str(tmp_path))

    def test_schema_project_id_valid(self, tmp_path):
        """Schema project_id matching project name succeeds."""
        _write_pyproject(tmp_path, "testapp")
        _write_schema(tmp_path, {
            "name": "testapp",
            "project_id": "testapp",
            "version": "1.0",
            "help": "test",
            "commands": {},
            "groups": {},
        })
        result = read_schema_json(str(tmp_path))
        assert result is not None
        assert result["app_name"] == "testapp"

    def test_schema_project_id_skips_when_name_unknown(self, tmp_path):
        """When project name cannot be determined, skip mismatch check."""
        # No pyproject.toml, package.json, or go.mod -- _read_project_field
        # returns "unknown", so any project_id should be accepted.
        _write_schema(tmp_path, {
            "name": "testapp",
            "project_id": "anything",
            "version": "1.0",
            "help": "test",
            "commands": {},
            "groups": {},
        })
        result = read_schema_json(str(tmp_path))
        assert result is not None

    def test_schema_project_id_missing_shows_app_name(self, tmp_path):
        """Error message includes the app name for regeneration hint."""
        _write_schema(tmp_path, {
            "name": "myapp",
            "version": "1.0",
            "help": "test",
            "commands": {},
            "groups": {},
        })
        with pytest.raises(ValueError, match="myapp --dump-schema"):
            read_schema_json(str(tmp_path))


# ---------------------------------------------------------------------------
# Introspection tests (extract_cli_structure wraps read_schema_json)
# ---------------------------------------------------------------------------


class TestExtractCliStructure:
    """Test extract_cli_structure as a thin wrapper around read_schema_json."""

    def test_basic_extraction(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        result = extract_cli_structure(["src/"], str(tmp_path))

        assert result is not None
        assert result["app_name"] == "testapp"
        assert result["app_version"] == "1.0"
        assert result["app_help"] == "A test app"

    def test_commands_extracted(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        result = extract_cli_structure(["src/"], str(tmp_path))

        assert len(result["commands"]) == 1
        deploy = result["commands"][0]
        assert deploy["name"] == "deploy"
        assert deploy["help"] == "deploy stuff"

    def test_flags_extracted(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        result = extract_cli_structure(["src/"], str(tmp_path))

        deploy = result["commands"][0]
        assert len(deploy["flags"]) == 2

        target_flag = next(f for f in deploy["flags"] if f["name"] == "target")
        assert target_flag["type"] == "str"
        assert target_flag["help"] == "deploy target"
        assert target_flag["default"] == "prod"
        assert target_flag["short"] is None

        dry_run_flag = next(f for f in deploy["flags"] if f["name"] == "dry-run")
        assert dry_run_flag["type"] == "bool"
        assert dry_run_flag["help"] == "dry run mode"
        assert dry_run_flag["short"] == "n"

    def test_groups_extracted(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        result = extract_cli_structure(["src/"], str(tmp_path))

        assert len(result["groups"]) == 1
        config_group = result["groups"][0]
        assert config_group["name"] == "config"
        assert config_group["help"] == "configuration"

    def test_group_commands_extracted(self, tmp_path, schema_json):
        _write_schema(tmp_path, schema_json)
        result = extract_cli_structure(["src/"], str(tmp_path))

        config_group = result["groups"][0]
        assert len(config_group["commands"]) == 1
        show_cmd = config_group["commands"][0]
        assert show_cmd["name"] == "show"
        assert show_cmd["help"] == "show config"
        assert len(show_cmd["flags"]) == 1
        assert show_cmd["flags"][0]["name"] == "format"
        assert show_cmd["flags"][0]["default"] == "text"

    def test_no_schema_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="schema.json"):
            extract_cli_structure(["src/"], str(tmp_path))


# ---------------------------------------------------------------------------
# Page generation tests
# ---------------------------------------------------------------------------


class TestGenerateCliPages:
    """Test Markdown page generation from CLI structure."""

    @pytest.fixture()
    def cli_structure(self):
        return {
            "app_name": "testapp",
            "app_version": "1.0",
            "app_help": "A test app",
            "commands": [
                {
                    "name": "deploy",
                    "help": "deploy stuff",
                    "flags": [
                        {
                            "name": "target",
                            "type": "str",
                            "help": "deploy target",
                            "short": None,
                            "default": "prod",
                            "env": None,
                        },
                        {
                            "name": "dry-run",
                            "type": "bool",
                            "help": "dry run mode",
                            "short": "n",
                            "default": None,
                            "env": None,
                        },
                    ],
                    "args": [],
                },
            ],
            "groups": [
                {
                    "name": "config",
                    "help": "configuration",
                    "commands": [
                        {
                            "name": "show",
                            "help": "show config",
                            "flags": [
                                {
                                    "name": "format",
                                    "type": "str",
                                    "help": "output format",
                                    "short": None,
                                    "default": "text",
                                    "env": None,
                                },
                            ],
                            "args": [],
                        },
                    ],
                },
            ],
        }

    def test_returns_filenames(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        pages = generate_cli_pages(cli_structure, docs_dir)

        assert "cli-index.md" in pages
        assert "cli-deploy.md" in pages
        assert "cli-config.md" in pages

    def test_files_created(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        pages = generate_cli_pages(cli_structure, docs_dir)

        for fname in pages:
            assert os.path.isfile(os.path.join(docs_dir, fname))

    def test_frontmatter(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        with open(os.path.join(docs_dir, "cli-index.md"), "r") as f:
            content = f.read()

        assert content.startswith("---\n")
        assert "generated: true" in content
        assert "title:" in content
        assert 'nav_group: "CLI Reference"' in content
        assert "nav_order: 0" in content
        assert "order: 91" in content

    def test_command_page_nav_group(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        with open(os.path.join(docs_dir, "cli-deploy.md"), "r") as f:
            content = f.read()

        assert 'nav_group: "CLI Reference"' in content
        assert "nav_order:" in content

    def test_group_page_nav_group(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        with open(os.path.join(docs_dir, "cli-config.md"), "r") as f:
            content = f.read()

        assert 'nav_group: "CLI Reference"' in content
        assert "nav_order:" in content

    def test_html_comment_marker(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        with open(os.path.join(docs_dir, "cli-deploy.md"), "r") as f:
            content = f.read()

        assert "<!-- generated by selfdoc gen (strictcli), do not edit -->" in content

    def test_flag_table(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        with open(os.path.join(docs_dir, "cli-deploy.md"), "r") as f:
            content = f.read()

        assert "| Name | Short | Type | Default | Env | Description |" in content
        assert "`--target`" in content
        assert "`--dry-run`" in content
        assert "`-n`" in content
        assert "deploy target" in content

    def test_read_only_permissions(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        for fname in ["cli-index.md", "cli-deploy.md", "cli-config.md"]:
            path = os.path.join(docs_dir, fname)
            mode = os.stat(path).st_mode
            assert mode & stat.S_IRUSR  # owner can read
            assert not (mode & stat.S_IWUSR)  # owner cannot write

    def test_group_page_has_subcommands(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        with open(os.path.join(docs_dir, "cli-config.md"), "r") as f:
            content = f.read()

        assert "config show" in content
        assert "show config" in content
        assert "`--format`" in content

    def test_index_links(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        with open(os.path.join(docs_dir, "cli-index.md"), "r") as f:
            content = f.read()

        assert "cli-deploy.html" in content
        assert "cli-config.html" in content

    def test_overwrite_existing(self, tmp_path, cli_structure):
        """Existing read-only pages are overwritten on re-run."""
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        # Modify structure and re-generate
        cli_structure["commands"][0]["help"] = "new help text"
        generate_cli_pages(cli_structure, docs_dir)

        with open(os.path.join(docs_dir, "cli-deploy.md"), "r") as f:
            content = f.read()

        assert "new help text" in content


class TestCommandPageArgumentsTable:
    """Test that command pages render the arguments table when args are non-empty."""

    @pytest.fixture()
    def cli_structure_with_args(self):
        return {
            "app_name": "testapp",
            "app_version": "1.0",
            "app_help": "A test app",
            "commands": [
                {
                    "name": "deploy",
                    "help": "deploy stuff",
                    "flags": [],
                    "args": [
                        {
                            "name": "target",
                            "required": True,
                            "help": "deploy target",
                        },
                        {
                            "name": "extra",
                            "required": False,
                            "help": "optional extra arg",
                        },
                    ],
                },
            ],
            "groups": [],
        }

    def test_command_page_args_table_header(self, tmp_path, cli_structure_with_args):
        """Command page renders the arguments table header."""
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure_with_args, docs_dir)

        with open(os.path.join(docs_dir, "cli-deploy.md"), "r") as f:
            content = f.read()

        assert "## Arguments" in content
        assert "| Name | Required | Description |" in content
        assert "|------|----------|-------------|" in content

    def test_command_page_args_required(self, tmp_path, cli_structure_with_args):
        """Command page renders required=true as 'yes'."""
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure_with_args, docs_dir)

        with open(os.path.join(docs_dir, "cli-deploy.md"), "r") as f:
            content = f.read()

        assert "| `target` | yes | deploy target |" in content

    def test_command_page_args_optional(self, tmp_path, cli_structure_with_args):
        """Command page renders required=false as 'no'."""
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure_with_args, docs_dir)

        with open(os.path.join(docs_dir, "cli-deploy.md"), "r") as f:
            content = f.read()

        assert "| `extra` | no | optional extra arg |" in content

    def test_command_page_args_default_required(self, tmp_path):
        """When 'required' key is missing, it defaults to True (yes)."""
        structure = {
            "app_name": "testapp",
            "app_version": "1.0",
            "app_help": "A test app",
            "commands": [
                {
                    "name": "run",
                    "help": "run something",
                    "flags": [],
                    "args": [
                        {"name": "script", "help": "script to run"},
                    ],
                },
            ],
            "groups": [],
        }
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(structure, docs_dir)

        with open(os.path.join(docs_dir, "cli-run.md"), "r") as f:
            content = f.read()

        assert "| `script` | yes | script to run |" in content


class TestGroupPageArgumentsTable:
    """Test that group pages render the arguments table for subcommands with args."""

    @pytest.fixture()
    def cli_structure_group_with_args(self):
        return {
            "app_name": "testapp",
            "app_version": "1.0",
            "app_help": "A test app",
            "commands": [],
            "groups": [
                {
                    "name": "config",
                    "help": "configuration",
                    "commands": [
                        {
                            "name": "set",
                            "help": "set a config value",
                            "flags": [],
                            "args": [
                                {
                                    "name": "key",
                                    "required": True,
                                    "help": "config key",
                                },
                                {
                                    "name": "value",
                                    "required": True,
                                    "help": "config value",
                                },
                            ],
                        },
                        {
                            "name": "get",
                            "help": "get a config value",
                            "flags": [],
                            "args": [
                                {
                                    "name": "key",
                                    "required": True,
                                    "help": "config key to read",
                                },
                                {
                                    "name": "fallback",
                                    "required": False,
                                    "help": "default if missing",
                                },
                            ],
                        },
                    ],
                },
            ],
        }

    def test_group_page_args_table_header(
        self, tmp_path, cli_structure_group_with_args,
    ):
        """Group page renders the arguments table header for subcommands."""
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure_group_with_args, docs_dir)

        with open(os.path.join(docs_dir, "cli-config.md"), "r") as f:
            content = f.read()

        assert "### Arguments" in content
        assert "| Name | Required | Description |" in content
        assert "|------|----------|-------------|" in content

    def test_group_page_args_required(
        self, tmp_path, cli_structure_group_with_args,
    ):
        """Group page renders required=true as 'yes' for subcommand args."""
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure_group_with_args, docs_dir)

        with open(os.path.join(docs_dir, "cli-config.md"), "r") as f:
            content = f.read()

        assert "| `key` | yes | config key |" in content
        assert "| `value` | yes | config value |" in content

    def test_group_page_args_optional(
        self, tmp_path, cli_structure_group_with_args,
    ):
        """Group page renders required=false as 'no' for subcommand args."""
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure_group_with_args, docs_dir)

        with open(os.path.join(docs_dir, "cli-config.md"), "r") as f:
            content = f.read()

        assert "| `fallback` | no | default if missing |" in content

    def test_group_page_args_multiple_subcommands(
        self, tmp_path, cli_structure_group_with_args,
    ):
        """Group page renders arguments tables for multiple subcommands."""
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure_group_with_args, docs_dir)

        with open(os.path.join(docs_dir, "cli-config.md"), "r") as f:
            content = f.read()

        # Both subcommand sections appear
        assert "## config set" in content
        assert "## config get" in content
        # Both subcommands' args are rendered
        assert "| `key` | yes | config key to read |" in content
        assert "| `fallback` | no | default if missing |" in content


class TestDescriptionPreservation:
    """Test that user-customized CLI page descriptions survive regeneration."""

    @pytest.fixture()
    def cli_structure(self):
        return {
            "app_name": "testapp",
            "app_version": "1.0",
            "app_help": "A test app",
            "commands": [
                {
                    "name": "deploy",
                    # >= 50 chars so the default uses the chelp[:155] form
                    "help": (
                        "Deploy the application to one or more configured "
                        "remote environments with health checks."
                    ),
                    "flags": [],
                    "args": [],
                },
                {
                    "name": "ping",
                    # < 50 chars so the default uses the long-form template
                    "help": "ping a host",
                    "flags": [],
                    "args": [],
                },
            ],
            "groups": [
                {
                    "name": "config",
                    "help": (
                        "Manage configuration files for the application "
                        "across multiple environments."
                    ),
                    "commands": [],
                },
                {
                    "name": "log",
                    "help": "show logs",
                    "commands": [],
                },
            ],
        }

    def _rewrite_description(self, filepath, new_description):
        """Replace the ``description:`` line in a CLI page's frontmatter.

        Handles the read-only permissions selfdoc sets on generated files.
        """
        os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        new_lines = []
        for line in content.split("\n"):
            if line.startswith("description:"):
                new_lines.append(f'description: "{new_description}"')
            else:
                new_lines.append(line)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))

    def test_preserves_handwritten_command_description(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        deploy_path = os.path.join(docs_dir, "cli-deploy.md")
        custom = "Handwritten deployment description with full sentence ending."
        self._rewrite_description(deploy_path, custom)

        generate_cli_pages(cli_structure, docs_dir)

        with open(deploy_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert f'description: "{custom}"' in content

    def test_preserves_handwritten_group_description(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        config_path = os.path.join(docs_dir, "cli-config.md")
        custom = "Handwritten config group description with explicit purpose."
        self._rewrite_description(config_path, custom)

        generate_cli_pages(cli_structure, docs_dir)

        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert f'description: "{custom}"' in content

    def test_preserves_handwritten_index_description(self, tmp_path, cli_structure):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        index_path = os.path.join(docs_dir, "cli-index.md")
        custom = "Handwritten CLI index landing description for testapp."
        self._rewrite_description(index_path, custom)

        generate_cli_pages(cli_structure, docs_dir)

        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert f'description: "{custom}"' in content

    def test_regenerates_default_description(self, tmp_path, cli_structure):
        """When the description still matches the default, it gets regenerated."""
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        # Change the command's help text and re-generate without touching
        # the page's description. Because the existing description is the
        # default chelp[:155], it must be overwritten with the new help.
        cli_structure["commands"][0]["help"] = (
            "Updated deploy help text long enough to trigger truncation "
            "of the description so the regeneration is observable."
        )
        generate_cli_pages(cli_structure, docs_dir)

        deploy_path = os.path.join(docs_dir, "cli-deploy.md")
        with open(deploy_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Updated deploy help text" in content

    def test_regenerates_truncated_default_when_help_grows(
        self, tmp_path, cli_structure,
    ):
        """A stale chelp[:155] truncation must not be mistaken for handwritten."""
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        # Help text grows: the previous default truncation is now a prefix
        # of the new default. Preservation must treat the old value as default
        # (prefix match) and recompute, not preserve the stale prefix.
        cli_structure["commands"][0]["help"] = (
            cli_structure["commands"][0]["help"] + " Now with extra detail "
            "about the deploy lifecycle and rollback behavior on failure."
        )
        generate_cli_pages(cli_structure, docs_dir)

        deploy_path = os.path.join(docs_dir, "cli-deploy.md")
        with open(deploy_path, "r", encoding="utf-8") as f:
            content = f.read()

        # The new chelp[:155] (which extends the old prefix) should appear.
        expected_prefix = cli_structure["commands"][0]["help"][:155]
        assert f'description: "{expected_prefix}"' in content

    def test_preserves_description_across_multiple_regenerations(
        self, tmp_path, cli_structure,
    ):
        docs_dir = os.path.join(tmp_path, "docs")
        generate_cli_pages(cli_structure, docs_dir)

        deploy_path = os.path.join(docs_dir, "cli-deploy.md")
        custom = "Persistent handwritten deploy description spanning runs."
        self._rewrite_description(deploy_path, custom)

        for _ in range(3):
            generate_cli_pages(cli_structure, docs_dir)

        with open(deploy_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert f'description: "{custom}"' in content


class TestGenerateDocsPreservesCliDescriptions:
    """Regression test: generate_docs must not delete cli-*.md files as stale
    before regeneration, otherwise per-page description preservation breaks
    (the preservation logic reads the existing file, which would not exist).
    """

    def test_handwritten_cli_description_survives_generate_docs(self, tmp_path):
        from selfdoc.gen import generate_docs

        # Set up a project with a strictcli schema.json
        src_dir = os.path.join(tmp_path, "myapp")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "__init__.py"), "w") as f:
            f.write("")

        # Write schema.json
        _write_schema(tmp_path, {
            "name": "myapp",
            "project_id": "myapp",
            "version": "1.0",
            "help": "A test app",
            "commands": {
                "deploy": {
                    "name": "deploy",
                    "help": "Deploy the app to one or more configured remote environments with health checks and rollback.",
                    "flags": [],
                    "args": [],
                    "passthrough": False,
                },
            },
            "groups": {},
        })

        docs_dir = os.path.join(tmp_path, "docs")
        os.makedirs(docs_dir)

        config = {
            "source": [{"path": "myapp/", "language": "python"}],
            "docs": "docs/",
            "output": "docs/_build/",
            "base_url": "https://example.com",
        }

        # First gen creates the CLI page with the default chelp[:155] description
        generate_docs(config, base_dir=str(tmp_path))

        deploy_path = os.path.join(docs_dir, "cli-deploy.md")
        assert os.path.isfile(deploy_path)

        # Hand-edit the description
        os.chmod(deploy_path, stat.S_IRUSR | stat.S_IWUSR)
        with open(deploy_path, "r", encoding="utf-8") as f:
            content = f.read()
        custom = "Handwritten deploy description that must survive generate_docs."
        new_lines = []
        for line in content.split("\n"):
            if line.startswith("description:"):
                new_lines.append(f'description: "{custom}"')
            else:
                new_lines.append(line)
        with open(deploy_path, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))

        # Second gen must preserve the handwritten description
        generate_docs(config, base_dir=str(tmp_path))

        with open(deploy_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert f'description: "{custom}"' in content


class TestExpectedCliPageFilenames:
    """Test the helper that lists CLI page filenames for stale-cleanup gating."""

    def test_returns_empty_for_none_structure(self):
        from selfdoc.strictcli_support import expected_cli_page_filenames

        assert expected_cli_page_filenames(None) == []

    def test_includes_index_commands_and_groups(self):
        from selfdoc.strictcli_support import expected_cli_page_filenames

        structure = {
            "commands": [{"name": "deploy"}, {"name": "ping"}],
            "groups": [{"name": "config"}],
        }
        result = expected_cli_page_filenames(structure)
        assert "cli-index.md" in result
        assert "cli-deploy.md" in result
        assert "cli-ping.md" in result
        assert "cli-config.md" in result


# ---------------------------------------------------------------------------
# Check integration tests
# ---------------------------------------------------------------------------


class TestCheckIntegration:
    """Test that check.py raises on code-help + strictcli."""

    def test_code_help_with_strictcli_raises(self, tmp_path):
        """code-help directive + strictcli schema.json produces a hard error."""
        from selfdoc.check import check_docs

        config = {
            "source": [{"path": "src/", "language": "python"}],
            "docs": "docs/",
            "output": "docs/_build/",
            "base_url": "https://example.com",
        }
        with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
            json.dump(config, f)

        # Source directory
        src_dir = os.path.join(tmp_path, "src")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "__init__.py"), "w") as f:
            f.write("")

        # Schema.json to indicate strictcli usage
        _write_schema(tmp_path, {
            "name": "testapp",
            "project_id": "testapp",
            "version": "1.0",
            "help": "test",
            "commands": {},
            "groups": {},
        })

        # Docs with code-help directive
        docs_dir = os.path.join(tmp_path, "docs")
        os.makedirs(docs_dir)
        with open(os.path.join(docs_dir, "cli.md"), "w") as f:
            f.write('# CLI\n\n:-: code-help path="src"\n')

        with pytest.raises(RuntimeError, match="strictcli"):
            check_docs(str(tmp_path))

    def test_strictcli_without_code_help_ok(self, tmp_path):
        """strictcli schema.json without code-help directive does not error."""
        from selfdoc.check import check_docs

        config = {
            "source": [{"path": "src/", "language": "python"}],
            "docs": "docs/",
            "output": "docs/_build/",
            "base_url": "https://example.com",
        }
        with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
            json.dump(config, f)

        src_dir = os.path.join(tmp_path, "src")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "__init__.py"), "w") as f:
            f.write("")

        # Schema.json to indicate strictcli usage
        _write_schema(tmp_path, {
            "name": "testapp",
            "project_id": "testapp",
            "version": "1.0",
            "help": "test",
            "commands": {},
            "groups": {},
        })

        docs_dir = os.path.join(tmp_path, "docs")
        os.makedirs(docs_dir)
        with open(os.path.join(docs_dir, "api.md"), "w") as f:
            f.write('# API\n\n:-: ref path="src"\n')

        # Should not raise
        result = check_docs(str(tmp_path))
        assert result is not None

    def test_code_help_without_strictcli_ok(self, tmp_path):
        """code-help directive without strictcli schema.json does not error."""
        from selfdoc.check import check_docs

        config = {
            "source": [{"path": "src/", "language": "python"}],
            "docs": "docs/",
            "output": "docs/_build/",
            "base_url": "https://example.com",
        }
        with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
            json.dump(config, f)

        src_dir = os.path.join(tmp_path, "src")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "__init__.py"), "w") as f:
            f.write("import argparse\n")

        docs_dir = os.path.join(tmp_path, "docs")
        os.makedirs(docs_dir)
        with open(os.path.join(docs_dir, "cli.md"), "w") as f:
            f.write('# CLI\n\n:-: code-help path="src"\n')

        # Should not raise (the directive might fail to resolve, but
        # the strictcli check should not trigger)
        result = check_docs(str(tmp_path))
        assert result is not None
