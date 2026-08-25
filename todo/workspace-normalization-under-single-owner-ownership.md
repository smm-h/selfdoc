# Workspace normalization under rlsbl's single-owner ownership model

## Background

rlsbl is adopting a new workspace ownership model: every file has exactly one
owning member (most specific member path wins; a mandatory root member owns
the remainder), the `watch` key is removed, and CI triggering is derived
instead of hand-globbed — a member's jobs run on its own territory, on
changes to members it declares `depends_on` edges to (all dependency scopes
trigger), plus built-in rules: a workspace-root manifest/lockfile change
triggers every member, release-machinery commits are auto-appended to
filters, and a CI-router change re-runs everything.

This workspace currently uses `watch` for exactly the things the new model
replaces: all members watch the root `pyproject.toml`/`uv.lock` (covered by
the built-in manifest rule), and one member additionally claims root
`docs/`, `scripts/`, `tests/`, `selfdoc.json`, and `LICENSE`.

## What to consider doing

- Remove the shared-manifest watch entries once the built-in rule ships;
  they become redundant.
- Register the shared root `tests/` directory as a dev-node member with
  `depends_on` on all three packages, so a test-only change still re-runs
  every package's CI. Without this, under residual ownership a tests-only
  change would trigger nobody.
- Add the root member the new model requires (dev node — there is no root
  project).
- Move the docs content into the member's territory. The zero-tool-change
  form is setting the `docs` config key to a member-relative path
  (`selfdoc/docs/`), which also fixes GitHub edit links; the fuller form is
  member-scoped `selfdoc.json` once the assembly transport supports
  subdirectories (see the separate todo about that). Either way, update the
  post-release hook if the config file moves.

## Why

Under single-owner attribution, root files claimed only via watch globs lose
their owner. Docs changes are user-facing and must keep changelog coverage —
moving the content into the member's directory preserves that structurally
instead of via a hand-maintained glob list.
