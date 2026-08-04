"""Auto-commit helper for selfdoc commands.

Commits project-directory files after writes. Guarded against loops
via the SELFDOC_AUTO_COMMIT environment variable.
"""

import os
import shutil
import subprocess
import sys

from selfdoc_core import effects


def auto_commit(files: list[str], message: str, cwd: str) -> bool:
    """Commit *files* in the git repo at *cwd* with *message*.

    Returns True if a commit was made, False otherwise. Silent on
    success; logs to stderr only on unexpected errors.  Under a command's
    ``--dry-run`` the commit is RECORDED rather than performed, and the
    return value is the ``Unsettled`` carrier standing in for it.

    Guards:
    - Returns False if SELFDOC_AUTO_COMMIT is set (prevents loops).
    - Returns False if *cwd* is not inside a git repo.
    - Filters out files that have no changes (tracked and unchanged,
      or not untracked). Handles deletions of tracked files.
    """
    # Guard against re-entrant calls (e.g. git hook triggers selfdoc)
    if os.environ.get("SELFDOC_AUTO_COMMIT"):
        return False

    # Check if cwd is inside a git repo
    try:
        result = effects.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=cwd,
            capture_output=True,
            timeout=10,
            read=True,
        )
        if result.returncode != 0:
            return False
    except (OSError, subprocess.TimeoutExpired):
        return False

    # Check for actual changes: tracked files with diffs, deletions,
    # or untracked (new) files
    committable = []
    untracked_new = []
    for f in files:
        path = f if os.path.isabs(f) else os.path.join(cwd, f)

        # Check if the file is tracked
        try:
            ls_result = effects.run(
                ["git", "ls-files", "--", f],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=10,
                read=True,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue

        if ls_result.returncode == 0 and ls_result.stdout.strip():
            # File is tracked -- commit regardless of gitignore
            if not os.path.exists(path):
                # Tracked but deleted from disk -- stage the deletion
                committable.append(f)
            else:
                # Tracked and exists -- check if it has changes
                try:
                    diff_result = effects.run(
                        ["git", "diff", "--quiet", "--", f],
                        cwd=cwd,
                        capture_output=True,
                        timeout=10,
                        read=True,
                    )
                    if diff_result.returncode != 0:
                        # Has changes
                        committable.append(f)
                except (OSError, subprocess.TimeoutExpired):
                    continue
        else:
            # File is untracked -- collect for gitignore filtering
            if os.path.exists(path):
                untracked_new.append(f)

    # Filter gitignored files from untracked candidates only
    if untracked_new:
        try:
            ci_result = effects.run(
                ["git", "check-ignore", "--stdin"],
                cwd=cwd,
                text=True,
                input="\n".join(untracked_new),
                capture_output=True,
                timeout=10,
                read=True,
            )
            if ci_result.returncode == 0:
                # Some files are ignored -- remove them
                ignored = set(ci_result.stdout.strip().splitlines())
                untracked_new = [f for f in untracked_new if f not in ignored]
            # returncode 1 means none are ignored -- keep all
            # returncode 128+ means error -- keep all (skip filtering)
        except (OSError, subprocess.TimeoutExpired):
            pass  # On error, keep all untracked candidates
        committable.extend(untracked_new)

    if not committable:
        return False

    # Build subprocess environment with loop guard
    env = os.environ.copy()
    env["SELFDOC_AUTO_COMMIT"] = "1"

    # Try rlsbl first, then safegit, fall back to plain git.
    #
    # No confirmation flag is passed.  Both tools are strictcli apps, and
    # strictcli prompts only for commands that declare themselves
    # ``consequential``; neither ``rlsbl commit`` nor ``safegit commit`` does,
    # because a commit is ordinary, undoable work.  Passing
    # ``--approve-consequential`` here would be accepted (it is framework-global)
    # but would state a decision nobody asked for, so the bare argv is correct.
    if shutil.which("rlsbl"):
        cmd = ["rlsbl", "commit", "-m", message, "--"] + committable
        label = "rlsbl"
    elif shutil.which("safegit"):
        cmd = ["safegit", "commit", "-m", message, "--"] + committable
        label = "safegit"
    else:
        return _plain_git_commit(committable, message, cwd, env)

    try:
        result = effects.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            resource=f"commit:{cwd}",
        )
        if effects.unsettled(result):
            # Recorded, not performed: nothing ran, so there is no exit
            # status to test.  The carrier is the honest answer.
            return result
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr, end="")
            return False
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"selfdoc: auto-commit failed ({label}): {exc}",
            file=sys.stderr,
        )
        return False


def _plain_git_commit(committable, message, cwd, env):
    """Commit through plain git when neither rlsbl nor safegit is installed."""
    try:
        add_result = effects.run(
            ["git", "add", "--"] + committable,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        commit_argv = ["git", "commit", "-m", message, "--"] + committable
        if effects.unsettled(add_result):
            # Recorded: the commit that would follow is recorded too, so the
            # preview stays complete without reading a status that does not
            # exist.
            return effects.run(
                commit_argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
                resource=f"commit:{cwd}",
            )
        if add_result.returncode != 0:
            print(add_result.stderr, file=sys.stderr, end="")
            return False
        commit_result = effects.run(
            commit_argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            resource=f"commit:{cwd}",
        )
        if commit_result.returncode != 0:
            print(commit_result.stderr, file=sys.stderr, end="")
            return False
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"selfdoc: auto-commit failed (git): {exc}",
            file=sys.stderr,
        )
        return False
