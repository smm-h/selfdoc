# Go gen creates per-file paths that ref directive can't resolve

## Problem

`selfdoc gen` for Go projects creates per-file documentation pages (e.g., `internal-db-schema.md` with `ref path="internal/db/schema"`). The `ref` directive's Go resolver works at the package (directory) level, not the file level. So `ref path="internal/db/schema"` fails because no directory `internal/db/schema/` exists.

This affects any Go project using `selfdoc gen` -- root-level files produce pages like `delete.md` with `ref path="delete"`, and internal files produce pages like `internal-archive-archive.md` with `ref path="internal/archive/archive"`.

## Root cause

`gen.py`'s `_file_to_module_path` strips the `.go` extension but keeps the filename, producing per-file paths instead of per-package paths. Go's module system is package-based (directory-level), not file-based.

## Current workaround

Projects use `"gen": {"exclude": ["*"]}` in `selfdoc.json` to suppress all gen output, then manually create per-package doc pages with correct `ref path="internal/archive"` directives. This works but defeats the purpose of gen.

## Proposed fix

For Go projects, `gen` should produce one page per **package** (directory), not one per file. The `ref path` should point to the package directory (e.g., `internal/archive`), not individual files. Multiple `.go` files in the same package should be consolidated into a single doc page.

## Affected projects

- saferm (uses the `exclude: ["*"]` workaround)
- Potentially any Go project using selfdoc
