# Generated gen-index.md description hardcodes "selfdoc" instead of the documented project

## Context

`selfdoc gen` produces an API-reference index page (`docs/gen-index.md`) for the project
being documented. Generated pages carry frontmatter (`title`, `description`,
`generated: true`) and participate in the SEO/staleness checks like any other page.

## Problem

The description written into every consumer's `gen-index.md` is hardcoded to name
**selfdoc itself** — `selfdoc/gen.py` (~line 372) emits a description along the lines of
"API reference for the selfdoc package" regardless of which project is being documented.
Every consumer project's generated API index therefore describes itself as selfdoc's.

Two concrete consequences observed in a real consumer project:

1. **Wrong metadata everywhere**: the page's SEO description (and anything downstream
   that consumes the manifest) misidentifies the project.
2. **Unresolvable STALE001**: when the consumer's module list changed (modules
   added/excluded), `selfdoc check` flagged `STALE001` on gen-index.md — "content changed
   but frontmatter description was not updated". But the description is machine-written
   and wrong-by-construction; there is no hand-edit that sticks (gen rewrites it), so the
   only resolution was manually re-baselining that page's entry in
   `.selfdoc/hashes/hashes.json`. This is a concrete instance of the broader
   generated-page staleness deadlock described in
   `todo/skeleton-cli-page-staleness-deadlock.md` (do not edit that file; this one adds
   the gen-index-specific defect: the description is not just un-editable, it is
   *incorrect*).

## Proposed solutions

1. **Derive the description from project config (recommended).** Use the documented
   project's name/description (manifest name, `selfdoc.json` `description`, or the same
   source `var key="project.name"` resolves from) — e.g. "API reference for {project
   name}: auto-generated module index." Falls back to a generic "API reference module
   index" when no name is resolvable — generic beats wrong.
   - Pros: correct metadata for every consumer; removes one guaranteed STALE001 trigger
     class; trivial.
   - Cons: none meaningful; regeneration will churn every consumer's gen-index.md once
     (auto-committed, changelog-exempt).
2. **Exempt gen-index.md from STALE001 only.**
   - Pros: stops the deadlock symptom.
   - Cons: the description stays wrong; treats the symptom, not the defect. (The
     exemption question for generated pages generally is already covered by the
     skeleton-staleness todo.)

## Affected files

- `selfdoc/gen.py` (~line 372) / the corresponding `selfdoc_core` implementation — the
  gen-index frontmatter emitter.
- Tests: assert the generated description contains the documented project's name (and the
  fallback path when unnamed); a regression test that gen-index.md for a non-selfdoc
  project does not contain the string "selfdoc".

## Effort

Tiny. One emitter change + two tests; well under an hour.
