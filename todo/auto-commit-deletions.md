# auto_commit doesn't handle deletions

## Problem

When `_remove_stale_generated` deletes files from disk, `auto_commit` doesn't commit those deletions because it filters paths with `os.path.exists()`. Stale generated files remain tracked in git even after a corrective re-run of `selfdoc gen`.

## Affected code

`_remove_stale_generated` deletes files but doesn't communicate the list of deleted paths to `auto_commit`. The commit function only stages files that exist on disk.

## Fix

Track deletions in `_remove_stale_generated` (return the list of deleted paths). Pass them to `auto_commit` and use `git rm` or equivalent to stage the deletions before committing.
