"""Tests for selfdoc.git auto-commit helper."""

import os
import subprocess
from unittest import mock

import pytest

from selfdoc.git import auto_commit


def _init_git_repo(path):
    """Initialize a git repo at *path* with an initial commit."""
    subprocess.run(
        ["git", "init"], cwd=str(path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=str(path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=str(path),
        capture_output=True, timeout=10,
    )
    # Create an initial commit so HEAD exists
    readme = path / "README"
    readme.write_text("init")
    subprocess.run(
        ["git", "add", "README"], cwd=str(path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=str(path),
        capture_output=True, timeout=10,
    )


def test_auto_commit_in_git_repo(tmp_path):
    """auto_commit commits a changed file in a git repo."""
    _init_git_repo(tmp_path)

    # Write a new file
    (tmp_path / "hello.txt").write_text("hello")

    result = auto_commit(["hello.txt"], "add hello", str(tmp_path))
    assert result is True

    # Verify the file was committed
    log = subprocess.run(
        ["git", "log", "--oneline", "--", "hello.txt"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert "add hello" in log.stdout


def test_auto_commit_not_git_repo(tmp_path):
    """auto_commit returns False when not in a git repo."""
    (tmp_path / "file.txt").write_text("data")

    result = auto_commit(["file.txt"], "msg", str(tmp_path))
    assert result is False


def test_auto_commit_no_changes(tmp_path):
    """auto_commit returns False when a tracked file has no changes."""
    _init_git_repo(tmp_path)

    # README is already committed with no changes
    result = auto_commit(["README"], "no change", str(tmp_path))
    assert result is False


def test_auto_commit_gitignored_file(tmp_path):
    """auto_commit skips gitignored files and returns False."""
    _init_git_repo(tmp_path)

    (tmp_path / ".gitignore").write_text("ignored.txt\n")
    subprocess.run(
        ["git", "add", ".gitignore"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "add gitignore"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )

    (tmp_path / "ignored.txt").write_text("should be ignored")

    result = auto_commit(["ignored.txt"], "msg", str(tmp_path))
    assert result is False


def test_auto_commit_loop_guard(tmp_path, monkeypatch):
    """auto_commit returns False when SELFDOC_AUTO_COMMIT is set."""
    _init_git_repo(tmp_path)
    (tmp_path / "file.txt").write_text("data")

    monkeypatch.setenv("SELFDOC_AUTO_COMMIT", "1")
    result = auto_commit(["file.txt"], "msg", str(tmp_path))
    assert result is False


def test_auto_commit_uses_rlsbl_when_available(tmp_path):
    """auto_commit calls rlsbl commit when it is on PATH."""
    _init_git_repo(tmp_path)
    (tmp_path / "file.txt").write_text("data")

    with mock.patch("shutil.which", return_value="/usr/bin/rlsbl"):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.Mock(returncode=0),      # git rev-parse --git-dir
                mock.Mock(returncode=1),       # git check-ignore (not ignored)
                mock.Mock(returncode=0, stdout=""),  # git ls-files (untracked)
                mock.Mock(returncode=0),       # rlsbl commit
            ]

            result = auto_commit(["file.txt"], "msg", str(tmp_path))

        # Verify rlsbl was called
        last_call = mock_run.call_args_list[-1]
        assert last_call[0][0][0] == "rlsbl"
        assert last_call[0][0][1] == "commit"
        assert result is True


def test_auto_commit_uses_safegit_when_available(tmp_path):
    """auto_commit calls safegit when rlsbl is not available."""
    _init_git_repo(tmp_path)
    (tmp_path / "file.txt").write_text("data")

    def which_side_effect(cmd):
        if cmd == "rlsbl":
            return None
        if cmd == "safegit":
            return "/usr/bin/safegit"
        return None

    with mock.patch("shutil.which", side_effect=which_side_effect):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.Mock(returncode=0),      # git rev-parse --git-dir
                mock.Mock(returncode=1),       # git check-ignore (not ignored)
                mock.Mock(returncode=0, stdout=""),  # git ls-files (untracked)
                mock.Mock(returncode=0),       # safegit commit
            ]

            result = auto_commit(["file.txt"], "msg", str(tmp_path))

        # Verify safegit was called (not rlsbl)
        last_call = mock_run.call_args_list[-1]
        assert last_call[0][0][0] == "safegit"
        assert last_call[0][0][1] == "commit"
        assert result is True


def test_auto_commit_falls_back_to_git(tmp_path):
    """auto_commit uses plain git when neither rlsbl nor safegit is available."""
    _init_git_repo(tmp_path)
    (tmp_path / "file.txt").write_text("data")

    with mock.patch("shutil.which", return_value=None):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.Mock(returncode=0),      # git rev-parse --git-dir
                mock.Mock(returncode=1),       # git check-ignore (not ignored)
                mock.Mock(returncode=0, stdout=""),  # git ls-files (untracked)
                mock.Mock(returncode=0),       # git add
                mock.Mock(returncode=0),       # git commit
            ]

            result = auto_commit(["file.txt"], "msg", str(tmp_path))

        # Verify git add and git commit were called (not rlsbl or safegit)
        add_call = mock_run.call_args_list[-2]
        assert add_call[0][0][0] == "git"
        assert add_call[0][0][1] == "add"
        commit_call = mock_run.call_args_list[-1]
        assert commit_call[0][0][0] == "git"
        assert commit_call[0][0][1] == "commit"
        assert result is True


def test_auto_commit_multiple_files(tmp_path):
    """auto_commit commits multiple files at once."""
    _init_git_repo(tmp_path)

    (tmp_path / "a.txt").write_text("aaa")
    (tmp_path / "b.txt").write_text("bbb")

    result = auto_commit(["a.txt", "b.txt"], "add both", str(tmp_path))
    assert result is True

    # Verify both files are in the commit
    log = subprocess.run(
        ["git", "log", "--oneline", "--name-only", "-1"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert "a.txt" in log.stdout
    assert "b.txt" in log.stdout


def test_auto_commit_untracked_file(tmp_path):
    """auto_commit commits a new untracked file."""
    _init_git_repo(tmp_path)

    (tmp_path / "newfile.txt").write_text("new content")

    result = auto_commit(["newfile.txt"], "add new", str(tmp_path))
    assert result is True

    # Verify the file is now tracked
    ls = subprocess.run(
        ["git", "ls-files", "newfile.txt"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert "newfile.txt" in ls.stdout
