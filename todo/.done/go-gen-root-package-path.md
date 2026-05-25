# Go gen uses module name instead of "." for root package

## Problem

`selfdoc gen` for Go projects generates the root package doc page with `ref path="<module-name>"` (e.g., `ref path="safegit"`). But the ref handler resolves paths as directories, and there's no `safegit/` directory — the root package is at `"."`.

Internal packages work correctly (`ref path="internal/commit"` resolves to the `internal/commit/` directory). Only the root package is wrong.

## Expected

The root package doc should use `ref path="."`, not `ref path="<module-name>"`.

## Affected code

`selfdoc/gen.py`, the function that computes the ref path for Go packages. For the root package (directory `"."`), it currently uses the Go module name from `go.mod`. It should use `"."` instead.

## Impact

Blocks selfdoc check for any Go project that has root-level `.go` files (which is most Go projects). Currently blocking safegit release — workaround is deleting the generated root package doc page.

## Scope

Small — one conditional in gen.py to check if the package directory is `"."` and use that as the ref path instead of the module name.
