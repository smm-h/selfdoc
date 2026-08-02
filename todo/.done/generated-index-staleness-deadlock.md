# Generated index pages can deadlock on STALE001

## Problem

Fully-generated index pages (produced by `gen`'s index generator) carry a
**hardcoded constant `description`** baked into the generator. Their body is a
derived listing (e.g. the set of generated module/command pages). The staleness
system then makes these pages unable to ever clear STALE001 once their content
legitimately changes:

1. `compute_content_hash` strips frontmatter and hashes the resolved body.
2. `check_staleness` raises STALE001 when the content hash changes but the
   `description` hash does not.
3. `update_hashes` deliberately does **not** advance the stored baseline for any
   page currently in an error state.

So whenever the generated set changes (a page added, removed, or renamed), the
index body — and thus its content hash — changes, but the description is a fixed
constant and never changes, so STALE001 fires and stays sticky:

- The baseline won't auto-advance because the page is in an error state.
- Manually editing the description doesn't stick — the file is regenerated
  (chmod 444) and the next `gen` overwrites the description back to the constant.

This is a catch-22: a class of pages (fully-generated index pages whose
`description` is a generator constant) can enter an unrecoverable STALE001 state
on any content change.

## Observed workaround (hacky, not a fix)

Because `compute_content_hash` strips frontmatter, one can set a temporarily
distinct description, run `check` (baseline advances since the description hash
differs), then run `gen` to restore the canonical constant description (body/
content hash unchanged, so it stays green). This is fragile and non-obvious.

## Suggested fixes (pick one)

- Exempt fully-generated index pages from STALE001 (they are 100% generator-owned;
  a human has no description to review).
- Derive the index page's description from its (changing) content so the
  description hash tracks the content hash.
- Advance the staleness baseline for pages whose content is entirely
  generator-owned, even when they currently show STALE001.

## Relevant symbols

- `staleness.compute_content_hash` (strips frontmatter before hashing)
- the index-content generator (hardcodes the description constant)
- `staleness.update_hashes` (skips baseline advance for error pages)
- `staleness.check_staleness` (raises STALE001 on content-vs-description mismatch)

## Related enhancement requests (lower priority, same area)

- There is no generic data-driven `table` directive that renders rows from a
  declared data source; bespoke tables require a custom directive that calls the
  internal markdown-table renderer.
- `gen-data` output (written under the data dir) is not consumed by any directive
  and is not run or gated by `gen`/`check`, so the gen-data -> render pipeline is
  half-built and its outputs can silently go stale.

## Effort estimate

Small-to-medium for the STALE001 fix (staleness module + the index generator);
the enhancement requests are independent and larger.
