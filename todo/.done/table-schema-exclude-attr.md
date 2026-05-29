# Add `exclude` attribute to `table-schema` directive for JSON files

## Problem

The `table-schema` directive renders ALL top-level keys from a JSON file. When the file contains volatile keys like `version`, the rendered output changes on every version bump, causing STALE001 (content hash changed but description wasn't updated) on every release.

Real-world case: rlsbl's `docs/configuration.md` uses `:-: table-schema path="selfdoc.json"`. The `selfdoc.json` file has `version` and `versions` keys that change on every release. This triggers STALE001 during the release pipeline, requiring manual pre-sync workarounds.

## Proposed fix

Add an `exclude` optional attribute to the `table-schema` directive:

```
:-: table-schema path="selfdoc.json" exclude="version,versions"
```

Implementation:
- `selfdoc/catalog.py`: add `"exclude"` to `optional_attrs` for `table-schema`
- `selfdoc/extractors/python.py` `_schema_from_json()` (lines 629-655): parse `exclude` as a comma-separated list, filter out matching keys before rendering the table

Consumer usage (rlsbl):
```
:-: table-schema path="selfdoc.json" exclude="version,versions"
```

## Root cause analysis

- `_schema_from_json()` iterates `for key, value in data.items()` with no filtering
- `compute_content_hash()` in `staleness.py` hashes the resolved content (including the rendered table)
- STALE001 fires when content hash changes but description stays the same
- The version field in selfdoc.json changes on every release, so the hash changes every time

## Effort

Small. One new optional attribute, a few lines of filtering in `_schema_from_json`, catalog update, and a test.
