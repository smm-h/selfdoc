# Semantic content hashing for staleness (directive identity by resolved target)

Successor to `todo/.done/stale001-no-ack-path-for-mechanical-content-changes.md` — that
file's ack-path need is served by the shipped `selfdoc baseline accept` command; this
successor carries its untaken option 1. Filed deliberately as part of the 2026-08
staleness-closure work.

## Problem

STALE001's content hash is computed over the raw template body, so purely mechanical
respellings still register as content change: renaming a path in a directive attribute,
re-flowing a directive's attributes, or otherwise rewording a line whose RESOLVED output
is identical all trip the staleness check even though nothing a reader sees changed. The
current remedy is `baseline accept` — honest, but manual toil for changes the tool could
prove are semantically inert.

## Proposal

Key directive identity by resolved target rather than path spelling: hash the directive's
resolved referent (the symbol/file it extracts from, its category, its attributes after
normalization) instead of its literal source text, so that respellings resolving to the
same target are hash-stable while changes that alter WHAT is being documented still move
the hash.

## Central design care point: under-hashing

The whole risk of this design is masking genuine staleness. Every normalization applied
before hashing widens the class of changes the check can no longer see. Each proposed
normalization must be argued individually with a worked example of (a) a mechanical change
it correctly ignores and (b) the nearest genuine change it must still catch. When in
doubt, hash more, not less.

## Baseline migration

Changing the hash inputs invalidates every stored baseline. Ship with a `_hash_version`
bump and a one-shot migration (the v2→v3 bump is the precedent), never with dual-reading
of old baselines.

## Effort

Medium — the hashing change itself is small; the work is the per-normalization argument,
tests for both sides of each normalization, and the baseline migration.
