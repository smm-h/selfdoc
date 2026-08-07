# Go `ref` directive cannot target unexported symbols

## Problem

`:-: ref path="internal/foo" target="someHelper"` fails with
`symbol 'someHelper' not found in 'internal/foo'` whenever `someHelper` is
unexported, even though the symbol exists and carries a doc comment.

The cause is structural, not a lookup bug. `_handle_module`
(`selfdoc_core/extractors/go.py:491`) builds its candidate set from
`_extract_exported_declarations`, whose regexes hard-code an exported first
letter:

```python
r"([A-Z]\w*)"                          # exported name    (funcs, ~line 658)
re.match(r"^type\s+([A-Z]\w*)\s+(.*)", stripped)          # types
```

An unexported target is therefore unreachable by construction, and the error
message ("not found") misdescribes the situation: the symbol was found by the
reader and rejected by the extractor.

## Why it matters

The untargeted form (`ref path="internal/foo"` with no `target`) is a package
API dump, and restricting *that* to exported declarations is right — it is
public API documentation. But the **targeted** form is a different act: the
author has named one specific declaration and wants its signature and doc
comment spliced into surrounding prose. Architecture and internals pages are
exactly where that is useful, and those pages are mostly about unexported
machinery: the cross-device fallback, the hashing helper, the tar writer, the
UUID minting. Today such a page either carries directives that silently never
render (they fail `selfdoc check`, so the failure is at least loud) or it
duplicates the signature by hand, which then drifts.

This bit a consumer repo: an architecture page shipped seven targeted refs at
unexported functions. They failed every `selfdoc check`, the release aborted at
the docs gate, and the only available fix was to delete the directives and let
the prose stand alone.

## Options

**A. Targeted refs resolve unexported declarations too (recommended).**
Split the extraction: keep `_extract_exported_declarations` for the untargeted
package dump, add an all-declarations variant used only when `target` is set.
Regexes become `(\w+)` instead of `([A-Z]\w*)`. The untargeted output is
unchanged, so no existing page moves.

- Pro: the targeted form does what the author asked; internals pages become
  expressible; no new syntax.
- Con: a page can now splice a private symbol whose signature is not a
  stability promise. That is the author's call to make, and they made it by
  naming it.

**B. Opt-in attribute: `ref path="..." target="..." unexported="true"`.**
Same machinery, gated behind a flag.

- Pro: the "this is private" decision is explicit in the source.
- Con: a second spelling for one concept, and the flag carries no information
  the target name does not already carry (Go's case convention IS the marker).

**C. Improve only the error message.**
Say "symbol 'x' exists but is unexported; the ref directive resolves exported
declarations only" instead of "not found".

- Pro: cheap; stops the misdiagnosis.
- Con: does not unblock the use case. Worth doing regardless of A/B.

**D. Do nothing; document the restriction.**
Internals pages keep hand-writing signatures.

- Con: hand-written signatures drift, which is the problem selfdoc exists to
  solve.

Recommendation: **A + C.** A makes the targeted form honest, C makes every
remaining failure legible.

## Affected files

- `selfdoc_core/extractors/go.py` — `_handle_module` (~491), `_extract_exported_declarations` (~639), func/type/const/var regexes
- Error string at `go.py:496`
- Tests: the Go extractor's directive tests need an unexported-target case per option chosen
- Sibling extractors: check whether `typescript.py`, `kotlin.py`, `swift.py`,
  `dart.py`, `zig.py`, `svelte.py` have the same exported-only restriction on
  targeted refs; if so this is one decision applied across the family, not a Go
  fix.

## Effort

A: an hour or two including the sibling-extractor sweep and tests. C alone: 15
minutes.
