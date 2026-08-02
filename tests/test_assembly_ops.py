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
        elif "describe" in cmd_str:
            result.stdout = "v1.0.0\n"
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
