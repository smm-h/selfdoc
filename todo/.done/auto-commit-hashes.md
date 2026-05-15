# Auto-commit content hashes after build

## Problem

`selfdoc build` updates `.selfdoc/hashes/hashes.json` with content and description hashes for every generated page. This file should be tracked in git (it enables incremental builds and staleness detection), but every build that changes page content leaves it as a dirty file. Downstream projects (e.g., rlsbl) that run `selfdoc build` in post-release hooks must manually commit the updated hashes.

## Proposal

Add a `--commit` flag to `selfdoc build` and `selfdoc check` that auto-commits `.selfdoc/hashes/hashes.json` after the build if its content changed.

### Behavior

- Compare file content before and after `save_hashes()`. Skip if unchanged.
- Use `git add .selfdoc/hashes/hashes.json && git commit -m "selfdoc: update content hashes"`.
- Skip silently when: not a git repo, file is gitignored, file unchanged, index has conflicts.
- Guard against pre-commit hook loops: set an env var (e.g., `SELFDOC_AUTO_COMMIT=1`) before committing, check it at the start of build to skip the commit path if already inside one.

### Implementation

- Add a helper in `staleness.py` or a new `git.py`: `commit_hashes_if_changed(dir_path)`.
- Use `git diff --quiet .selfdoc/hashes/hashes.json` to detect changes.
- Use `git check-ignore -q .selfdoc/hashes/hashes.json` to skip if gitignored.
- Call at the end of `_cmd_build()` (after lint checks) and `_cmd_check()` unless `--no-commit` is set.
- Existing git patterns in `build.py` (branch detection) and `deploy.py` (force-push) provide templates.

### Config alternative

Instead of (or in addition to) `--commit`, support `"auto_commit_hashes": true` in `selfdoc.json` so projects can opt in permanently without flags. Default: false.

### Does not apply to `gen`

`selfdoc gen` creates markdown source files and does not touch hashes. Auto-commit for `gen` output is a separate concern.

## Affected files

- `selfdoc/cli.py` — add `--commit` flag to `build` and `check` commands
- `selfdoc/staleness.py` — add commit helper, or create `selfdoc/git.py`

## Effort

Small. ~40-60 lines of new code plus tests. No architectural changes.
