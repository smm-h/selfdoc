# XREF002 uses os.path.isfile for Go package paths

## Bug

check.py line 256 uses `os.path.isfile(resolved_path)` to validate that a directive's source path exists. For Go packages, the resolved path is a directory (e.g., `internal/audit`), not a file. `os.path.isfile()` returns False for directories, causing a spurious XREF002 error on every generated Go API reference page.

## Impact

Every Go project using selfdoc v0.16.0 with per-package source entries fails `selfdoc check` with 19 XREF002 errors (one per generated doc page), even though all directives resolve successfully and coverage is 100%.

## Fix

Line 256 should use `os.path.exists()` instead of `os.path.isfile()`, or check `os.path.isfile() or os.path.isdir()`. Go packages are directories; Python modules are files. The check should accept both.
