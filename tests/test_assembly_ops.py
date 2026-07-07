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
from selfdoc.cli import app


def _setup_project(tmp_path, config_overrides=None):
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0", "indexed": True}],
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
        _cmd_assembly_init()


def test_push_no_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_push()


def test_status_no_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_status()


def test_rebuild_no_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_rebuild()


# -- Config present but no assembly.repo -------------------------------------


def test_init_no_assembly_repo(tmp_path, monkeypatch):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_init()


def test_push_no_assembly_repo(tmp_path, monkeypatch):
    # No assembly.repo AND no topology.assembly -> exits
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_push()


def test_status_no_assembly_repo(tmp_path, monkeypatch):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_status()


def test_rebuild_no_assembly_repo(tmp_path, monkeypatch):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        _cmd_assembly_rebuild()


# -- Push uses topology.assembly fallback ------------------------------------


def test_push_uses_topology_assembly_fallback(tmp_path, monkeypatch):
    _setup_project(tmp_path, {
        "topology": {"assembly": "owner/assembly", "slug": "myproject"},
    })
    monkeypatch.chdir(tmp_path)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "repo" in cmd_str and "view" in cmd_str:
            result.stdout = "owner/source-repo\n"
        elif "describe" in cmd_str:
            result.stdout = "v1.0.0\n"
        elif "dispatches" in cmd_str:
            pass
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_assembly_push()
    assert len(calls) >= 3


# -- Status with no runs ----------------------------------------------------


def test_status_no_runs(tmp_path, monkeypatch, capsys):
    _setup_project(tmp_path, {"assembly": {"repo": "owner/docs-assembly"}})
    monkeypatch.chdir(tmp_path)

    def fake_run(cmd, **kwargs):
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_assembly_status()
    captured = capsys.readouterr()
    assert "No recent assembly builds found." in captured.out


# -- Rebuild with empty projects.json ---------------------------------------


def test_rebuild_empty_projects(tmp_path, monkeypatch, capsys):
    _setup_project(tmp_path, {"assembly": {"repo": "owner/docs-assembly"}})
    monkeypatch.chdir(tmp_path)

    empty_b64 = base64.b64encode(b"{}").decode()

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "contents/projects.json" in cmd_str:
            result.stdout = empty_b64 + "\n"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_assembly_rebuild()
    captured = capsys.readouterr()
    assert "No projects configured" in captured.out


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
