"""Auto-commit helper for selfdoc commands.

Commits project-directory files after writes. Guarded against loops
via the SELFDOC_AUTO_COMMIT environment variable.
"""

import os
import shutil
import subprocess
import sys


def auto_commit(files: list[str], message: str, cwd: str) -> bool:
    """Commit *files* in the git repo at *cwd* with *message*.

    Returns True if a commit was made, False otherwise. Silent on
    success; logs to stderr only on unexpected errors.

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
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=cwd,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False
    except (OSError, subprocess.TimeoutExpired):
        return False

    # Check for actual changes: tracked files with diffs, deletions,
    # or untracked (new) files
    committable = []
    for f in files:
        path = f if os.path.isabs(f) else os.path.join(cwd, f)

        # Check if the file is tracked
        try:
            ls_result = subprocess.run(
                ["git", "ls-files", "--", f],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue

        if ls_result.returncode == 0 and ls_result.stdout.strip():
            # File is tracked
            if not os.path.exists(path):
                # Tracked but deleted from disk -- stage the deletion
                committable.append(f)
            else:
                # Tracked and exists -- check if it has changes
                try:
                    diff_result = subprocess.run(
                        ["git", "diff", "--quiet", "--", f],
                        cwd=cwd,
                        capture_output=True,
                        timeout=10,
                    )
                    if diff_result.returncode != 0:
                        # Has changes
                        committable.append(f)
                except (OSError, subprocess.TimeoutExpired):
                    continue
        else:
            # File is untracked -- it's new and should be committed
            if os.path.exists(path):
                committable.append(f)

    if not committable:
        return False

    # Build subprocess environment with loop guard
    env = os.environ.copy()
    env["SELFDOC_AUTO_COMMIT"] = "1"

    # Try rlsbl first, then safegit, fall back to plain git
    if shutil.which("rlsbl"):
        cmd = ["rlsbl", "commit", "-m", message, "--"] + committable
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                env=env,
                timeout=30,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(
                f"selfdoc: auto-commit failed (rlsbl): {exc}",
                file=sys.stderr,
            )
            return False
    elif shutil.which("safegit"):
        cmd = ["safegit", "commit", "-m", message, "--"] + committable
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                env=env,
                timeout=30,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(
                f"selfdoc: auto-commit failed (safegit): {exc}",
                file=sys.stderr,
            )
            return False
    else:
        # Fallback: git add + git commit
        try:
            add_result = subprocess.run(
                ["git", "add", "--"] + committable,
                cwd=cwd,
                capture_output=True,
                env=env,
                timeout=30,
            )
            if add_result.returncode != 0:
                return False
            commit_result = subprocess.run(
                ["git", "commit", "-m", message, "--"] + committable,
                cwd=cwd,
                capture_output=True,
                env=env,
                timeout=30,
            )
            return commit_result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(
                f"selfdoc: auto-commit failed (git): {exc}",
                file=sys.stderr,
            )
            return False
