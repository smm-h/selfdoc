# auto_commit includes gitignored files, causing silent commit failure

## Problem

`selfdoc gen` fails to auto-commit its generated documentation when the project has `.selfdoc/` in `.gitignore`. The commit is silently swallowed with no error output.

## Root cause

Three bugs in the auto-commit pipeline:

### Bug 1: gitignored files included in commit list

`auto_commit()` in `selfdoc/git.py` treats any untracked-but-existing file as committable. It uses `git ls-files` to check if a file is tracked, and if not, checks `os.path.exists()`. But it never checks `.gitignore`. When `.selfdoc/hashes/hashes.json` and `.selfdoc/manifest.json` are gitignored (which is correct — they're generated caches), they get added to the commit file list anyway. The commit tool (`safegit commit` or `rlsbl commit`) then hard-errors on the gitignored files, aborting the entire commit — including the legitimate doc files.

### Bug 2: silent error swallowing

`auto_commit()` uses `capture_output=True` when calling the commit tool but never prints `result.stderr` on failure. The hard error from the commit tool is silently discarded.

### Bug 3: unchecked return value

`_cmd_gen()` in `selfdoc/cli.py` calls `auto_commit()` but ignores its return value. If auto-commit fails, the command exits 0 with no error indication. The user sees "Generated 35 doc file(s)" and assumes everything worked.

## Reproduction

In any project where `.selfdoc/` is in `.gitignore` and the commit tool is `safegit` (which rejects gitignored files):

```
selfdoc gen
git status  # docs/ files remain uncommitted
```

## Fix

### Bug 1

In `auto_commit()`, filter out gitignored files before adding them to `committable`. Use `git check-ignore -q <path>` per file, or use `git ls-files --others --exclude-standard` to correctly identify truly untracked (non-ignored) files.

### Bug 2

When `result.returncode != 0`, print `result.stderr` to stderr so commit failures are visible.

### Bug 3

Check `auto_commit()`'s return value in `_cmd_gen()`. If it returns False, either warn (non-fatal) or exit non-zero (fatal). At minimum, print a message: "auto-commit failed — generated files are uncommitted."

## Affected files

- `selfdoc/git.py` — `auto_commit()` function
- `selfdoc/cli.py` — `_cmd_gen()` around line 912-916
