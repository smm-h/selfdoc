# Staleness/drift deadlock on auto-generated (skeleton) CLI pages

## Summary

Auto-generated CLI reference pages (`generated: true` + `seeded: true`, written chmod 444
with a "do not edit" header) are subject to the STALE001/STALE and DRIFT001 checks, but
their frontmatter `description` is auto-derived from the command's summary and cannot be
hand-edited. When a consuming project changes its CLI schema in a way that alters a page's
CONTENT or its per-command SCHEMA slice WITHOUT changing the command's one-line description
(e.g. lengthening flag/arg help text), `selfdoc check` reports STALE001 + DRIFT001 as
**errors** (exit 1) and — by design — refuses to advance the baseline until the description
is rewritten. For a skeleton page there is no valid way to rewrite the description, so the
error is a permanent deadlock. The only escape is to delete/reset the `.selfdoc/` hash cache
by hand.

This blocks `selfdoc check` (and therefore any rlsbl release that runs it) for a strictcli
project the first time it edits flag help after being baselined with a selfdoc version that
tracks `schema_hash`.

## Reproduction

1. A strictcli-based project with `.strictcli/schema.json` and selfdoc `root_files`/CLI
   pages. Run `selfdoc gen` — it produces `docs/cli-<command>.md` with frontmatter
   `generated: true`, `seeded: true`, a description auto-derived from the command summary,
   chmod 444.
2. `selfdoc check` (baseline is written to `.selfdoc/hashes/hashes.json`, including a
   `schema_hash` for the CLI page).
3. Change only FLAG/ARG help text in the CLI (not the command's description). Regenerate:
   `<app> --dump-schema` then `selfdoc gen`. The CLI page's content and `schema_hash`
   change; the command-level `description` does not.
4. `selfdoc check` → exit 1 with:
   - `error: [STALE001] cli-<command>.md - content changed but frontmatter description was not updated`
   - `error: [DRIFT001] cli-<command>.md - CLI schema changed but page description was not updated`
5. Re-running `selfdoc check` does NOT clear it: the baseline is intentionally held for a
   page with errors, and the description can never change (auto-derived, 444). Deadlock.

Workaround a consumer is currently forced into: delete `.selfdoc/hashes/hashes.json` (or the
page's entry) so `check` re-establishes a fresh baseline. There is no clean "acknowledge /
re-baseline" command.

## Root cause

- `selfdoc_core/staleness.py` `update_hashes()` (lines ~190-286): computes current content,
  description, source-docstring, and CLI `schema_hash` per page and compares against the
  stored baseline. STALE fires when content changed but description didn't
  (`check_staleness`); DRIFT fires when the source docstring or the CLI `schema_hash`
  changed but the description didn't (`check_drift` / `check_schema_drift`).
- Lines ~275-282 deliberately HOLD the baseline for any page with a staleness/drift error
  ("Pages with staleness or drift errors keep their old baseline so the error persists until
  the description is actually rewritten. ... per-page-all-fields atomic hold."). For a
  hand-written page this is correct. For a skeleton page it is unresolvable.
- `selfdoc/check.py` (~lines 495-521) appends STALE001 and DRIFT001 with `severity="error"`,
  so they fail the command / release.
- `_is_skeleton_page(frontmatter)` (`selfdoc/check.py` ~line 1473) already distinguishes
  auto-generated, auto-described pages (`generated: true` AND `seeded: true`), but it is used
  ONLY for coverage accounting (documented vs. referenced), NOT for the staleness/drift
  gate. So skeleton pages are still subject to a check they can never satisfy.
- `selfdoc gen` regenerates the page but does NOT advance the hash baseline (only
  `build`/`check` write `.selfdoc/hashes/hashes.json`), so gen cannot un-stick it either.

Note: projects baselined by an OLDER selfdoc (whose `hashes.json` has no `schema_hash` for
the CLI page) do not hit DRIFT001 for schema changes, because `check_schema_drift` with a
missing stored `schema_hash` treats it as first-seen (no drift). So this only bites once a
project is baselined with a `schema_hash`-tracking selfdoc and then edits its CLI.

## Proposed fixes

1. **Exempt skeleton pages (`generated: true` + `seeded: true`) from STALE001/DRIFT001**
   (recommended). Such pages are regenerated wholesale by `selfdoc gen`, so "drift between
   content and description" is impossible by construction — the description auto-tracks the
   command summary and nothing else. Reuse `_is_skeleton_page` to skip them in the
   staleness/drift path (either filter in `check.py` before appending the lints, or pass a
   skeleton predicate into `update_hashes` and continue past those pages while still
   advancing their baseline).
   - Pro: eliminates the false positive at the source; no consumer action needed.
   - Con: a skeleton page whose description is genuinely wrong won't be flagged — but that
     description is machine-generated from the command summary, so "wrong" means the command
     summary is wrong, which is a source-level concern, not a staleness concern.

2. **Have skeleton pages always advance their baseline** (a softer variant of #1): in
   `update_hashes`, exclude skeleton pages from the "hold baseline on error" set (lines
   ~278-282) so their hashes advance every run; still skip emitting the error for them.

3. **Add a re-baseline / acknowledge affordance** so intentional changes can be accepted
   without hand-deleting the cache — e.g. `selfdoc gen` advances the baseline for the pages
   it (re)generates, or a `selfdoc check --accept`/`selfdoc rebaseline` command. Useful
   independently of #1 for hand-written pages too.

#1 (or #1+#3) is the cleanest: it targets exactly the pages that cannot satisfy the gate,
while leaving the guard fully active for hand-written pages.

## Affected files

- `selfdoc_core/staleness.py` — `update_hashes()` baseline-hold logic (~lines 275-286) and
  the STALE/DRIFT computation (~lines 214-273).
- `selfdoc/check.py` — where STALE001/DRIFT001 lints are appended (~lines 495-521); reuse
  `_is_skeleton_page` (~line 1473) for the exemption.
- If adding a re-baseline command: `selfdoc/gen.py` and/or the check/CLI entry points.

## Tests

`tests/test_check.py` already has DRIFT001 tests (~lines 4200-4270). Add a red-green case:
a project with an auto-generated CLI page (`generated: true` + `seeded: true`) whose command
SCHEMA slice changes (e.g. a flag's help text) while the command description stays the same
must NOT emit STALE001/DRIFT001 after `gen`, and the baseline must advance. Include a
companion assertion that a HAND-WRITTEN page with the same content/description mismatch STILL
emits the lint (so the exemption is scoped to skeleton pages only).

## Effort

Small–medium. The exemption itself is a few lines (reuse `_is_skeleton_page`); the care is in
also advancing the baseline for exempted pages so the cache stays consistent, plus the
red-green tests. Roughly a few hours including tests.
