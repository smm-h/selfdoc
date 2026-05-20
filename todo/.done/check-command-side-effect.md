# selfdoc check side-effect naming

## Context

`selfdoc check` writes to `.selfdoc/hashes/hashes.json` as a side effect. Both `check` and `build` update stored content and description hashes. This is intentional -- it enables the edit-check-edit workflow: fix a description, re-run check, it passes because check updated the stored hashes on the first run. Without this, users would need to run `build` between every check iteration.

## Problem

The name "check" implies a read-only operation. Users and AI agents are surprised when it writes files. This was investigated and the side effect was confirmed as intentional UX, not a bug.

## Options

- **(a) Keep `check`, add `--dry-run` flag for read-only mode.** Simplest approach. The familiar name stays, and users who need read-only behavior get an explicit opt-in. `--dry-run` is a well-understood convention.
- **(b) Rename to `sync` or `verify`.** Communicates that state changes happen, but may confuse existing users and break existing scripts/workflows.
- **(c) Split into `lint` (read-only) + `check` (writes).** Cleanest semantics, but doubles command surface area and splits a single workflow into two commands.
- **(d) Just document the behavior.** Cheapest option -- no code change, just add a note to help output and docs explaining that `check` updates hashes.

## Recommendation

Option (a) -- add `--dry-run` to `check`. Document that default behavior writes hashes. This preserves the current edit-check-edit workflow while giving users and automation a read-only escape hatch.

## Effort

Small.
