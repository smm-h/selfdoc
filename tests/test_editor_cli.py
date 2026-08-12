"""The editor's command surface: `selfblog editor list-repos` and `serve`.

`serve` is not exercised end to end here -- it blocks until interrupted, and
the wire behaviour it exposes has its own module.  What is asserted here is
the registration: the flags that exist, the ones with no default (and are
therefore required), the effect classification, and the refusals a bad
registry or a missing asset tree produce before anything binds a port.
"""

from __future__ import annotations

import os

from selfblog.cli import app


def _registry(tmp_path, body, name="registry.toml"):
    path = os.path.join(str(tmp_path), name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


class TestRegistration:
    def test_the_editor_group_exists(self):
        assert "editor" in app._groups

    def test_it_has_both_commands(self):
        commands = app._groups["editor"].commands
        assert set(commands) >= {"serve", "list-repos"}

    def test_list_repos_is_read_only(self):
        assert app._groups["editor"].commands["list-repos"].effect == "read_only"

    def test_serve_is_mutating_and_not_consequential(self):
        serve = app._groups["editor"].commands["serve"]
        assert serve.effect == "mutating"
        assert serve.consequential is False

    def test_serve_refuses_a_preview_with_a_reason(self, tmp_path):
        """An interactive server has no set of effects to record at launch.

        The refusal belongs at parse time (``dry_run_supported=False``), but
        strictcli exposes that on ``App.command`` only, not on
        ``Group.command``, at this project's floor.  The handler refuses one
        step later instead -- what must never happen is a preview that binds
        a port and then performs real saves.
        """
        path = _registry(tmp_path, "")
        result = app.test([
            "editor", "serve", "--port", "0", "--registry", path, "--dry-run",
        ])
        assert result.exit_code == 1
        assert "cannot be previewed" in result.stderr

    def test_the_port_flag_has_no_default(self):
        """No default means strictcli requires it -- the port is stated."""
        port = next(
            f for f in app._groups["editor"].commands["serve"].flags
            if f.name == "port"
        )
        assert port.type is int
        assert port.default is None

    def test_help_runs(self):
        assert app.test(["editor", "--help"]).exit_code == 0
        assert app.test(["editor", "serve", "--help"]).exit_code == 0
        assert app.test(["editor", "list-repos", "--help"]).exit_code == 0

    def test_serve_refuses_without_a_port(self):
        result = app.test(["editor", "serve"])
        assert result.exit_code != 0
        assert "port" in (result.stderr + result.stdout)


class TestListRepos:
    def test_it_lists_a_hand_written_file(self, tmp_path):
        tree = os.path.join(str(tmp_path), "proj")
        os.makedirs(tree, exist_ok=True)
        path = _registry(tmp_path, f"""
[[repo]]
name = "proj"
kind = "local"
path = "{tree}"

[[repo]]
name = "afar"
kind = "remote"
repo = "smm-h/afar"
ref = "main"
cache = "{os.path.join(str(tmp_path), "cache")}"
render = false
""")
        result = app.test(["editor", "list-repos", "--registry", path])

        assert result.exit_code == 0
        assert "proj" in result.stdout
        assert tree in result.stdout
        assert "smm-h/afar@main" in result.stdout
        assert "not served yet" in result.stdout

    def test_an_empty_registry_says_so(self, tmp_path):
        path = _registry(tmp_path, "")
        result = app.test(["editor", "list-repos", "--registry", path])
        assert result.exit_code == 0
        assert "No repositories" in result.stdout

    def test_a_malformed_registry_refuses_and_names_the_offender(self, tmp_path):
        path = _registry(tmp_path, """
[[repo]]
name = "broken"
kind = "local"
""")
        result = app.test(["editor", "list-repos", "--registry", path])
        assert result.exit_code == 1
        assert "broken" in result.stderr
        assert "path" in result.stderr

    def test_a_missing_registry_names_the_path(self, tmp_path):
        missing = os.path.join(str(tmp_path), "nope.toml")
        result = app.test(["editor", "list-repos", "--registry", missing])
        assert result.exit_code == 1
        assert "nope.toml" in result.stderr


class TestServeRefusesBeforeBinding:
    def test_a_malformed_registry_stops_it(self, tmp_path):
        path = _registry(tmp_path, 'port = 1\n')
        result = app.test([
            "editor", "serve", "--port", "0", "--registry", path,
        ])
        assert result.exit_code == 1
        assert "port" in result.stderr

    def test_missing_tinymoon_assets_stop_it(self, tmp_path):
        path = _registry(tmp_path, "")
        nowhere = os.path.join(str(tmp_path), "nowhere")
        result = app.test([
            "editor", "serve", "--port", "0", "--registry", path,
            "--tinymoon-assets", nowhere,
        ])
        assert result.exit_code == 1
        assert "nowhere" in result.stderr

    def test_an_asset_tree_without_the_editor_tier_stops_it(self, tmp_path):
        from selfblog.editor_assets import TINYMOON_REQUIRED

        assets = os.path.join(str(tmp_path), "assets")
        for rel in TINYMOON_REQUIRED:
            if rel == "js/editor.js":
                continue
            full = os.path.join(assets, *rel.split("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write("/* stub */\n")

        path = _registry(tmp_path, "")
        result = app.test([
            "editor", "serve", "--port", "0", "--registry", path,
            "--tinymoon-assets", assets,
        ])
        assert result.exit_code == 1
        assert "js/editor.js" in result.stderr
