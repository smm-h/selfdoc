# Front-matter description seeding reads the wrong comment

## Context

When `selfdoc gen` creates a generated per-package doc page that does not
exist yet, it seeds the front-matter `description` and marks it
`seeded: true`.

## Problem

The seed source appears to be the leading comment block of the package's
first `.go` file in name order, not Go's package doc comment. A file that
sorts first and opens with a build constraint produces a description that
is the constraint itself.

Observed live: a package whose `cleanup_unix.go` sorts before its main
file (which carries the real package doc comment) was regenerated from
scratch and received:

```yaml
description: "go:build !windows"
seeded: true
```

A `//go:build` line followed by a blank line is not a doc comment by Go's
own rules, but the seeder took it anyway.

## Expected behavior

Seed from the go/doc package comment (`doc.Package.Doc`, first sentence)
— the language's own definition of a package description. That is
independent of file name ordering and can never be a build constraint.

## Affected

The description-seeding path in the generator (wherever a missing page's
front matter is first written).

## Solutions

1. Parse the package with `go/doc` (or `go list -f '{{.Doc}}'`) and use
   its package comment's first sentence. Recommended — it is the one
   correct source.
2. Minimal patch: skip leading comment blocks that are build constraints
   or otherwise not doc comments (no blank-line adjacency to `package`).
   Weaker: still file-order-dependent.

## Effort

Small. One seeding call site plus a regression test with a package whose
first file by name order opens with a build constraint.
