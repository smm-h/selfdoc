# Spec-driven directive descriptors (collapse catalog + dispatch + validation + docs)

## Context

Directive knowledge is currently spread across parallel structures that must be kept in
sync by hand:

- `selfdoc_core/catalog.py` DirectiveSpec (description, category, required/optional attrs,
  example) — now enforced at check/gen time (attribute enforcement shipped), with a
  hand-verified expected-attrs map in tests to catch drift.
- The dispatch if-chain / registry in `resolve_content` (which resolver runs for which
  name).
- Per-resolver attribute reads (`attrs.get(...)`) — the actual source of truth the catalog
  mirrors.
- Docs pages listing directives (table-directives et al.).

The attribute-enforcement work made the catalog load-bearing, but the sync between catalog,
dispatch, and resolver reality is still maintained by convention plus a curated test.

## Proposal

One descriptor object per directive that *feeds everything*: name, attribute schema
(names, required-ness, value validation), resolver callable, category, example, docs blurb.
Registration derives the dispatch table; enforcement derives allowed/required attrs;
`table-directives`/docs derive their rows; the catalog file disappears as a separate
artifact (or becomes the descriptor collection itself).

## Notes

- Overlaps the deferred `todo/.defer/directive-name-first-class-type.md` (DirectiveName as
  a validated type) — a combined design pass should consider both.
- The custom-directive registration path (`config["directives"]`, register_directive)
  should produce the same descriptor shape so custom directives get attribute enforcement
  too (today they are skipped by enforcement because they have no catalog spec).
- Two follow-ups from the enforcement work belong in this design: build-time enforcement
  (today only check/gen enforce; a bare `selfdoc build` resolves unknown attrs silently)
  and schema-discovery caching for table-commands (discovery currently walks per
  resolution).

## Effort

Medium-large: a selfdoc_core restructure of directive registration; mechanical per
directive once the descriptor shape exists.
