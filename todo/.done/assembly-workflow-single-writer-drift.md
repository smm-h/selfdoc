# The assembly repo's deploy workflow has a single writer and drifts silently

## Context

`assembly init` is the ONLY writer of the assembly repo's generated
`deploy.yml`. Template changes in `selfblog/assembly.py` therefore never reach
an existing assembly repo — the deployed copy strands at whatever the template
said when init last ran.

## Problem (observed live, 2026-08-07)

selfblog 0.3.0 made `--portfolio-canonical` a required flag of
`generate-shared`. The assembly repo's deployed workflow still invoked the
command without it. The post-release rebuild only passed because it started
~19 seconds BEFORE 0.3.0 landed on PyPI (the workflow installs selfblog
unpinned); the very next dispatch from any project would have hard-failed the
unified docs deploy fleet-wide. The fix was a hand-regeneration and manual
push of the workflow — exactly the drift class the generated-files convention
exists to prevent, except here nothing regenerates.

## Solutions

- (a) `assembly sync-workflow` command: regenerate `deploy.yml` from the
  current template + config and push it to the assembly repo via the existing
  Git-Trees push helper; the release flow's assembly-push hook (or the
  release itself) invokes it so template and deployed copy cannot diverge
  across a release. Pros: closes the class; reuses existing machinery.
  Cons: every release touches the assembly repo (cheap — one API commit when
  changed, no-op otherwise; content-compare before write).
- (b) Version-pin selfblog in the generated workflow and bump the pin on
  sync. Narrows the blast radius (a stale workflow keeps working against the
  old selfblog) but preserves the drift; combined with (a) it makes the
  transition atomic — pin and workflow move together.
- (c) Do nothing; document that `assembly init` must be re-run against the
  existing repo after template changes. Weakest; init also creates resources
  and is not obviously idempotent against a live repo.

(a), with (b)'s pin folded in, is the most correct: the workflow becomes a
regenerate-only artifact like every other generated file in the fleet.

## Affected

- `selfblog/assembly.py` (template + a sync entry point), `selfblog/cli.py`
  (command registration), the assembly-push hook wiring, the live assembly
  repo's `deploy.yml`.

## Effort

Small-medium: the generator and push helper both exist; the work is the
command, the content-compare, the pin, and tests.
