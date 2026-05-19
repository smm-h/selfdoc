# STALE001 release friction: catch stale descriptions before release starts

## Context

Projects using both rlsbl and selfdoc (e.g., rlsbl itself) hit a recurring friction pattern during releases. When code changes affect a module's public API or content, `selfdoc check` flags STALE001 (content changed but description wasn't updated). This is correct behavior. The problem is WHEN it's caught -- `selfdoc check` runs as part of rlsbl's built-in lint step, which happens mid-release. The release aborts, the user fixes the description, adds a changelog entry for the fix, and retries. This happened twice in a single session (v0.35.1 and v0.36.0 both required mid-release description fixes).

## Problem

The fix-and-retry loop adds 2-3 commits per release that are purely reactive. It would be better to catch stale descriptions BEFORE starting the release, so they can be fixed as part of normal pre-release preparation.

## Options

### (a) selfdoc check in rlsbl pre-checks hook

Users add `selfdoc check` to `.rlsbl/hooks/pre-checks.sh`. This runs before the release begins, failing early. Requires manual setup per project. No selfdoc code change needed.

### (b) rlsbl auto-detects selfdoc and runs check earlier

rlsbl already runs `selfdoc check` as built-in lint. Move it from the lint phase to the pre-checks phase so it fails before any mutation. This is an rlsbl change, not selfdoc.

### (c) selfdoc provides a lightweight "are descriptions stale?" query

A fast read-only check that rlsbl (or git hooks) can run cheaply. Currently `selfdoc check` does directives + coverage + lints -- the staleness check could be split out as a faster targeted command.

## Recommendation

Option (a) is the quickest -- it's just a hook configuration, no code change. Option (b) is the structural fix in rlsbl. Option (c) makes selfdoc more composable long-term.

## Effort

- **(a)** Zero code change
- **(b)** Small rlsbl change
- **(c)** Medium selfdoc change
