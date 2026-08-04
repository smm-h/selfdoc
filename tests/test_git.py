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
    """auto_commit lets git handle gitignored files (git add fails)."""
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

    # With no external tools, git add will fail on a gitignored file
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
                mock.Mock(returncode=0, stdout=""),  # git ls-files (untracked)
                mock.Mock(returncode=1, stdout="", stderr=""),  # git check-ignore (none ignored)
                mock.Mock(returncode=0, stdout="", stderr=""),  # rlsbl commit
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
                mock.Mock(returncode=0, stdout=""),  # git ls-files (untracked)
                mock.Mock(returncode=1, stdout="", stderr=""),  # git check-ignore (none ignored)
                mock.Mock(returncode=0, stdout="", stderr=""),  # safegit commit
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
                mock.Mock(returncode=0, stdout=""),  # git ls-files (untracked)
                mock.Mock(returncode=1, stdout="", stderr=""),  # git check-ignore (none ignored)
                mock.Mock(returncode=0, stdout="", stderr=""),  # git add
                mock.Mock(returncode=0, stdout="", stderr=""),  # git commit
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


def test_auto_commit_filename_resembling_git_flag(tmp_path):
    """auto_commit handles filenames that look like git options (-- separator)."""
    _init_git_repo(tmp_path)

    # Create a file whose name starts with "--" which git would
    # interpret as an option without the "--" separator
    tricky_name = "--hierarchical"
    (tmp_path / tricky_name).write_text("tricky content")

    result = auto_commit([tricky_name], "add tricky file", str(tmp_path))
    assert result is True

    # Verify the file was committed
    log = subprocess.run(
        ["git", "log", "--oneline", "--", tricky_name],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert "add tricky file" in log.stdout


def test_auto_commit_dash_separator_in_subprocess_calls(tmp_path):
    """Verify -- separator is present in all git subprocess calls."""
    _init_git_repo(tmp_path)
    (tmp_path / "file.txt").write_text("data")

    with mock.patch("shutil.which", return_value=None):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.Mock(returncode=0),           # git rev-parse --git-dir
                mock.Mock(returncode=0, stdout=""), # git ls-files (untracked)
                mock.Mock(returncode=1, stdout="", stderr=""),  # git check-ignore (none ignored)
                mock.Mock(returncode=0, stdout="", stderr=""),  # git add
                mock.Mock(returncode=0, stdout="", stderr=""),  # git commit
            ]

            auto_commit(["file.txt"], "msg", str(tmp_path))

        calls = mock_run.call_args_list

        # ls-files call (index 1) must have "--" before filename
        ls_files_cmd = calls[1][0][0]
        assert ls_files_cmd == ["git", "ls-files", "--", "file.txt"]

        # git add call (index 3) must have "--" before filenames
        add_cmd = calls[3][0][0]
        assert add_cmd == ["git", "add", "--", "file.txt"]

        # git commit call (index 4) must have "--" before filenames
        commit_cmd = calls[4][0][0]
        assert "--" in commit_cmd
        dash_idx = commit_cmd.index("--")
        assert commit_cmd[dash_idx + 1] == "file.txt"


def test_auto_commit_deleted_file(tmp_path):
    """auto_commit commits a deletion of a tracked file."""
    _init_git_repo(tmp_path)

    # Create and commit a file
    target = tmp_path / "to_delete.txt"
    target.write_text("will be deleted")
    subprocess.run(
        ["git", "add", "to_delete.txt"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "add file"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )

    # Delete the file from disk
    os.unlink(target)
    assert not target.exists()

    # auto_commit should detect and commit the deletion
    result = auto_commit(["to_delete.txt"], "delete file", str(tmp_path))
    assert result is True

    # Verify the file is no longer tracked
    ls = subprocess.run(
        ["git", "ls-files", "to_delete.txt"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert ls.stdout.strip() == ""


def test_auto_commit_mixed_operations(tmp_path):
    """auto_commit handles modify + delete + new file in one call."""
    _init_git_repo(tmp_path)

    # Create and commit two files
    (tmp_path / "file1.txt").write_text("original")
    (tmp_path / "file2.txt").write_text("to delete")
    subprocess.run(
        ["git", "add", "file1.txt", "file2.txt"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "add files"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )

    # Modify file1, delete file2, create file3 (new)
    (tmp_path / "file1.txt").write_text("modified")
    os.unlink(tmp_path / "file2.txt")
    (tmp_path / "file3.txt").write_text("brand new")

    result = auto_commit(
        ["file1.txt", "file2.txt", "file3.txt"],
        "mixed ops",
        str(tmp_path),
    )
    assert result is True

    # Verify file1 was modified in the commit
    show = subprocess.run(
        ["git", "show", "HEAD:file1.txt"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert show.stdout == "modified"

    # Verify file2 is no longer tracked
    ls = subprocess.run(
        ["git", "ls-files", "file2.txt"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert ls.stdout.strip() == ""

    # Verify file3 is now tracked
    ls3 = subprocess.run(
        ["git", "ls-files", "file3.txt"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert "file3.txt" in ls3.stdout


def test_auto_commit_deleted_file_rlsbl_path(tmp_path):
    """auto_commit passes deleted file to rlsbl commit."""
    _init_git_repo(tmp_path)

    # Create and commit a file, then delete it
    target = tmp_path / "gone.txt"
    target.write_text("will vanish")
    subprocess.run(
        ["git", "add", "gone.txt"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "add gone"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    os.unlink(target)

    with mock.patch("shutil.which", return_value="/usr/bin/rlsbl"):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.Mock(returncode=0),                      # git rev-parse
                mock.Mock(returncode=0, stdout="gone.txt\n"), # git ls-files
                mock.Mock(returncode=0),                      # rlsbl commit
            ]

            result = auto_commit(["gone.txt"], "rm gone", str(tmp_path))

        assert result is True
        last_call = mock_run.call_args_list[-1]
        cmd = last_call[0][0]
        assert cmd[0] == "rlsbl"
        assert cmd[1] == "commit"
        assert "gone.txt" in cmd


def test_auto_commit_deleted_file_safegit_path(tmp_path):
    """auto_commit passes deleted file to safegit commit."""
    _init_git_repo(tmp_path)

    # Create and commit a file, then delete it
    target = tmp_path / "gone.txt"
    target.write_text("will vanish")
    subprocess.run(
        ["git", "add", "gone.txt"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "add gone"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    os.unlink(target)

    def which_side_effect(cmd):
        if cmd == "rlsbl":
            return None
        if cmd == "safegit":
            return "/usr/bin/safegit"
        return None

    with mock.patch("shutil.which", side_effect=which_side_effect):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.Mock(returncode=0),                      # git rev-parse
                mock.Mock(returncode=0, stdout="gone.txt\n"), # git ls-files
                mock.Mock(returncode=0),                      # safegit commit
            ]

            result = auto_commit(["gone.txt"], "rm gone", str(tmp_path))

        assert result is True
        last_call = mock_run.call_args_list[-1]
        cmd = last_call[0][0]
        assert cmd[0] == "safegit"
        assert cmd[1] == "commit"
        assert "gone.txt" in cmd


def test_auto_commit_filters_gitignored_from_mixed_list(tmp_path):
    """auto_commit should commit legitimate files even when mixed with gitignored ones.

    When a file list contains both a normal untracked file and a gitignored
    file, auto_commit should filter out the gitignored file and still commit
    the legitimate one.  Currently it does not check .gitignore, so git add
    fails on the gitignored file and the entire commit is aborted.
    """
    _init_git_repo(tmp_path)

    # Set up .gitignore to ignore the .selfdoc/ directory
    (tmp_path / ".gitignore").write_text(".selfdoc/\n")
    subprocess.run(
        ["git", "add", ".gitignore"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "add gitignore"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )

    # Create a legitimate doc file and a gitignored file
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# Hello\n")
    (tmp_path / ".selfdoc").mkdir()
    (tmp_path / ".selfdoc" / "hashes.json").write_text("{}\n")

    # Force the git fallback path (no rlsbl, no safegit) for deterministic
    # behavior -- the real git subprocess will reject the gitignored file.
    with mock.patch("shutil.which", return_value=None):
        result = auto_commit(
            ["docs/index.md", ".selfdoc/hashes.json"],
            "test commit",
            str(tmp_path),
        )

    # The commit should succeed (the legitimate file should be committed)
    assert result is True

    # The legitimate file should appear in the commit
    log = subprocess.run(
        ["git", "log", "--oneline", "--name-only", "-1"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert "docs/index.md" in log.stdout

    # The gitignored file should NOT be in the commit
    assert ".selfdoc/hashes.json" not in log.stdout


def test_auto_commit_all_files_gitignored(tmp_path):
    """auto_commit returns False when all candidate files are gitignored."""
    _init_git_repo(tmp_path)

    (tmp_path / ".gitignore").write_text("*.log\ncache/\n")
    subprocess.run(
        ["git", "add", ".gitignore"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "add gitignore"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )

    # Create only gitignored files
    (tmp_path / "debug.log").write_text("log data")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "data.bin").write_text("cached")

    with mock.patch("shutil.which", return_value=None):
        result = auto_commit(
            ["debug.log", "cache/data.bin"],
            "should not commit",
            str(tmp_path),
        )

    assert result is False


def test_auto_commit_tracked_file_matching_gitignore_still_committed(tmp_path):
    """A tracked file matching a gitignore pattern should still be committed.

    Gitignore only affects untracked files. If a file is already tracked,
    it must be committed even if its path matches a gitignore pattern.
    """
    _init_git_repo(tmp_path)

    # Create and commit a file
    (tmp_path / "config.log").write_text("original")
    subprocess.run(
        ["git", "add", "config.log"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "add config.log"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )

    # Now add a gitignore that matches the tracked file
    (tmp_path / ".gitignore").write_text("*.log\n")
    subprocess.run(
        ["git", "add", ".gitignore"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "add gitignore"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )

    # Modify the tracked file (it matches gitignore but is tracked)
    (tmp_path / "config.log").write_text("modified")

    with mock.patch("shutil.which", return_value=None):
        result = auto_commit(
            ["config.log"],
            "update tracked file",
            str(tmp_path),
        )

    assert result is True

    log = subprocess.run(
        ["git", "log", "--oneline", "--name-only", "-1"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert "config.log" in log.stdout


def test_auto_commit_git_check_ignore_none_ignored(tmp_path):
    """When git check-ignore returns exit code 1 (none ignored), all files pass."""
    _init_git_repo(tmp_path)

    # No gitignore -- all files should pass through
    (tmp_path / "a.txt").write_text("aaa")
    (tmp_path / "b.txt").write_text("bbb")

    with mock.patch("shutil.which", return_value=None):
        result = auto_commit(
            ["a.txt", "b.txt"],
            "add both",
            str(tmp_path),
        )

    assert result is True

    log = subprocess.run(
        ["git", "log", "--oneline", "--name-only", "-1"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert "a.txt" in log.stdout
    assert "b.txt" in log.stdout


def test_auto_commit_stderr_visible_on_failure(tmp_path, capsys):
    """When the commit tool fails, stderr output is printed."""
    _init_git_repo(tmp_path)
    (tmp_path / "file.txt").write_text("data")

    with mock.patch("shutil.which", return_value=None):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.Mock(returncode=0),       # git rev-parse --git-dir
                mock.Mock(returncode=0, stdout=""),  # git ls-files (untracked)
                mock.Mock(returncode=1, stdout="", stderr=""),  # git check-ignore (none ignored)
                mock.Mock(returncode=0, stdout="", stderr=""),  # git add
                mock.Mock(
                    returncode=1,
                    stdout="",
                    stderr="error: pathspec 'file.txt' did not match\n",
                ),  # git commit fails
            ]

            result = auto_commit(["file.txt"], "msg", str(tmp_path))

    assert result is False
    captured = capsys.readouterr()
    assert "error: pathspec" in captured.err


def test_auto_commit_mixed_files_rlsbl_path(tmp_path):
    """With rlsbl, gitignored files are filtered before the commit tool is called."""
    _init_git_repo(tmp_path)

    # Set up gitignore
    (tmp_path / ".gitignore").write_text("*.cache\n")
    subprocess.run(
        ["git", "add", ".gitignore"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )
    subprocess.run(
        ["git", "commit", "-m", "add gitignore"], cwd=str(tmp_path),
        capture_output=True, timeout=10,
    )

    # Create both legitimate and gitignored files
    (tmp_path / "doc.md").write_text("# Doc")
    (tmp_path / "build.cache").write_text("cached")

    with mock.patch("shutil.which", return_value="/usr/bin/rlsbl"):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock.Mock(returncode=0),       # git rev-parse --git-dir
                mock.Mock(returncode=0, stdout=""),  # git ls-files doc.md
                mock.Mock(returncode=0, stdout=""),  # git ls-files build.cache
                # git check-ignore: build.cache is ignored
                mock.Mock(returncode=0, stdout="build.cache\n", stderr=""),
                mock.Mock(returncode=0, stdout="", stderr=""),  # rlsbl commit
            ]

            result = auto_commit(
                ["doc.md", "build.cache"],
                "test commit",
                str(tmp_path),
            )

        assert result is True

        # Verify rlsbl was called with only doc.md, not build.cache
        rlsbl_call = mock_run.call_args_list[-1]
        cmd = rlsbl_call[0][0]
        assert cmd[0] == "rlsbl"
        assert "doc.md" in cmd
        assert "build.cache" not in cmd


def test_commit_tool_invocation_passes_yes(tmp_path, monkeypatch):
    """The internal commit-tool invocation carries ``--yes``.

    Both `rlsbl commit` and `safegit commit` are mutating strictcli commands,
    and strictcli's confirm protocol hard-errors ("stdin is not interactive;
    pass --yes to confirm") when stdin is not a TTY -- which is every context
    selfdoc auto-commits from: CI, a release pipeline, an agent session. Without
    the flag, `selfdoc gen`'s documented default of auto-committing its output
    silently cannot complete. This asserts the flag on the argv rather than only
    the outcome, so the fix cannot regress on a machine where the tool happens
    to be absent and the plain-git fallback runs instead.
    """
    _init_git_repo(tmp_path)
    (tmp_path / "hello.txt").write_text("hello")

    seen = []

    def fake_which(name):
        return "/usr/bin/rlsbl" if name == "rlsbl" else None

    def fake_run(argv, **kwargs):
        seen.append(list(argv))
        if kwargs.get("read"):
            return subprocess.run(
                list(argv),
                cwd=kwargs.get("cwd"),
                capture_output=kwargs.get("capture_output", False),
                text=kwargs.get("text", False),
                input=kwargs.get("input"),
                timeout=kwargs.get("timeout"),
            )
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("selfdoc_core.git.shutil.which", fake_which)
    monkeypatch.setattr("selfdoc_core.git.effects.run", fake_run)

    assert auto_commit(["hello.txt"], "add hello", str(tmp_path)) is True

    commit_argv = [a for a in seen if a[:2] == ["rlsbl", "commit"]]
    assert len(commit_argv) == 1, seen
    assert "--yes" in commit_argv[0]
