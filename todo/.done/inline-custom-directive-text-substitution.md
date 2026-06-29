# Inline custom directives break when surrounded by prose text

## Problem

Custom directives that return plain text (not key-value resolved) don't work inline in prose. The `_INLINE_RE` regex at `selfdoc/directives.py:48` captures `(\S+)` as the directive name, which greedily eats trailing punctuation.

Example: `(v:-: rlsbl-version).` parses the directive name as `rlsbl-version).` instead of `rlsbl-version`, because `)` and `.` are non-space characters.

The inline regex expects attributes in `key="value"` format after the name:
```python
_INLINE_RE = re.compile(r':-:\s+(\S+)((?:\s+\w+="[^"]*")*)')
```

This works for `:-: var key="project.version"` (has attributes) but not for `:-: rlsbl-version` (no attributes, just returns text).

## Expected behavior

`(v:-: rlsbl-version).` should resolve to `(v0.7.0).` — the directive name is `rlsbl-version`, the surrounding `(v` and `).` are prose.

## Suggested fix

The `_INLINE_RE` regex should stop capturing the directive name at non-word characters that aren't part of the name. Something like `(\w[\w-]*)` instead of `(\S+)`, since directive names are alphanumeric with hyphens.

## Context

Discovered in orxtra (smm-h/orxtra) while trying to use custom directives for dynamic version and project count in CLAUDE.md prose: "Active implementation (v:-: rlsbl-version). Monorepo with :-: project-count sub-projects..."
