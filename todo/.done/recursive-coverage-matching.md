# Coverage matching is non-recursive while discovery is recursive

## Problem

`_compute_coverage` in `check.py` discovers symbols recursively via `os.walk` (finding all `.go` files in subdirectories), but when matching symbols to directives, it uses exact directory equality (`os.path.abspath(file_dir) == dir_abs`). A directive like `:-: ref path="."` resolves to the project root, but symbols in `internal/commit/` etc. never match because their parent directory isn't the root.

This causes projects like safegit (where all public symbols live in `internal/` subpackages) to report 0% coverage despite having doc comments on every symbol.

## Proposed fix

In `check.py` lines ~853-862, change the directory comparison from `==` to `startswith` so that a directive for a parent directory also counts symbols in subdirectories:

```python
# Before:
if os.path.abspath(file_dir) == dir_abs:

# After:
if os.path.abspath(file_dir).startswith(dir_abs):
```

Alternatively, only count symbols in directories that have a corresponding directive (make discovery non-recursive to match matching), but that would miss undocumented symbols in the report.

## Related issue

The Go extractor's `_handle_module` uses `os.listdir` (non-recursive), so `ref path="."` only renders root-package symbols. Projects need one `ref` directive per subpackage. A recursive mode for the Go extractor would also help, but is a separate feature.

## Effort

Small. The coverage matching fix is a one-line change. The recursive extractor is a separate, medium-effort feature.
