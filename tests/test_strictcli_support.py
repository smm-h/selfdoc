"""Tests for selfdoc.strictcli_support -- strictcli detection, introspection, and page generation."""

import json
import os
import stat
import textwrap

import pytest

from selfdoc.strictcli_support import (
    uses_strictcli,
    extract_cli_structure,
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
def strictcli_app_source():
    """Return source code for a realistic strictcli app definition."""
    return textwrap.dedent('''\
        import strictcli

        app = strictcli.App(name="testapp", version="1.0", help="A test app")

        @app.command("deploy", help="deploy stuff")
        @strictcli.flag("target", type=str, help="deploy target", default="prod")
        @strictcli.flag("dry-run", type=bool, help="dry run mode", short="n")
        def deploy(target, dry_run):
            pass

        config = app.group("config", help="configuration")

        @config.command("show", help="show config")
        @strictcli.flag("format", type=str, help="output format", default="text")
        def config_show(format):
            pass
    ''')


# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------


class TestUsesStrictcli:
    """Test detection of strictcli imports."""

    def test_import_strictcli(self, src_dir, tmp_path):
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write("import strictcli\n")

        assert uses_strictcli(["src/"], str(tmp_path)) is True

    def test_from_strictcli_import_app(self, src_dir, tmp_path):
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write("from strictcli import App\n")

        assert uses_strictcli(["src/"], str(tmp_path)) is True

    def test_from_strictcli_submodule(self, src_dir, tmp_path):
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write("from strictcli.something import X\n")

        assert uses_strictcli(["src/"], str(tmp_path)) is True

    def test_no_strictcli(self, src_dir, tmp_path):
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write("import argparse\n")

        assert uses_strictcli(["src/"], str(tmp_path)) is False

    def test_strictcli_in_string(self, src_dir, tmp_path):
        """AST ignores strictcli mentioned in strings."""
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write('x = "import strictcli"\n')

        assert uses_strictcli(["src/"], str(tmp_path)) is False

    def test_strictcli_in_comment(self, src_dir, tmp_path):
        """AST ignores strictcli mentioned in comments."""
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write("# import strictcli\nx = 1\n")

        assert uses_strictcli(["src/"], str(tmp_path)) is False

    def test_empty_source_path(self, tmp_path):
        """Non-existent source path returns False."""
        assert uses_strictcli(["nonexistent/"], str(tmp_path)) is False

    def test_nested_file(self, src_dir, tmp_path):
        """Detects strictcli in nested subdirectories."""
        sub = os.path.join(src_dir, "pkg", "sub")
        os.makedirs(sub)
        with open(os.path.join(sub, "app.py"), "w") as f:
            f.write("import strictcli\n")

        assert uses_strictcli(["src/"], str(tmp_path)) is True


# ---------------------------------------------------------------------------
# Introspection tests
# ---------------------------------------------------------------------------


class TestExtractCliStructure:
    """Test AST-based extraction of CLI structure."""

    def test_basic_extraction(self, src_dir, tmp_path, strictcli_app_source):
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write(strictcli_app_source)

        result = extract_cli_structure(["src/"], str(tmp_path))

        assert result is not None
        assert result["app_name"] == "testapp"
        assert result["app_version"] == "1.0"
        assert result["app_help"] == "A test app"

    def test_commands_extracted(self, src_dir, tmp_path, strictcli_app_source):
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write(strictcli_app_source)

        result = extract_cli_structure(["src/"], str(tmp_path))

        assert len(result["commands"]) == 1
        deploy = result["commands"][0]
        assert deploy["name"] == "deploy"
        assert deploy["help"] == "deploy stuff"

    def test_flags_extracted(self, src_dir, tmp_path, strictcli_app_source):
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write(strictcli_app_source)

        result = extract_cli_structure(["src/"], str(tmp_path))

        deploy = result["commands"][0]
        assert len(deploy["flags"]) == 2

        # Find the target flag
        target_flag = next(f for f in deploy["flags"] if f["name"] == "target")
        assert target_flag["type"] == "str"
        assert target_flag["help"] == "deploy target"
        assert target_flag["default"] == "prod"
        assert target_flag["short"] is None

        # Find the dry-run flag
        dry_run_flag = next(f for f in deploy["flags"] if f["name"] == "dry-run")
        assert dry_run_flag["type"] == "bool"
        assert dry_run_flag["help"] == "dry run mode"
        assert dry_run_flag["short"] == "n"

    def test_groups_extracted(self, src_dir, tmp_path, strictcli_app_source):
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write(strictcli_app_source)

        result = extract_cli_structure(["src/"], str(tmp_path))

        assert len(result["groups"]) == 1
        config_group = result["groups"][0]
        assert config_group["name"] == "config"
        assert config_group["help"] == "configuration"

    def test_group_commands_extracted(self, src_dir, tmp_path, strictcli_app_source):
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write(strictcli_app_source)

        result = extract_cli_structure(["src/"], str(tmp_path))

        config_group = result["groups"][0]
        assert len(config_group["commands"]) == 1
        show_cmd = config_group["commands"][0]
        assert show_cmd["name"] == "show"
        assert show_cmd["help"] == "show config"
        assert len(show_cmd["flags"]) == 1
        assert show_cmd["flags"][0]["name"] == "format"
        assert show_cmd["flags"][0]["default"] == "text"

    def test_no_app_returns_none(self, src_dir, tmp_path):
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write("import strictcli\nx = 1\n")

        result = extract_cli_structure(["src/"], str(tmp_path))
        assert result is None

    def test_no_source_returns_none(self, tmp_path):
        result = extract_cli_structure(["nonexistent/"], str(tmp_path))
        assert result is None

    def test_arg_extraction(self, src_dir, tmp_path):
        """Test extraction of @strictcli.arg decorators."""
        source = textwrap.dedent('''\
            import strictcli

            app = strictcli.App(name="myapp", version="0.1", help="test")

            @app.command("greet", help="greet someone")
            @strictcli.arg("name", help="person to greet", required=True)
            @strictcli.arg("title", help="optional title", required=False)
            def greet(name, title):
                pass
        ''')
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write(source)

        result = extract_cli_structure(["src/"], str(tmp_path))

        assert result is not None
        greet = result["commands"][0]
        assert len(greet["args"]) == 2

        name_arg = next(a for a in greet["args"] if a["name"] == "name")
        assert name_arg["help"] == "person to greet"
        assert name_arg["required"] is True

        title_arg = next(a for a in greet["args"] if a["name"] == "title")
        assert title_arg["required"] is False

    def test_from_import_style(self, src_dir, tmp_path):
        """Test extraction with ``from strictcli import App`` style."""
        source = textwrap.dedent('''\
            from strictcli import App

            app = App(name="fromapp", version="2.0", help="from import")

            @app.command("run", help="run it")
            def run_cmd():
                pass
        ''')
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write(source)

        result = extract_cli_structure(["src/"], str(tmp_path))

        assert result is not None
        assert result["app_name"] == "fromapp"
        assert len(result["commands"]) == 1
        assert result["commands"][0]["name"] == "run"


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

        # Set up a project with a strictcli app
        src_dir = os.path.join(tmp_path, "myapp")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "__init__.py"), "w") as f:
            f.write("")
        cli_src = textwrap.dedent('''\
            import strictcli

            app = strictcli.App(name="myapp", version="1.0", help="A test app")

            @app.command("deploy", help="Deploy the app to one or more configured remote environments with health checks and rollback.")
            def deploy():
                pass
        ''')
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write(cli_src)

        docs_dir = os.path.join(tmp_path, "docs")
        os.makedirs(docs_dir)

        config = {
            "language": "python",
            "source": ["myapp/"],
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
        """code-help directive + strictcli import produces a hard error."""
        from selfdoc.check import check_docs

        config = {
            "language": "python",
            "source": ["src/"],
            "docs": "docs/",
            "output": "docs/_build/",
            "base_url": "https://example.com",
        }
        with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
            json.dump(config, f)

        # Source with strictcli import
        src_dir = os.path.join(tmp_path, "src")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write("import strictcli\n")
        with open(os.path.join(src_dir, "__init__.py"), "w") as f:
            f.write("")

        # Docs with code-help directive
        docs_dir = os.path.join(tmp_path, "docs")
        os.makedirs(docs_dir)
        with open(os.path.join(docs_dir, "cli.md"), "w") as f:
            f.write('# CLI\n\n:-: code-help path="src"\n')

        with pytest.raises(RuntimeError, match="strictcli"):
            check_docs(str(tmp_path))

    def test_strictcli_without_code_help_ok(self, tmp_path):
        """strictcli import without code-help directive does not error."""
        from selfdoc.check import check_docs

        config = {
            "language": "python",
            "source": ["src/"],
            "docs": "docs/",
            "output": "docs/_build/",
            "base_url": "https://example.com",
        }
        with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
            json.dump(config, f)

        src_dir = os.path.join(tmp_path, "src")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "cli.py"), "w") as f:
            f.write("import strictcli\n")
        with open(os.path.join(src_dir, "__init__.py"), "w") as f:
            f.write("")

        docs_dir = os.path.join(tmp_path, "docs")
        os.makedirs(docs_dir)
        with open(os.path.join(docs_dir, "api.md"), "w") as f:
            f.write('# API\n\n:-: ref path="src"\n')

        # Should not raise
        result = check_docs(str(tmp_path))
        assert result is not None

    def test_code_help_without_strictcli_ok(self, tmp_path):
        """code-help directive without strictcli import does not error."""
        from selfdoc.check import check_docs

        config = {
            "language": "python",
            "source": ["src/"],
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
