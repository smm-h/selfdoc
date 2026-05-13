# Coverage for Go and TypeScript

## Problem

`_compute_python_coverage` provides per-symbol documentation coverage for Python projects using `ast`. Go and TypeScript projects get `coverage = None` — no coverage data at all. The `selfdoc check` output simply omits the coverage section for non-Python projects.

## Proposed solution

### Go coverage

Implement `_compute_go_coverage`:

1. Walk `.go` source files.
2. Extract exported symbols: functions, types, methods, constants whose names start with an uppercase letter (Go's visibility convention).
3. For each `:::module` directive referencing a Go file, check which exported symbols appear in the resolved content.
4. Return `CoverageStats` with total/referenced/documented/undocumented counts.

Use regex-based parsing (matching the Go extractor pattern) since `ast` is not available for Go.

### TypeScript coverage

Implement `_compute_typescript_coverage`:

1. Walk `.ts`/`.tsx` files.
2. Extract exported symbols: items with `export` keyword (functions, classes, interfaces, types, constants).
3. Same matching logic as Python/Go.

Use regex-based parsing (matching the TypeScript extractor pattern).

## Affected files

- `selfdoc/check.py` — new `_compute_go_coverage` and `_compute_typescript_coverage` functions, dispatch by language
- `tests/test_check.py` — coverage tests for Go and TypeScript projects

## Effort

Medium-high. Each language needs symbol extraction logic. Go is simpler (uppercase = exported). TypeScript is harder (`export` keyword detection, re-exports, barrel files).
