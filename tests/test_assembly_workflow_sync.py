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
from conftest import StubPyPI

from selfblog.assembly import (
    WORKFLOW_PATH,
    ToolchainPins,
    generate_workflow_yaml,
    git_blob_sha1,
)
from selfblog.cli import _cmd_assembly_sync_workflow

PAGES_PROJECT = "unified-site"
CANONICAL_BASE = "https://docs.example.com"

# The three versions the stub registry below claims are published.
PINNED_SELFDOC = "0.36.0"
PINNED_PAGEFIND = "1.4.0"
PINS = ToolchainPins(
    selfblog="1.2.3", selfdoc=PINNED_SELFDOC, pagefind=PINNED_PAGEFIND,
)


def _setup_project(tmp_path, config_overrides=None):
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
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


def test_sync_writes_the_workflow_when_the_repo_has_none(project, stub_pypi, monkeypatch, capsys):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    assert WORKFLOW_PATH in remote.blobs
    assert remote.commits == 1
    assert "Synced" in capsys.readouterr().out


def test_the_written_workflow_pins_the_given_version(project, stub_pypi, monkeypatch):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    assert b"'selfblog==1.2.3'" in remote.blobs[WORKFLOW_PATH]


def test_the_written_workflow_carries_the_projects_config(project, stub_pypi, monkeypatch):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    content = remote.blobs[WORKFLOW_PATH].decode()
    assert f"--project-name '{PAGES_PROJECT}'" in content
    assert f"--canonical-base '{CANONICAL_BASE}'" in content


def test_the_pin_defaults_to_the_running_selfblog(project, stub_pypi, monkeypatch):
    from selfblog import __version__

    stub_pypi.published["selfblog"] = ["1.0.0", __version__]
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None)

    assert f"'selfblog=={__version__}'".encode() in remote.blobs[WORKFLOW_PATH]


# -- every tool the deploy installs is pinned ---------------------------------


def test_the_written_workflow_pins_selfdoc_too(project, stub_pypi, monkeypatch):
    """selfdoc floated while selfblog was pinned, on the same install line.

    The rationale for the selfblog pin -- a released change breaking every
    project's deploy at once -- says nothing about selfblog in particular,
    and selfdoc is the tool that actually builds the docs.
    """
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3",
                                pin_selfdoc=PINNED_SELFDOC,
                                pin_pagefind=PINNED_PAGEFIND)

    content = remote.blobs[WORKFLOW_PATH].decode()
    assert f"'selfdoc=={PINNED_SELFDOC}'" in content


def test_the_written_workflow_pins_pagefind_too(project, stub_pypi, monkeypatch):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3",
                                pin_selfdoc=PINNED_SELFDOC,
                                pin_pagefind=PINNED_PAGEFIND)

    content = remote.blobs[WORKFLOW_PATH].decode()
    assert f"'pagefind[bin]=={PINNED_PAGEFIND}'" in content


def test_no_tool_on_the_install_line_floats(project, stub_pypi, monkeypatch):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    content = remote.blobs[WORKFLOW_PATH].decode()
    install = [ln for ln in content.splitlines() if "pip install" in ln]
    assert len(install) == 1, "the workflow installs its toolchain in one step"
    for spec in ("selfdoc==", "selfblog==", "pagefind[bin]=="):
        assert spec in install[0], f"{spec} is missing: that tool floats"


def test_the_selfdoc_pin_defaults_to_the_installed_selfdoc(project, stub_pypi, monkeypatch):
    from importlib.metadata import version as dist_version

    installed = dist_version("selfdoc")
    stub_pypi.published["selfdoc"] = ["0.1.0", installed]
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    assert f"'selfdoc=={installed}'".encode() in remote.blobs[WORKFLOW_PATH]


def test_the_pagefind_pin_defaults_to_the_registrys_current_release(project, stub_pypi, monkeypatch):
    """pagefind is a CI-only tool nothing here installs, so PyPI is the source."""
    stub_pypi.published["pagefind"] = ["1.0.0", "9.9.9"]
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    assert b"'pagefind[bin]==9.9.9'" in remote.blobs[WORKFLOW_PATH]


# -- a pin nobody can install is refused before it is written -----------------


def test_an_unpublished_selfblog_pin_is_refused(project, stub_pypi, monkeypatch, capsys):
    """The default pin is the RUNNING selfblog, which in a checkout is editable.

    An editable install sits ahead of the registry the moment work starts on
    the next version, so the written workflow would run a `pip install
    selfblog==X` that cannot resolve -- and the failure would surface on the
    assembly repo at the next dispatch, far from here.
    """
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    with pytest.raises(SystemExit):
        _cmd_assembly_sync_workflow(None, pin_version="9.9.9")

    err = capsys.readouterr().err
    assert "9.9.9" in err, "the unpublished version must be named"
    assert "pypi.org" in err, "the registry that was asked must be named"
    assert remote.commits == 0, "nothing may be written"


def test_an_unpublished_selfdoc_pin_is_refused(project, stub_pypi, monkeypatch, capsys):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    with pytest.raises(SystemExit):
        _cmd_assembly_sync_workflow(None, pin_version="1.2.3",
                                    pin_selfdoc="4.5.6")

    err = capsys.readouterr().err
    assert "4.5.6" in err
    assert "selfdoc" in err
    assert remote.commits == 0


def test_an_unpublished_pagefind_pin_is_refused(project, stub_pypi, monkeypatch, capsys):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    with pytest.raises(SystemExit):
        _cmd_assembly_sync_workflow(None, pin_version="1.2.3",
                                    pin_pagefind="7.7.7")

    err = capsys.readouterr().err
    assert "7.7.7" in err
    assert remote.commits == 0


def test_the_probe_runs_before_anything_is_written(project, stub_pypi, monkeypatch):
    """Fail-closed: the refusal happens before the first API call."""
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    with pytest.raises(SystemExit):
        _cmd_assembly_sync_workflow(None, pin_version="9.9.9")

    assert remote.uploads == 0
    assert stub_pypi.asked, "the registry must actually have been asked"


def test_a_registry_that_cannot_be_reached_is_a_hard_error(project, monkeypatch, capsys):
    def unreachable(package):
        raise RuntimeError("could not read https://pypi.org/pypi/x/json: refused")

    monkeypatch.setattr("selfblog.assembly.fetch_pypi_metadata", unreachable)
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    with pytest.raises(SystemExit):
        _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    assert remote.commits == 0
    assert "pypi.org" in capsys.readouterr().err


# -- idempotence --------------------------------------------------------------


def test_running_the_writer_twice_is_a_no_op(project, stub_pypi, monkeypatch, capsys):
    remote = FakeAssemblyRepo()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")
    first_commits, first_uploads = remote.commits, remote.uploads
    capsys.readouterr()

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3")

    assert remote.commits == first_commits, "second run must not commit"
    assert remote.uploads == first_uploads, "second run must not upload a blob"
    assert "already current" in capsys.readouterr().out


def test_a_workflow_that_matches_is_recognized_without_a_push(project, stub_pypi, monkeypatch):
    """A repo already holding the generated bytes gets nothing pushed at all."""
    content = generate_workflow_yaml(
        PAGES_PROJECT, CANONICAL_BASE, "", "", PINS,
    ).encode()
    remote = FakeAssemblyRepo({WORKFLOW_PATH: content})
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3",
                                pin_selfdoc=PINNED_SELFDOC,
                                pin_pagefind=PINNED_PAGEFIND)

    assert remote.commits == 0


def test_a_changed_pin_does_push(project, stub_pypi, monkeypatch):
    content = generate_workflow_yaml(
        PAGES_PROJECT, CANONICAL_BASE, "", "", PINS,
    ).encode()
    remote = FakeAssemblyRepo({WORKFLOW_PATH: content})
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.4",
                                pin_selfdoc=PINNED_SELFDOC,
                                pin_pagefind=PINNED_PAGEFIND)

    assert remote.commits == 1
    assert b"'selfblog==1.2.4'" in remote.blobs[WORKFLOW_PATH]


def test_a_changed_selfdoc_pin_does_push(project, stub_pypi, monkeypatch):
    content = generate_workflow_yaml(
        PAGES_PROJECT, CANONICAL_BASE, "", "", PINS,
    ).encode()
    remote = FakeAssemblyRepo({WORKFLOW_PATH: content})
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)

    _cmd_assembly_sync_workflow(None, pin_version="1.2.3",
                                pin_selfdoc="0.35.0",
                                pin_pagefind=PINNED_PAGEFIND)

    assert remote.commits == 1
    assert b"'selfdoc==0.35.0'" in remote.blobs[WORKFLOW_PATH]


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


# -- the pins themselves ------------------------------------------------------


def test_pins_refuse_to_be_empty():
    for kwargs in (
        {"selfblog": "", "selfdoc": "1.0", "pagefind": "1.0"},
        {"selfblog": "1.0", "selfdoc": "", "pagefind": "1.0"},
        {"selfblog": "1.0", "selfdoc": "1.0", "pagefind": ""},
    ):
        with pytest.raises(ValueError):
            ToolchainPins(**kwargs)


def test_the_generator_renders_every_pin():
    yaml_str = generate_workflow_yaml(
        PAGES_PROJECT, CANONICAL_BASE, "", "", PINS,
    )
    assert "'selfblog==1.2.3'" in yaml_str
    assert f"'selfdoc=={PINNED_SELFDOC}'" in yaml_str
    assert f"'pagefind[bin]=={PINNED_PAGEFIND}'" in yaml_str


def test_check_pins_are_published_accepts_published_versions():
    from selfblog.assembly import check_pins_are_published

    check_pins_are_published(PINS, fetch=StubPyPI())


def test_check_pins_are_published_names_the_registry_and_version():
    from selfblog.assembly import check_pins_are_published

    pins = ToolchainPins(selfblog="9.9.9", selfdoc=PINNED_SELFDOC,
                         pagefind=PINNED_PAGEFIND)
    with pytest.raises(RuntimeError) as excinfo:
        check_pins_are_published(pins, fetch=StubPyPI())
    message = str(excinfo.value)
    assert "9.9.9" in message
    assert "pypi.org" in message


def test_a_release_with_no_files_counts_as_unpublished():
    """A version whose artifacts were removed cannot be pip-installed."""
    from selfblog.assembly import check_pins_are_published

    def empty_release(package):
        return {"info": {"version": "1.2.3"}, "releases": {"1.2.3": []}}

    pins = ToolchainPins(selfblog="1.2.3", selfdoc="1.2.3", pagefind="1.2.3")
    with pytest.raises(RuntimeError, match="1.2.3"):
        check_pins_are_published(pins, fetch=empty_release)


def test_registry_latest_version_reads_the_current_release():
    from selfblog.assembly import registry_latest_version

    assert registry_latest_version("pagefind", fetch=StubPyPI()) == PINNED_PAGEFIND


def test_registry_latest_version_refuses_metadata_with_no_version():
    from selfblog.assembly import registry_latest_version

    with pytest.raises(RuntimeError):
        registry_latest_version("pagefind", fetch=lambda package: {"info": {}})


def test_resolve_pins_takes_explicit_values_verbatim():
    from selfblog.assembly import resolve_toolchain_pins

    stub = StubPyPI()
    pins = resolve_toolchain_pins(
        selfblog_version="1.2.3", selfdoc_version="0.35.0",
        pagefind_version="1.3.0", fetch=stub,
    )
    assert pins == ToolchainPins(selfblog="1.2.3", selfdoc="0.35.0",
                                 pagefind="1.3.0")
    assert stub.asked == [], "explicit pins ask the registry nothing"


def test_resolve_pins_reads_the_running_selfblog_and_installed_selfdoc():
    from importlib.metadata import version as dist_version

    from selfblog import __version__
    from selfblog.assembly import resolve_toolchain_pins

    pins = resolve_toolchain_pins(fetch=StubPyPI())
    assert pins.selfblog == __version__
    assert pins.selfdoc == dist_version("selfdoc")


def test_resolve_pins_asks_the_registry_only_for_pagefind():
    from selfblog.assembly import resolve_toolchain_pins

    stub = StubPyPI()
    pins = resolve_toolchain_pins(fetch=stub)
    assert stub.asked == ["pagefind"]
    assert pins.pagefind == PINNED_PAGEFIND


def test_the_real_probe_targets_pypis_json_api():
    """The default probe is the one the smoke path would use.

    The suite's isolation floor denies sockets, so this asserts the URL the
    probe builds rather than performing the request; a live probe is what
    `assembly sync-workflow` itself does on every release.
    """
    from selfblog.assembly import PYPI_JSON_URL

    assert PYPI_JSON_URL.format(package="selfblog") == (
        "https://pypi.org/pypi/selfblog/json"
    )


def test_the_real_probe_actually_dials_pypi():
    """The unmocked probe reaches for pypi.org, and the floor stops it there.

    This is as close to a live smoke test as this suite goes: sockets are
    denied, so the assertion is that the default probe genuinely tries the
    registry (a forgotten mock fails loudly rather than passing on stale
    data). The floor's refusal is not an ``Exception`` subclass, on
    purpose, so it cannot be swallowed by ordinary error handling.
    """
    from selfblog.assembly import fetch_pypi_metadata

    with pytest.raises(BaseException) as excinfo:
        fetch_pypi_metadata("selfblog")
    assert "pypi.org" in str(excinfo.value)


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
