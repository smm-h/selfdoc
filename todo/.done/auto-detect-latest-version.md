# Auto-detect latest version in selfdoc.json

## Problem

The `version` and `versions` fields in `selfdoc.json` must be manually updated on every release. This is easy to forget, leading to stale version references in documentation configs. For example, claudestream's `selfdoc.json` was stuck at `0.3.0` while the project had reached `0.5.1`.

## Proposed solution

Support a `"latest"` keyword (or auto-detection) so `selfdoc.json` doesn't need manual version bumps.

Options:

- **Auto-detect from project file**: selfdoc already knows the project language. It could read the version from `pyproject.toml` (Python), `package.json` (npm), `VERSION` (Go), etc. at build/gen time. The `version` field in `selfdoc.json` would become optional — if omitted, selfdoc resolves it automatically.
- **`"version": "latest"` sentinel**: Explicitly opt into auto-detection. At gen/build time, selfdoc resolves `"latest"` to the actual version from the project file.
- **Remove `version` from selfdoc.json entirely**: Always auto-detect. One less thing to maintain. Breaking change but selfdoc is pre-1.0.

For the `versions` array, selfdoc could auto-append new versions when it detects a version not yet in the list, or derive the list from git tags.

## Affected files

- `selfdoc/config.py` (or equivalent config loader) — version resolution logic
- `selfdoc/gen.py` (or equivalent) — use resolved version during generation
- Every consumer project's `selfdoc.json` — migration if the field is removed

## Effort

Small to medium. The version-reading logic per language likely already exists or is trivial. The main design decision is which option to pick.
