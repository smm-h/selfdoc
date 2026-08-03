# Stray duplicate `.strictcli/schema.json` tracked at the monorepo root

Filed 2026-08-03.

## Problem

Three schema files are tracked (`git ls-files`):

- `.strictcli/schema.json` (repo root)
- `selfblog/.strictcli/schema.json`
- `selfdoc/.strictcli/schema.json`

The two package-level files are the real ones (one per app). The root file is a stray duplicate of the selfdoc app's schema, produced by a `--dump-schema` run from the wrong working directory (the dump writes to CWD). It shadows nothing but pollutes discovery: tooling that walks for schema files finds a third app that does not exist, and release-time regeneration never updates it, so it drifts silently stale.

## Work

1. Confirm the root file's `name`/`project_id` matches one of the package apps (i.e. it is a duplicate, not a third app).
2. Remove the tracked root file (deletion via the sanctioned deletion tool; also drop it from git) and verify nothing references the root path — the docs pipeline reads the package-level files.
3. Optional hardening: a check that the repo tracks exactly one schema per app directory.

## Affected files

`.strictcli/schema.json` (root — removed), possibly a check script.

## Effort

S.
