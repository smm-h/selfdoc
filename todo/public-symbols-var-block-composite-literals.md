# public_symbols miscounts composite-literal fields inside var blocks

## Problem

The `public_symbols` extractor treats every line inside a Go `var (...)`
block that starts with a capitalized identifier as a package-level symbol.
A multi-line composite literal inside such a block therefore contributes
its FIELD NAMES as "symbols":

```go
var (
    SomeFeature = Feature{
        Name:  "...",   // <- counted as symbol "Name"
        Floor: "...",   // <- counted as symbol "Floor"
        Used:  "...",   // <- counted as symbol "Used"
    }
)
```

`Name`, `Floor` and `Used` are struct fields of the literal, not package
symbols. The renderer can never emit documentation for them, so they are
PERMANENTLY UNREACHABLE coverage: a project with such a declaration can
never reach a 100% `coverage_threshold`, and the only in-project
workarounds are restructuring the source (moving the declarations out of
the var block into plain `var` statements) or lowering the threshold —
one distorts the code for the tool, the other weakens the check for
every real page.

## Observed

Found live in a consumer project: two composite-literal feature
declarations inside a `var (...)` block produced three phantom symbols
and pinned coverage below threshold until the source was restructured.

## Solution sketch

Parse symbols from the AST (or at minimum track brace depth) so only
depth-zero identifiers inside the var block are counted. Go's own
`go/ast` distinguishes `ValueSpec` names from composite-literal fields
trivially; a line-based heuristic cannot.

## Affected

The `public_symbols` extraction and every consumer's coverage figure.

## Effort

Small if the extractor already parses Go files with go/ast; medium if it
is currently line/regex-based (the fix is then "switch this extractor to
the AST", which likely also fixes other edge shapes: multi-name specs,
iota groups, deeply nested literals).
