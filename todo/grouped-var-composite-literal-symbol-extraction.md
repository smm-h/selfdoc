# Grouped-var composite literals confuse the Go symbol extractor

## Context

selfdoc's coverage check requires every exported symbol of a documented Go
package to be documented. The Go symbol extractor that feeds it reads source
with regular expressions rather than parsing Go.

## Problem

Inside a grouped `var ( ... )` block whose entries are composite literals,
the extractor takes every capitalized line start for an exported symbol. A
struct literal spelled with one field per line (fields like `SQL:`, `Why:`,
`Doc:`, `PG:`) therefore produces phantom "exported symbols" that no page
can ever document, and the package's coverage drops far below 100% with no
real undocumented symbol behind it.

Observed in a consumer project: a package holding its data tables in grouped
`var` blocks reported coverage in the high-80s percent, entirely from
composite-literal field keys. The consumer worked around it by splitting the
grouped blocks into standalone `var` declarations (behavior-neutral, but the
workaround must be remembered forever and re-applied to every new table, and
a comment now guards each split against being regrouped).

## Solutions

1. **Parse Go properly for symbol extraction (most correct).** Use go/ast
   (or `go doc`-style export data) to enumerate exported symbols instead of
   scanning text. Eliminates this defect class entirely — field keys, string
   contents, and comments can never be mistaken for declarations again.
   Effort: medium — replaces the extractor's core, but the Go standard
   library does all the parsing.
2. **Track brace depth in the existing scanner.** Only treat a capitalized
   token as a declaration when it appears at declaration depth inside the
   `var` group (depth one), not inside a literal's braces. Small, targeted,
   stays lexical — but remains a text heuristic and the class can recur in a
   shape the heuristic misses.
3. **Document the limitation and recommend ungrouped vars.** Zero code
   change; makes every affected consumer carry the split-blocks workaround
   permanently. Weakest option.

## Affected area

The Go source/symbol extractor behind the coverage computation and the
per-package documentation pages.

## Effort

Option 2 is small; option 1 is medium and removes the class for good.
