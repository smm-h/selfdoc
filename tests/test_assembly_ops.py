"""Tests for assembly CLI operations (_cmd_assembly_init/push/status/rebuild)."""

import base64
import json
import os
import subprocess

import pytest

from selfblog.cli import (
    _cmd_assembly_init,
    _cmd_assembly_push,
    _cmd_assembly_rebuild,
    _cmd_assembly_status,
)
from selfblog.cli import app


def _setup_project(tmp_path, config_overrides=None):
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }
    if config_overrides:
        config.update(config_overrides)
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text("")
    return tmp_path


# -- No config (no selfdoc.json) ---------------------------------------------


def test_init_no_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_init(None)


def test_push_no_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_push(None)


def test_status_no_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_status(None)


def test_rebuild_no_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_rebuild(None)


# -- Config present but no assembly.repo -------------------------------------


def test_init_no_assembly_repo(tmp_path, monkeypatch):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_init(None)


def test_push_no_assembly_repo(tmp_path, monkeypatch):
    # No assembly.repo -> exits
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_push(None)


def test_status_no_assembly_repo(tmp_path, monkeypatch):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_status(None)


def test_rebuild_no_assembly_repo(tmp_path, monkeypatch):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_rebuild(None)


# -- topology.assembly is rejected outright ----------------------------------


def test_topology_assembly_key_is_rejected(tmp_path, monkeypatch):
    """The retired dual key is a hard config error, not a silent fallback."""
    from selfdoc_core.config import ConfigError, load_config

    _setup_project(tmp_path, {
        "topology": {"assembly": "owner/assembly", "slug": "myproject"},
    })
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError) as excinfo:
        load_config(".")
    assert "topology.assembly" in str(excinfo.value)
    assert "assembly" in str(excinfo.value)


def test_push_reads_assembly_repo(tmp_path, monkeypatch):
    """assembly.repo is the one canonical home for the assembly repo."""
    _setup_project(tmp_path, {
        "assembly": {"repo": "owner/assembly", "pages_project": "site"},
        "topology": {"slug": "myproject", "docs_base": "https://docs.example.com"},
    })
    monkeypatch.chdir(tmp_path)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "repo" in cmd_str and "view" in cmd_str:
            result.stdout = "owner/source-repo\n"
        elif "for-each-ref" in cmd_str:
            result.stdout = "v1.0.0\nv0.9.0\n"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    _cmd_assembly_push(None)

    dispatches = [c for c in calls if any("dispatches" in str(x) for x in c)]
    assert dispatches
    assert any("/repos/owner/assembly/dispatches" in str(x)
               for x in dispatches[0])


def test_init_requires_pages_project(tmp_path, monkeypatch):
    """assembly init refuses to run without an explicit Pages project."""
    _setup_project(tmp_path, {
        "assembly": {"repo": "owner/assembly"},
        "topology": {"slug": "myproject", "docs_base": "https://docs.example.com"},
    })
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_init(None)


def test_init_requires_docs_base(tmp_path, monkeypatch):
    """assembly init refuses to run without a canonical docs base."""
    _setup_project(tmp_path, {
        "assembly": {"repo": "owner/assembly", "pages_project": "site"},
        "topology": {"slug": "myproject"},
    })
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_init(None)


# -- Help output -------------------------------------------------------------


def test_assembly_init_help():
    result = app.test(["assembly", "init", "--help"])
    assert result.exit_code == 0


def test_assembly_push_help():
    result = app.test(["assembly", "push", "--help"])
    assert result.exit_code == 0


def test_assembly_status_help():
    result = app.test(["assembly", "status", "--help"])
    assert result.exit_code == 0


def test_assembly_rebuild_help():
    result = app.test(["assembly", "rebuild", "--help"])
    assert result.exit_code == 0


# -- reading projects.json off the assembly ----------------------------------
#
# `assembly rebuild` decoded and parsed the membership record under
# `except (json.JSONDecodeError, Exception)`, whose first clause could never
# be reached: `Exception` already covers it, so the two-clause tuple only
# looked like it distinguished a malformed document from anything else. It
# reads through the same helper every other remote read uses now, and its
# own handler names the one thing it is left to catch.


def _rebuild_project(tmp_path, monkeypatch, repo="owner/assembly"):
    _setup_project(tmp_path, {"assembly": {"repo": repo}})
    monkeypatch.chdir(tmp_path)


def _contents_reply(payload, *, returncode=0, stderr=""):
    def run(cmd, **kwargs):
        joined = " ".join(str(c) for c in cmd)
        if "/contents/" in joined:
            return subprocess.CompletedProcess(
                args=list(cmd), returncode=returncode,
                stdout=payload, stderr=stderr,
            )
        return subprocess.CompletedProcess(args=list(cmd), returncode=0,
                                           stdout="", stderr="")
    return run


def _encoded(text):
    return base64.b64encode(text.encode()).decode()


def test_rebuild_reports_a_malformed_membership_record(tmp_path, monkeypatch,
                                                       capsys):
    _rebuild_project(tmp_path, monkeypatch)
    monkeypatch.setattr("selfblog.cli.effects.run",
                        _contents_reply(_encoded("{not json")))
    monkeypatch.setattr("selfblog.assembly.effects.run",
                        _contents_reply(_encoded("{not json")))
    with pytest.raises(SystemExit):
        _cmd_assembly_rebuild(None)
    assert "projects.json" in capsys.readouterr().err


def test_rebuild_reports_a_failed_read(tmp_path, monkeypatch, capsys):
    """A rate limit is not an assembly with no projects."""
    _rebuild_project(tmp_path, monkeypatch)
    reply = _contents_reply("", returncode=1,
                            stderr="gh: API rate limit exceeded (HTTP 403)")
    monkeypatch.setattr("selfblog.cli.effects.run", reply)
    monkeypatch.setattr("selfblog.assembly.effects.run", reply)
    with pytest.raises(SystemExit):
        _cmd_assembly_rebuild(None)
    err = capsys.readouterr().err
    assert "rate limit" in err
    assert "No projects configured" not in err


def test_rebuild_reports_an_absent_membership_record(tmp_path, monkeypatch,
                                                     capsys):
    _rebuild_project(tmp_path, monkeypatch)
    reply = _contents_reply("", returncode=1,
                            stderr="gh: Not Found (HTTP 404)")
    monkeypatch.setattr("selfblog.cli.effects.run", reply)
    monkeypatch.setattr("selfblog.assembly.effects.run", reply)
    with pytest.raises(SystemExit):
        _cmd_assembly_rebuild(None)
    assert "projects.json" in capsys.readouterr().err


def test_rebuild_dispatches_for_every_registered_project(tmp_path, monkeypatch,
                                                         capsys):
    _rebuild_project(tmp_path, monkeypatch)
    payload = _encoded(json.dumps({
        "alpha": {"repo": "owner/alpha", "ref": "v1.0.0", "version": "1.0.0"},
        "beta": {"repo": "owner/beta", "ref": "v2.0.0", "version": "2.0.0"},
    }))
    monkeypatch.setattr("selfblog.cli.effects.run", _contents_reply(payload))
    monkeypatch.setattr("selfblog.assembly.effects.run",
                        _contents_reply(payload))
    assert _cmd_assembly_rebuild(None) == 0
    out = capsys.readouterr().out
    assert "Dispatched 2 rebuild(s)." in out
