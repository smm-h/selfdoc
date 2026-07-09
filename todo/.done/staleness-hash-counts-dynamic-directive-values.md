# STALE001 staleness hash includes resolved dynamic directive values (version bumps re-stale pages every release)

## Context

A consumer project's docs index page renders the project version via a `var` directive
(`:-: var key="project.version"`). Its release pipeline runs `selfdoc gen` + `selfdoc check`
as a release gate.

## Problem

The STALE001 staleness detector computes its content hash on the *resolved* page content —
including values substituted by directives. A page that renders `project.version` therefore
changes content on every version bump, which re-stales its human-owned frontmatter
description on every release. Because the "atomic hold" only releases when the description
text is actually rewritten, the maintainer must hand-tweak the description each release even
though nothing meaningful changed — the resolved version string is the only delta.

Observed consequence: a release pipeline was blocked twice in a row by STALE001 on the same
page; the second occurrence was caused purely by the previous release's own version bump.
A per-release manual description edit is not a sustainable workaround, and it trains
maintainers to make meaningless description edits — eroding the check's value.

## Potential solutions

- **Hash the raw (pre-resolution) page body** for staleness purposes instead of the resolved
  content. Directive-substituted values then never trip STALE001; genuine content edits still
  do. Pros: fixes the whole class; staleness tracks what humans wrote. Cons: content that
  changes only via directive resolution (e.g. an included snippet edited elsewhere) would no
  longer flag the including page — arguably correct, since the description describes the
  page's own prose, but worth a deliberate call.
- **Exclude specific directive types from the hash** (e.g. `var` substitutions) while keeping
  includes/refs hashed. More surgical; more special cases.
- **Per-page or per-directive opt-out** (frontmatter flag like `stale_ignore_dynamic: true`
  or a directive modifier). Most flexible, but pushes the burden onto every affected page and
  invites blanket opt-outs that defeat the check.

## Affected areas

- The staleness/content-hash computation used by STALE001 (and likely DRIFT001's baseline
  logic, which shares the hash model).
- Hash baseline storage (hashes.json) and the atomic-hold release condition.
- Docs for the staleness check semantics.

## Effort estimate

Small-medium: the hash-input change itself is small; the care is in baseline migration
(existing hashes.json values were computed on resolved content, so the first run after the
change must re-baseline without mass-flagging every page) plus a regression test for the
version-bump scenario.
