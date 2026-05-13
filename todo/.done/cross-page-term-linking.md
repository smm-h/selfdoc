# Cross-page `<dfn>` term linking

## Problem

`_apply_definitions` wraps terms in `<dfn>` tags within a single page, and `DefinedTermSet` JSON-LD is generated per-page. But there is no mechanism to link term *usage* on one page to the *definition* on another. A user reading about "resolvers" on the API page has no way to jump to the definition on the concepts page.

## Proposed solution

Build a global term index during the build pipeline:

1. After all pages are processed, collect all `<dfn>` terms and their page paths into a `{term: page_path#id}` index.
2. In a second pass over all HTML output, find inline `<code>` elements whose text matches a defined term (exact, case-insensitive).
3. Wrap those matches in `<a href="page_path#term-id" class="term-link">` linking to the definition page.
4. Skip self-links (don't link a term on the page where it's defined).

## Affected files

- `selfdoc/build.py` — second pass after `generate_html`, term index construction
- `selfdoc/html.py` — possible helper for term link injection
- `selfdoc/themes/minimal.css` — `.term-link` styling (dotted underline, distinct from regular links)

## Effort

Medium-high. Requires a post-processing pass over all HTML files, careful deduplication, and handling of edge cases (terms inside code blocks should not be linked, plural forms, etc.).
