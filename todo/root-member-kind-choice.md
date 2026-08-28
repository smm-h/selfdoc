# Choose the workspace root member's kind: dev node, or member of the selfdoc releasable

## Context

The fleet migration to rlsbl's root-member workspace model (rlsbl >= 0.118)
migrated this workspace with a dev-node root member, by the mechanical rule
"a root with no project manifest becomes a dev node" — the root
`pyproject.toml` here is a virtual uv-workspace shim with no `[project]`
section. That was a mechanical default, not a considered choice for this
repository, and the maintainers should decide deliberately.

What the root member owns either way: everything no subdirectory member
claims — `docs/**`, `scripts/**`, the root `tests/`, `selfdoc.json`,
`LICENSE`, the root `pyproject.toml` and `uv.lock`. Under the old model the
selfdoc member's watch globs pulled those paths into its changelog scope;
watch is gone, so ownership decides scope now.

Also relevant: the repository's bare `v<semver>` tags belong to the selfdoc
member's release line, not to the root.

## Option A — keep the dev-node root (current state)

- Pro: the root genuinely ships nothing; docs, scripts and workspace
  plumbing are development infrastructure, and a dev node requires no
  changelog for them — commits touching only root-owned paths need no
  changelog entry.
- Pro: no change needed; checks pass as migrated.
- Con: changes to `docs/**` and the root `tests/` no longer count toward
  the selfdoc releasable's changelog, even when they are user-visible
  documentation work that previously rode selfdoc releases. A
  documentation overhaul would ship in a selfdoc release with no changelog
  trace unless entries are written against member-owned files.

## Option B — the root member joins the selfdoc releasable

- Pro: closest to the old behavior — root-level docs/scripts/tests changes
  count toward the selfdoc releasable's changelog coverage again, so
  releases document the documentation work they carry.
- Pro: one-line edit — set `releasable = "selfdoc"` on the root member in
  `.rlsbl-monorepo/workspace.toml` (and drop `dev_only`), then re-run
  `rlsbl check --tag workspace`.
- Con: every commit touching root-owned paths then requires a changelog
  entry (or a non-user-facing one), including pure plumbing edits to
  `uv.lock` or `selfdoc.json`.
- Con: a root-owning releasable must declare its `tag_format` explicitly;
  the selfdoc line uses bare `v{version}` tags, so the declaration would be
  `tag_format = "v{version}"` on the selfdoc releasable.

## Effort

Minutes either way; the judgment is the work.
