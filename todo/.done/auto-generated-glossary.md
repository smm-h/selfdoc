# Auto-generated glossary page

## Problem

The `.glossary` CSS exists for manually-authored glossary blocks, but there is no mechanism to aggregate all `<dfn>` terms across the entire site into a single glossary page. Users must manually maintain glossary content.

## Proposed solution

During `selfdoc build`, after all pages are processed:

1. Collect all `<dfn>` terms and their definitions from `DefinedTermSet` JSON-LD data (already generated per-page).
2. Deduplicate by term name (keep the first definition if a term appears on multiple pages).
3. Generate a `glossary.html` page with all terms in alphabetical order, using the existing `<div class="glossary"><dl><dt><dfn>...</dfn></dt><dd>...</dd></dl></div>` structure.
4. Add the glossary page to the sidebar navigation.
5. Make this opt-in via a `selfdoc.json` config key (`"glossary": true`).

## Affected files

- `selfdoc/build.py` — glossary page generation after HTML generation
- `selfdoc/html.py` — glossary page template, nav integration
- `selfdoc/config.py` — `glossary` config key validation

## Effort

Medium. The term data is already extracted during HTML generation (DefinedTermSet JSON-LD). The main work is building the aggregation pipeline and the page template.
