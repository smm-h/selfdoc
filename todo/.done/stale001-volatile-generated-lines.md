# STALE001 false-positives on generated pages with volatile lines

## Context

A consumer project's release pipeline regenerates its docs on every
release. One generated page (a CLI index) embeds a "Version: X.Y.Z" line,
so every release changes the page's content by exactly that line. STALE001
("content changed but frontmatter description was not updated") fires on
every single release, and the release operator must run
`selfdoc baseline accept <page>` each time even though the description is
still perfectly accurate.

## Problem

STALE001's premise — content change implies the description may be stale —
is wrong for mechanical, expected volatility (version stamps, dates,
counts) in GENERATED pages. Generated pages can't acknowledge the change
by editing their description (they're read-only), so the only remedy is a
manual per-release baseline accept: recurring toil with zero signal.

## Solutions

- (a) Volatility-aware hashing: exclude declared-volatile patterns (or
  frontmatter-declared `volatile:` line patterns) from the STALE001
  content hash, so version-line-only changes never trip it. Pros: kills
  the false-positive class at the root. Cons: pattern configuration
  surface.
- (b) Generated-page exemption with a stronger regeneration check:
  STALE001 skips `generated: true` pages entirely (their content is
  derivational; staleness is the generator's concern, already covered by
  the freshness check). Pros: simplest; arguably the correct semantics.
  Cons: loses STALE001 on generated pages whose auto-descriptions could
  genuinely rot.
- (c) Auto-accept on `selfdoc gen`: a bare gen that regenerates a page
  also advances its baseline (the tool made the change; it can vouch for
  it). Pros: no config. Cons: silently accepts every generated change,
  weakening the check's intent.

## Effort

Small-medium depending on the option; (b) is the smallest.
