"""Tests for `selfblog assembly sync-workflow`, the deploy workflow's writer.

`assembly init` used to be the only writer of the assembly repo's
``deploy.yml``, so the deployed copy froze at whatever the template said the
day the repo was created.  A released flag change then broke the deploy for
every project at once, and the repair was a hand-regeneration and a manual
push.  The workflow is now a regenerated artifact: this command rewrites it,
pushes it only when its content actually differs, and the release path runs
it so the deployed copy can never fall behind the generator by more than one
release.
"""

import base64
import json
import os
import subprocess

import pytest

from selfblog.assembly import WORKFLOW_PATH, generate_workflow_yaml, git_blob_sha1
from selfblog.cli import _cmd_assembly_sync_workflow

PAGES_PROJECT = "unified-site"
CANONICAL_BASE = "https://docs.example.com"


def _setup_project(tmp_path, config_overrides=None):
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0", "indexed": True}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "assembly": {"repo": "owner/assembly", "pages_project": PAGES_PROJECT},
        "topology": {"slug": "myproject", "docs_base": CANONICAL_BASE},
    }
    if config_overrides:
        config.update(config_overrides)
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text("")
    return tmp_path


class FakeAssemblyRepo:
    """A mocked Git Data API for one assembly repo, with persistent state."""

    def __init__(self, blobs=None):
        self.blobs = dict(blobs or {})
        self.commits = 0
        self.uploads = 0

    def __call__(self, cmd, **kwargs):
        joined = " ".join(str(c) for c in cmd)
        stdout = ""
        if "/git/ref/heads/" in joined:
            stdout = "headsha"
        elif "/git/commits/headsha" in joined:
            stdout = "basetree"
        elif "/git/trees/basetree" in joined:
            stdout = json.dumps({
                "truncated": False,
                "tree": [
                    {"path": p, "type": "blob", "mode": "100644",
                     "sha": git_blob_sha1(d)}
                    for p, d in sorted(self.blobs.items())
                ],
            })
        elif "/git/blobs" in joined:
            payload = json.loads(kwargs["input"])
            self._pending = base64.b64decode(payload["content"])
            self.uploads += 1
            stdout = "newblob"
        elif "/git/trees" in joined:
            for entry in json.loads(kwargs["input"])["tree"]:
                if entry["sha"] is None:
                    self.blobs.pop(entry["path"], None)
                else:
                    self.blobs[entry["path"]] = self._pending
            stdout = "newtree"
        elif "/git/commits" in joined:
            self.commits += 1
            stdout = "newcommit"
        elif "/git/refs/heads/" in joined:
            stdout = "newcommit"
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout=stdout, stderr="",
        )


@pytest.fixture()
def project(tmp_path, monkeypatch):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# -- the writer ---------------------------------------------------------------


def test_sync_writes_the_workflow_when_the_repo_has_none(project, monkeypatch, capsys):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    assert WORKFLOW_PATH in remote.blobs
    assert remote.commits == 1
    assert "Synced" in capsys.readouterr().out


def test_the_written_workflow_pins_the_given_version(project, monkeypatch):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    assert b"'selfblog==1.2.3'" in remote.blobs[WORKFLOW_PATH]


def test_the_written_workflow_carries_the_projects_config(project, monkeypatch):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    content = remote.blobs[WORKFLOW_PATH].decode()
    assert f"--project-name '{PAGES_PROJECT}'" in content
    assert f"--canonical-base '{CANONICAL_BASE}'" in content


def test_the_pin_defaults_to_the_running_selfblog(project, monkeypatch):
    from selfblog import __version__

    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None)

    assert f"'selfblog=={__version__}'".encode() in remote.blobs[WORKFLOW_PATH]


# -- idempotence --------------------------------------------------------------


def test_running_the_writer_twice_is_a_no_op(project, monkeypatch, capsys):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")
    first_commits, first_uploads = remote.commits, remote.uploads
    capsys.readouterr()

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    assert remote.commits == first_commits, "second run must not commit"
    assert remote.uploads == first_uploads, "second run must not upload a blob"
    assert "already current" in capsys.readouterr().out


def test_a_workflow_that_matches_is_recognized_without_a_push(project, monkeypatch):
    """A repo already holding the generated bytes gets nothing pushed at all."""
    content = generate_workflow_yaml(
        PAGES_PROJECT, CANONICAL_BASE, "", "", "1.2.3",
    ).encode()
    remote = FakeAssemblyRepo({WORKFLOW_PATH: content})
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    assert remote.commits == 0


def test_a_changed_pin_does_push(project, monkeypatch):
    content = generate_workflow_yaml(
        PAGES_PROJECT, CANONICAL_BASE, "", "", "1.2.3",
    ).encode()
    remote = FakeAssemblyRepo({WORKFLOW_PATH: content})
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.4")

    assert remote.commits == 1
    assert b"'selfblog==1.2.4'" in remote.blobs[WORKFLOW_PATH]


# -- configuration requirements -----------------------------------------------


def test_sync_requires_a_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_sync_workflow(None)


def test_sync_requires_an_assembly_repo(tmp_path, monkeypatch):
    _setup_project(tmp_path, {"assembly": {"pages_project": PAGES_PROJECT}})
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_sync_workflow(None)


def test_sync_requires_a_pages_project(tmp_path, monkeypatch):
    _setup_project(tmp_path, {"assembly": {"repo": "owner/assembly"}})
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_sync_workflow(None)


def test_sync_requires_a_docs_base(tmp_path, monkeypatch):
    _setup_project(tmp_path, {"topology": {"slug": "myproject"}})
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_sync_workflow(None)


# -- release wiring -----------------------------------------------------------


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _post_release_hook():
    return os.path.join(
        _repo_root(), ".rlsbl-monorepo", "releasables", "selfdoc", "hooks",
        "post-release.sh",
    )


def test_the_release_path_syncs_the_workflow():
    """Every release regenerates the deployed workflow before dispatching."""
    with open(_post_release_hook(), encoding="utf-8") as f:
        hook = f.read()
    assert "selfblog assembly sync-workflow" in hook


def test_the_release_syncs_before_it_dispatches():
    """A dispatch must run against the workflow this release just wrote."""
    with open(_post_release_hook(), encoding="utf-8") as f:
        hook = f.read()
    assert (hook.index("selfblog assembly sync-workflow")
            < hook.index("selfblog assembly push"))
