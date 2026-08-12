"""Where the editor's front-end assets come from, stated rather than guessed.

The authoring surface is tinymoon's editor component, which is a tier of
files inside tinymoon's asset tree.  There are exactly two places that tree
can come from and the caller picks one; neither is tried-then-abandoned.  A
tree that is missing the editor tier is refused before the server binds,
because the alternative is a shell that loads and an editor that never
mounts.
"""

from __future__ import annotations

import os

import pytest

from selfblog.editor_assets import (
    TINYMOON_EDITOR_TIER,
    TINYMOON_REQUIRED,
    AssetsError,
    resolve_tinymoon_assets,
    ui_assets_path,
)


def _fake_tinymoon(tmp_path, omit=()):
    """A tinymoon asset tree with every file the editor shell needs."""
    root = os.path.join(str(tmp_path), "assets")
    for rel in TINYMOON_REQUIRED:
        if rel in omit:
            continue
        full = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write("/* stub */\n")
    os.makedirs(root, exist_ok=True)
    return root


class TestTheTierIsRequired:
    def test_the_editor_tier_is_part_of_what_is_required(self):
        for rel in TINYMOON_EDITOR_TIER:
            assert rel in TINYMOON_REQUIRED

    def test_a_complete_tree_resolves(self, tmp_path):
        root = _fake_tinymoon(tmp_path)
        path, source = resolve_tinymoon_assets(root)
        assert path == root
        assert source == root

    def test_a_tree_without_the_editor_tier_is_refused(self, tmp_path):
        root = _fake_tinymoon(tmp_path, omit=("js/editor.js",))
        with pytest.raises(AssetsError, match="js/editor.js"):
            resolve_tinymoon_assets(root)

    def test_a_tree_without_the_completion_module_is_refused(self, tmp_path):
        root = _fake_tinymoon(tmp_path, omit=("js/completion.js",))
        with pytest.raises(AssetsError, match="js/completion.js"):
            resolve_tinymoon_assets(root)

    def test_a_tree_without_the_editor_stylesheet_is_refused(self, tmp_path):
        root = _fake_tinymoon(tmp_path, omit=("css/editor.css",))
        with pytest.raises(AssetsError, match="css/editor.css"):
            resolve_tinymoon_assets(root)

    def test_every_missing_file_is_named_at_once(self, tmp_path):
        root = _fake_tinymoon(tmp_path, omit=("js/editor.js", "css/editor.css"))
        with pytest.raises(AssetsError) as exc:
            resolve_tinymoon_assets(root)
        assert "js/editor.js" in str(exc.value)
        assert "css/editor.css" in str(exc.value)

    def test_a_path_that_is_not_a_directory_is_refused(self, tmp_path):
        nowhere = os.path.join(str(tmp_path), "nowhere")
        with pytest.raises(AssetsError, match="nowhere"):
            resolve_tinymoon_assets(nowhere)

    def test_a_tilde_path_is_expanded(self, tmp_path, monkeypatch):
        home = os.path.join(str(tmp_path), "home")
        os.makedirs(home, exist_ok=True)
        root = _fake_tinymoon(tmp_path)
        os.rename(root, os.path.join(home, "assets"))
        monkeypatch.setenv("HOME", home)

        path, _ = resolve_tinymoon_assets("~/assets")
        assert path == os.path.join(home, "assets")


class TestTheInstalledPackage:
    def test_no_installed_tinymoon_says_so_and_names_the_flag(
        self, monkeypatch,
    ):
        """The refusal has to point at the way out, not just at the absence."""
        import builtins

        real_import = builtins.__import__

        def _refuse(name, *a, **kw):
            if name == "tinymoon" or name.startswith("tinymoon."):
                raise ImportError("no tinymoon here")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _refuse)

        with pytest.raises(AssetsError, match="--tinymoon-assets"):
            resolve_tinymoon_assets("")


class TestTheShellAndTheRequiredListAgree:
    """Whatever the shell names directly is what the tree is checked for.

    The list is not the transitive module graph -- those resolve inside the
    served tree -- but every path the page and the app spell out has to be in
    it, or a tree could pass the check and 404 on load.
    """

    def _references(self):
        root = ui_assets_path()
        found = set()
        for name in ("index.html", "app.js"):
            with open(os.path.join(root, name), encoding="utf-8") as f:
                text = f.read()
            for chunk in text.split("/tinymoon/")[1:]:
                found.add(chunk.split('"')[0].split("'")[0].split(")")[0])
        return found

    def test_every_referenced_file_is_required(self):
        missing = sorted(self._references() - set(TINYMOON_REQUIRED))
        assert not missing, (
            f"the shell loads {missing} but the asset check does not require "
            f"them: a tree without them would pass and then 404"
        )

    def test_the_required_list_is_not_padded(self):
        """Every entry earns its place: a direct reference, or the tier."""
        unused = sorted(
            set(TINYMOON_REQUIRED)
            - self._references()
            - set(TINYMOON_EDITOR_TIER)
        )
        assert not unused, (
            f"{unused} are required but nothing in the shell loads them and "
            f"they are not part of the editor tier"
        )


def _app_source():
    with open(os.path.join(ui_assets_path(), "app.js"), encoding="utf-8") as f:
        return f.read()


class TestTheEditorsOwnAssets:
    def test_the_packaged_ui_directory_holds_the_app(self):
        root = ui_assets_path()
        for name in ("index.html", "app.js", "app.css"):
            assert os.path.isfile(os.path.join(root, name)), name

    def test_the_app_mounts_the_tinymoon_editor_component(self):
        source = _app_source()
        assert "createEditor" in source
        assert "setDecorations" in source


class TestTheShellWiresTheAssistanceLanes:
    """The two decoration lanes and the completion reach the server."""

    def test_the_buffer_is_sent_for_analysis(self):
        assert "/analysis?path=" in _app_source()

    def test_spelling_goes_into_the_underlay(self):
        source = _app_source()
        assert "setDecorations(" in source
        assert "tm-deco-spell" in source

    def test_lints_go_into_the_gutter(self):
        source = _app_source()
        assert "setGutterMarkers(" in source
        assert "tm-editor-marker-error" in source

    def test_the_findings_also_have_a_keyboard_reachable_control(self):
        """The gutter lane is aria-hidden; a list of buttons is the pairing."""
        source = _app_source()
        assert "renderFindings" in source
        assert "setSelection(" in source

    def test_completion_asks_the_server_for_link_targets(self):
        source = _app_source()
        assert "/api/link-targets?q=" in source
        assert "onCompletionContext" in source

    def test_the_completion_trigger_is_a_markdown_link_target(self):
        assert "LINK_TOKEN" in _app_source()


class TestThePublishSurfaceIsHonest:
    def test_the_button_never_claims_to_publish_one_post(self):
        source = _app_source().lower()
        assert "publish this post" not in source
        assert "publish post" not in source

    def test_the_button_names_the_repository(self):
        assert "Publish repository" in _app_source()

    def test_the_dialog_is_rendered_from_the_descriptor(self):
        source = _app_source()
        for field in ("scope_note", "consequential", "effect", "grants"):
            assert f"descriptor.{field}" in source, field

    def test_the_dialog_lists_what_will_publish(self):
        assert "plan.publishing" in _app_source()

    def test_consent_is_never_stored(self):
        """No don't-ask-again: nothing about consent outlives the dialog."""
        source = _app_source()
        assert "localStorage" not in source
        assert "sessionStorage" not in source
        assert source.count("approve_consequential") == 1
