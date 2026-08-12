"""The editor's repository registry: a hand-written TOML file, read strictly.

The registry is not framework config.  It is a list of repositories the
authoring app may open, written by hand on one machine, and every shape it
can be written wrong in has to refuse loudly and name the offender -- an
entry that silently disappears is an entry whose posts silently stop being
editable.
"""

from __future__ import annotations

import os

import pytest

from selfblog.editor_registry import (
    DEFAULT_REGISTRY_PATH,
    LocalRepo,
    RegistryError,
    RemoteRepo,
    load_registry,
)


def _write(tmp_path, text, name="selfblog-registry.toml"):
    path = os.path.join(str(tmp_path), name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _tree(tmp_path, name):
    path = os.path.join(str(tmp_path), name)
    os.makedirs(path, exist_ok=True)
    return path


class TestDefaultPath:
    def test_default_is_the_machine_local_ark_file(self):
        assert DEFAULT_REGISTRY_PATH == os.path.join(
            os.path.expanduser("~"), "Projects", "ark",
            "selfblog-registry.toml",
        )


class TestLocalEntries:
    def test_reads_a_hand_written_file(self, tmp_path):
        first = _tree(tmp_path, "first")
        second = _tree(tmp_path, "second")
        path = _write(tmp_path, f"""
[[repo]]
name = "first"
kind = "local"
path = "{first}"

[[repo]]
name = "second"
kind = "local"
path = "{second}"
""")
        registry = load_registry(path)

        assert registry.names() == ["first", "second"]
        assert all(isinstance(e, LocalRepo) for e in registry.entries)
        assert registry.get("first").path == first
        assert registry.get("second").path == second

    def test_an_empty_registry_is_legal(self, tmp_path):
        path = _write(tmp_path, "")
        assert load_registry(path).entries == []

    def test_a_tilde_path_is_expanded(self, tmp_path, monkeypatch):
        home = _tree(tmp_path, "home")
        os.makedirs(os.path.join(home, "proj"), exist_ok=True)
        monkeypatch.setenv("HOME", home)
        path = _write(tmp_path, """
[[repo]]
name = "proj"
kind = "local"
path = "~/proj"
""")
        assert load_registry(path).get("proj").path == os.path.join(home, "proj")

    def test_get_names_the_offender_for_an_unknown_entry(self, tmp_path):
        path = _write(tmp_path, "")
        with pytest.raises(RegistryError, match="nosuch"):
            load_registry(path).get("nosuch")


class TestRemoteEntries:
    def test_a_remote_entry_validates(self, tmp_path):
        path = _write(tmp_path, """
[[repo]]
name = "afar"
kind = "remote"
repo = "smm-h/afar"
ref = "v1.2.3"
cache = "/var/cache/afar"
render = true
""")
        entry = load_registry(path).get("afar")

        assert isinstance(entry, RemoteRepo)
        assert entry.repo == "smm-h/afar"
        assert entry.ref == "v1.2.3"
        assert entry.cache == "/var/cache/afar"
        assert entry.render is True

    def test_render_is_required(self, tmp_path):
        path = _write(tmp_path, """
[[repo]]
name = "afar"
kind = "remote"
repo = "smm-h/afar"
ref = "main"
cache = "/var/cache/afar"
""")
        with pytest.raises(RegistryError, match="afar.*render"):
            load_registry(path)

    def test_render_must_be_a_boolean(self, tmp_path):
        path = _write(tmp_path, """
[[repo]]
name = "afar"
kind = "remote"
repo = "smm-h/afar"
ref = "main"
cache = "/var/cache/afar"
render = "yes"
""")
        with pytest.raises(RegistryError, match="afar.*render.*true or false"):
            load_registry(path)

    @pytest.mark.parametrize("missing", ["repo", "ref", "cache"])
    def test_every_remote_key_is_required(self, tmp_path, missing):
        lines = [
            '[[repo]]', 'name = "afar"', 'kind = "remote"',
            'repo = "smm-h/afar"', 'ref = "main"',
            'cache = "/var/cache/afar"', 'render = false',
        ]
        kept = [ln for ln in lines if not ln.startswith(f"{missing} =")]
        path = _write(tmp_path, "\n".join(kept) + "\n")
        with pytest.raises(RegistryError, match=f"afar.*{missing}"):
            load_registry(path)


class TestMalformedShapesRefuseLoudly:
    def test_a_missing_file_names_the_path(self, tmp_path):
        missing = os.path.join(str(tmp_path), "nope.toml")
        with pytest.raises(RegistryError, match="nope.toml"):
            load_registry(missing)

    def test_unparsable_toml_names_the_path(self, tmp_path):
        path = _write(tmp_path, "[[repo]\nname = ")
        with pytest.raises(RegistryError, match="selfblog-registry.toml"):
            load_registry(path)

    def test_an_unknown_top_level_key_is_refused(self, tmp_path):
        path = _write(tmp_path, """
port = 8080

[[repo]]
name = "a"
kind = "local"
path = "."
""")
        with pytest.raises(RegistryError, match="port"):
            load_registry(path)

    def test_repo_must_be_an_array_of_tables(self, tmp_path):
        path = _write(tmp_path, 'repo = "selfdoc"\n')
        with pytest.raises(RegistryError, match="repo"):
            load_registry(path)

    def test_a_missing_name_is_refused(self, tmp_path, ):
        tree = _tree(tmp_path, "t")
        path = _write(tmp_path, f"""
[[repo]]
kind = "local"
path = "{tree}"
""")
        with pytest.raises(RegistryError, match="name"):
            load_registry(path)

    def test_a_missing_path_names_the_entry(self, tmp_path):
        path = _write(tmp_path, """
[[repo]]
name = "orphan"
kind = "local"
""")
        with pytest.raises(RegistryError, match="orphan.*path"):
            load_registry(path)

    def test_a_path_that_is_not_a_directory_names_the_entry(self, tmp_path):
        nowhere = os.path.join(str(tmp_path), "nowhere")
        path = _write(tmp_path, f"""
[[repo]]
name = "gone"
kind = "local"
path = "{nowhere}"
""")
        with pytest.raises(RegistryError, match="gone.*nowhere"):
            load_registry(path)

    def test_a_missing_kind_names_the_entry(self, tmp_path):
        tree = _tree(tmp_path, "t")
        path = _write(tmp_path, f"""
[[repo]]
name = "kindless"
path = "{tree}"
""")
        with pytest.raises(RegistryError, match="kindless.*kind"):
            load_registry(path)

    def test_an_unknown_kind_names_the_entry_and_the_kind(self, tmp_path):
        path = _write(tmp_path, """
[[repo]]
name = "weird"
kind = "submodule"
path = "."
""")
        with pytest.raises(RegistryError, match="weird.*submodule"):
            load_registry(path)

    def test_an_unknown_entry_key_names_entry_and_key(self, tmp_path):
        tree = _tree(tmp_path, "t")
        path = _write(tmp_path, f"""
[[repo]]
name = "typo"
kind = "local"
path = "{tree}"
brnach = "main"
""")
        with pytest.raises(RegistryError, match="typo.*brnach"):
            load_registry(path)

    def test_a_remote_key_on_a_local_entry_is_unknown(self, tmp_path):
        tree = _tree(tmp_path, "t")
        path = _write(tmp_path, f"""
[[repo]]
name = "mixed"
kind = "local"
path = "{tree}"
ref = "main"
""")
        with pytest.raises(RegistryError, match="mixed.*ref"):
            load_registry(path)

    def test_duplicate_names_name_the_offender(self, tmp_path):
        a = _tree(tmp_path, "a")
        b = _tree(tmp_path, "b")
        path = _write(tmp_path, f"""
[[repo]]
name = "twice"
kind = "local"
path = "{a}"

[[repo]]
name = "twice"
kind = "local"
path = "{b}"
""")
        with pytest.raises(RegistryError, match="twice"):
            load_registry(path)

    @pytest.mark.parametrize("bad", ["../escape", "with/slash", "sp ace", ""])
    def test_a_name_that_cannot_address_a_url_is_refused(self, tmp_path, bad):
        tree = _tree(tmp_path, "t")
        path = _write(tmp_path, f"""
[[repo]]
name = "{bad}"
kind = "local"
path = "{tree}"
""")
        with pytest.raises(RegistryError):
            load_registry(path)

    def test_an_entry_that_is_not_a_table_is_refused(self, tmp_path):
        path = _write(tmp_path, 'repo = ["selfdoc"]\n')
        with pytest.raises(RegistryError, match="repo"):
            load_registry(path)
