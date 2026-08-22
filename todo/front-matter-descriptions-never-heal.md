# Seeded front-matter descriptions never heal after code changes

## Context

`selfdoc gen` preserves an existing generated file's front-matter
`description` on every regeneration; only the body is rebuilt. Seeded
descriptions carry `seeded: true`.

## Problem

A description falsified by a later code change never heals. Regeneration
updates the body but keeps the stale description forever, so a published
doc page can indefinitely claim a mechanism the code removed.

Observed live: a package rewrote its core mechanism and updated its
in-code package doc accordingly; every subsequent `selfdoc gen` kept the
old front-matter description asserting the removed mechanism, on a
chmod-444 generated file. The workaround was to delete the file to force
re-seeding (which then hit the seeding-source defect — see the sibling
todo `front-matter-description-seeding-source.md`), or to hand-edit the
front matter and drop `seeded: true`.

The `seeded: true` marker makes this fixable cleanly: a seeded
description is machine-owned by declaration, so preserving it against its
own source is the part that makes no sense. Hand-authored descriptions
(no marker) are a different case and preserving those is correct.

## Solutions

1. **Re-seed on every gen whenever `seeded: true` is present** — treat
   the marker as "machine-owned, keep fresh". Authored descriptions
   without the marker stay preserved. Recommended: zero new surface,
   makes the marker mean something.
2. A `--reseed-descriptions` flag forcing re-seed for marked entries.
   Weaker: an opt-in heal is a heal nobody runs.
3. Warn when a seeded description differs from the current package-doc
   first sentence. Weakest: warn-and-continue.

## Affected

The regeneration path's front-matter merge logic.

## Effort

Small to medium — the merge decision plus a regression test: seed, change
the package doc, regen, assert the description followed.
