# Audit the strictspec adoption (external session hand-off)

An external session converted the built-in directive catalogue from a Python
dict literal into a strictspec-governed declarative document (strictspec
0.1.0 is now a selfdoc-core dependency). Committed but NOT released — rides
along with the next release. This todo exists so the work can be audited
first.

## What changed and why

Why: the DirectiveSpec catalogue was a hand-maintained dict whose shape
nothing validated, with a dispatch table that could silently drift from it;
this repo's own todos were already converging on a spec-driven descriptor
design — the migration realizes that via the fleet's validation authority.

- `selfdoc_core/directives.toml` — the 20 core descriptors, single source of
  truth — governed by `selfdoc_core/.strictspec/directive-descriptor.schema.toml`
  (name grammar `^[a-zA-Z][\w-]*$` as a regex refinement, category enum,
  unique-by name, `format_version = 1`) + generated validator (committed 444).
- `selfdoc_core/catalog.py` is now a thin loader: validates the document at
  import and raises `CatalogDocumentError` on any diagnostic; the 123-line
  `CORE_DIRECTIVES` dict literal was deleted. Public API, enforcement
  behavior, and the custom-directive skip are byte-identical (existing
  enforcement tests kept unchanged as the oracle).
- New dispatch-freshness tests: content-dispatch keys must equal the
  document's content-category directives.
- Collateral fix: `scripts/gen-directive-stats.py` had been silently emitting
  ZERO core directives since the monorepo split (it AST-parsed a file that
  became a re-export shim); rewritten to read directives.toml; stats
  regenerated (core 20, future 60).
- Suite: 2945 passed. Docs builds verified against sibling repos with no
  directive errors (one repo's pre-existing content-staleness failures are
  unrelated).
- Changelog entries are non-user-facing by deliberate judgment: no consumer
  behavior changed; verify you agree before the next release.

## Audit points and open calls

1. The three pre-existing convergence todos were deliberately LEFT ACTIVE:
   `spec-driven-directive-descriptors.md` is partially resolved (dispatch
   collapse realized as a freshness test; custom-directive descriptor
   unification and build-time enforcement not done) — owner call whether to
   split or keep; the other two are untouched in scope.
2. Generated docs prose still claims "one runtime dependency" — now stale
   (selfdoc-core transitively pulls strictspec); refresh the prose.
