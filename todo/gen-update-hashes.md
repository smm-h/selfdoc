# selfdoc gen should update content hashes after generating docs

## Problem

selfdoc gen regenerates doc pages but does NOT update `.selfdoc/hashes/hashes.json`. When selfdoc check runs afterward, it finds content changed (from gen) but hashes are stale, reports STALE001, updates the hashes, and exits with error. Running check a second time passes because hashes are now settled.

This creates a "run twice to fix" ritual in every release pipeline that uses selfdoc.

## Root cause

`update_hashes()` is only called by `check_docs()` (in check.py). The `_cmd_gen` function in cli.py does not call it.

## Fix

In `selfdoc/cli.py` `_cmd_gen`, after generating docs, call `update_hashes()` to bring the hash store in sync with freshly-generated content. Discard the return value (gen is not a checking operation). Include `.selfdoc/hashes/hashes.json` in the auto-commit file list.

## Effort

Small. One function call + one file added to commit list.
