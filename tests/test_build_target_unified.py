"""Tests for selfblog build --target unified."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from conftest import default_config
from selfblog.cli import _cmd_build


def _setup_project(tmp_path):
    """Write a minimal valid selfdoc.json."""
    config = default_config(docs="docs/", output="docs/_build/")
    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)
    os.makedirs(os.path.join(tmp_path, "docs"), exist_ok=True)
    os.makedirs(os.path.join(tmp_path, "src"), exist_ok=True)
    with open(os.path.join(tmp_path, "src", "__init__.py"), "w") as f:
        f.write('"""pkg."""\n')


def test_build_target_unified_calls_build_unified(tmp_path, monkeypatch):
    """selfblog build --target unified calls build_unified."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with patch("selfblog.unified.build_unified", return_value={"a.html": True}) as mock_fn:
        _cmd_build(None, target="unified", drafts=False, auto_commit=False)
        mock_fn.assert_called_once_with(
            dir_path=".", include_drafts=False, theme="",
        )


def test_build_target_posts_still_works(tmp_path, monkeypatch):
    """selfblog build --target posts still calls the posts build path."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with patch("selfdoc_core.build.build", return_value={}) as mock_build:
        _cmd_build(None, target="posts", drafts=False, auto_commit=False)
        mock_build.assert_called_once_with(
            ".", include_drafts=False, target="posts", theme="",
        )


def test_build_target_invalid_exits_with_error(tmp_path, monkeypatch):
    """selfblog build --target invalid exits with sys.exit(1)."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        _cmd_build(None, target="invalid", drafts=False, auto_commit=False)
    assert exc_info.value.code == 1


def test_build_target_invalid_prints_error_message(tmp_path, monkeypatch, capsys):
    """selfblog build --target invalid prints the valid targets in the error."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _cmd_build(None, target="invalid", drafts=False, auto_commit=False)

    captured = capsys.readouterr()
    assert "unknown build target 'invalid'" in captured.err
    assert "posts" in captured.err
    assert "unified" in captured.err


def test_build_target_unified_passes_include_drafts(tmp_path, monkeypatch):
    """selfblog build --target unified --drafts passes include_drafts=True."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with patch("selfblog.unified.build_unified", return_value={}) as mock_fn:
        _cmd_build(None, target="unified", drafts=True, auto_commit=False)
        mock_fn.assert_called_once_with(
            dir_path=".", include_drafts=True, theme="",
        )


def test_build_target_unified_runtime_error(tmp_path, monkeypatch, capsys):
    """selfblog build --target unified exits 1 on RuntimeError."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with patch("selfblog.unified.build_unified", side_effect=RuntimeError("broken")):
        with pytest.raises(SystemExit) as exc_info:
            _cmd_build(None, target="unified", drafts=False, auto_commit=False)
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "broken" in captured.err
