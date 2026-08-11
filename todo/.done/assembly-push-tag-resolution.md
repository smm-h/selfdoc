# assembly push resolves the newest tag by date, ignoring the target prefix

## Problem

In a multi-target monorepo, `selfblog assembly push` picks the repo's newest tag by
creatordate. Observed live (2026-08-09): a repo whose Python releasable is the docs target
dispatched its Go releasable's tag instead — the assembly built version 0.0.0 content and
the unified site served a 404 stub. Related gap: nothing validates that selfdoc.json's
`versions` array tracks the released version (one consumer's lists only a version 24 minors
old, so even a correct tag builds ancient docs).

## Solutions

Resolve the tag through the releasable/topology mapping (prefix-aware), hard-error on
ambiguity; add a check that versions[] contains the current project version (VER004 family).

## Effort

Small-medium.
