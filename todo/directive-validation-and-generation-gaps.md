# Directive validation and generation gaps (three related findings)

## Context

While setting up directive-driven root-file templates for a Go CLI project, a
consumer hit three independent gaps in the directive/generation pipeline. They
are bundled here because they share the same subsystems (check validation,
strictcli page generation, content directives) and could be triaged together.

## Finding 1: `selfdoc check` never validates root-file templates

**Problem.** `resolve_all_docs` (selfdoc/docs.py, ~lines 55-57) explicitly
skips underscore-prefixed files, and root-file templates are only resolved by
`gen` (`generate_root_files` in gen.py) — never by `check`. Consequences:

- Directives inside `docs/_README.md` / `docs/_CLAUDE.md` are never validated
  by `check`. A broken directive (bad path, wrong args) only surfaces at `gen`
  time, as an embedded `> *[selfdoc: ...]*` blockquote in the generated root
  file — which can then be committed unnoticed.
- A project whose only directives live in root templates gets the notice
  "No directives found in documentation templates." from `check`
  (check.py, print_results, ~line 1690) even when the templates contain many
  working directives. Misleading in both directions: it suggests the project
  is not directive-driven, and it hides that nothing was validated.

**Proposed solution.** In `check`, resolve `root_files` templates through the
same `parse_directives`/`resolve_directives` path used for site pages, and
include their directives in `directive_results` (labelled with the template
path). Only print "No directives found" when site pages AND root templates
together contain zero directives.

- Pros: closes the validation blind spot; the notice becomes truthful; no
  behavior change for projects without root_files.
- Cons: check gets slightly slower (root templates resolve directives against
  source/schema); FAILED results in templates will now block checks that
  previously passed — desirable, but release pipelines will notice.

**Affected files:** selfdoc/check.py, selfdoc/docs.py (or a shared helper),
tests for check.

## Finding 2: reworded strictcli help text leaves stale CLI-page descriptions

**Problem.** `_read_existing_cli_description` + `_render_command_page`
(selfdoc/strictcli_support.py) preserve an existing `description:` frontmatter
value as "hand-edited" unless it equals, or is a prefix of, the freshly
computed default. When a command's help string in code is reworded, the stored
description (derived from the OLD help) is no longer a prefix of the new
default, so it is preserved forever — the page body regenerates but the
frontmatter description stays stale. Observed in practice: a help-text
rewording did not propagate until the generated `cli-*.md` was deleted and
regenerated. The module-page path (`_read_existing_description` in gen.py) has
the same pattern.

**Proposed solutions.**

1. Track provenance by hash: store a `description_source` hash (of the help
   text that generated the description) in frontmatter or in
   `.selfdoc/hashes/`. On gen: if the stored description was auto-generated
   from a previous help text (hash matches an auto-derivation), regenerate it;
   only preserve when it was genuinely hand-edited (no matching hash).
   - Pros: exact; preserves real hand edits; infrastructure (hashes store)
     already exists.
   - Cons: needs a migration story for existing pages without the hash.
2. A `selfdoc gen --refresh-descriptions` flag that force-regenerates all
   auto-derived descriptions.
   - Pros: trivial.
   - Cons: manual escape hatch; agents won't know to run it — the stale state
     remains the default outcome (soft-guidance antipattern).

Option 1 is the structurally correct fix.

**Affected files:** selfdoc/strictcli_support.py, selfdoc/gen.py,
selfdoc/staleness.py, tests.

## Finding 3: `list-modules` is unusable for non-Python projects

**Problem.** `resolve_list_modules` emits one bullet per source FILE —
including `_test.go` files — with no summaries for non-Python languages,
because `_extract_first_line_any` (selfdoc/content.py, ~lines 375-383) returns
None for anything but Python. For a Go project with 7 packages it produced 22
description-less bullets. The directive is effectively Python-only, which is
not documented.

**Proposed solution.** For Go (and other supported extractor languages): group
by package/module rather than by file, skip test files, and source the summary
from the language extractor's module docstring (the Go extractor already
parses package doc comments for `ref`/`prose-desc`). Fall back to the current
behavior only when no extractor exists for the language.

- Pros: makes the directive language-consistent with `ref`/`prose-desc`;
  matches user expectations ("modules", not "files").
- Cons: per-language grouping rules (Go package vs TS module vs Python file)
  need defining; snapshot tests per language.

**Affected files:** selfdoc/content.py, extractors (go, ts) if summary hooks
are missing, tests.

## Effort estimate

Finding 1: small (a day incl. tests). Finding 2 (option 1): medium (hash
provenance + migration, ~1-2 days). Finding 3: medium (~1 day per language
with tests). Independent — can land separately.
