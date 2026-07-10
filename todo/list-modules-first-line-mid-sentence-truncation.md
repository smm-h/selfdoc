# list-modules truncates summaries mid-sentence at the first source line

## Context

The per-package `list-modules` rendering for Go (added in 0.27.0) sources
each bullet's summary from the package doc comment. A consumer project's
generated output shows bullets cut mid-sentence.

## Problem

The summary extraction takes the first LINE of the doc comment, not the
first sentence. Go doc comments are conventionally wrapped at ~75 columns,
so multi-line first sentences get cut at the source line break, producing
bullets like:

- **internal/classify**: Package classify determines a file's group name (format) and its.

(the stray trailing period appears to be appended to the truncated
fragment). Likely in `_first_line_of` / the summary path of
`_list_modules_by_package` in selfdoc_core/content.py, fed by the Go
extractor's `module_docstring`.

## Proposed solutions

1. Extract the first SENTENCE: join the doc comment's first paragraph
   (lines until a blank line), then cut at the first sentence terminator
   (`. ` / end of paragraph). This matches how godoc renders synopses
   (go/doc's Synopsis does exactly this).
   - Pros: correct summaries regardless of source wrapping; consistent
     with Go tooling conventions.
   - Cons: sentence-splitting heuristics need a couple of edge-case tests
     (abbreviations, no terminator).
2. Use the whole first paragraph unjoined-length-capped (e.g. 155 chars,
   like page descriptions).
   - Pros: trivially simple.
   - Cons: can still end mid-sentence, just later.

Option 1 is the correct fix. Applies to all languages whose doc comments
wrap across source lines, not just Go.

## Affected files

- selfdoc_core/content.py (summary extraction for list-modules)
- possibly selfdoc_core/extractors/go.py (if module_docstring should return
  the joined paragraph instead)
- tests with a wrapped multi-line first sentence

## Effort estimate

Small — an hour including tests.
