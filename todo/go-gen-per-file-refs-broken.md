# Go gen produces per-file ref paths that don't resolve

## Problem

`selfdoc gen` for Go projects generates one doc page per `.go` file, using file-stem ref paths like `ref path="commit"` (for `commit.go`) or `ref path="internal/commit/amend"` (for `internal/commit/amend.go`). But the `_handle_module` ref handler in `extractors/go.py` resolves paths as **package directories** via `_resolve_package_dir()`, which calls `os.path.isdir()`. File stems aren't directories, so 26 of 27 generated pages fail validation.

The only ref that works is `path="."` (the project root, which is a real directory).

## Affected code

- `selfdoc/gen.py`, function `_file_to_module_path` (line ~64): converts `commit.go` to `"commit"`, `internal/commit/amend.go` to `"internal/commit/amend"`. These are file stems, not package dirs.
- `selfdoc/extractors/go.py`, function `_resolve_package_dir` (line ~216): expects the ref path to be a directory containing `.go` files.

## Two sub-problems

1. **Root-level files**: `commit.go`, `main.go`, `push.go`, etc. are all in the root package (`.`). `gen` produces `path="commit"`, `path="main"`, `path="push"`, but the package is `"."`.

2. **Internal files**: `internal/commit/commit.go` and `internal/commit/amend.go` are both in the `internal/commit` package. `gen` produces `path="internal/commit/commit"` and `path="internal/commit/amend"`, but the package is `"internal/commit"`.

## Fix options

**Option A: Make gen produce per-package pages (not per-file)**
- `gen.py` groups Go files by their parent directory and emits one doc page per package.
- Each page's ref points to the package directory.
- Avoids duplicates. Matches Go's natural package-level documentation model.

**Option B: Make the ref handler support file-level paths**
- `_resolve_package_dir` (or a new `_resolve_file`) checks if `path + ".go"` exists as a file, and if so, extracts only that file's symbols.
- Keeps per-file granularity. More pages, but each focuses on one file's exports.

Option A is simpler and more idiomatic for Go. Option B gives finer granularity but adds complexity.

## Impact

Blocks releases for Go projects that use selfdoc (currently blocking safegit v0.11.0 release).

## Scope

Medium. Primarily changes in `gen.py` (page generation logic) and possibly `go.py` (ref resolution).
