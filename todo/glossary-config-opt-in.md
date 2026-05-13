# Glossary page config opt-in

## Status: Pending | Priority: Low | Effort: Small

## Problem

The auto-generated glossary page runs unconditionally whenever `<dfn>` terms exist and no user-authored `glossary.md` is present. There is no way to disable it via `selfdoc.json`.

## Solution

Add a `"glossary"` boolean config key to `selfdoc.json` (default `true`). When `false`, skip glossary page generation even if `<dfn>` terms exist.

## Affected files

- `selfdoc/config.py` -- add and validate the key
- `selfdoc/html.py` -- gate glossary generation on the config value
- `tests/test_build.py` -- test that `glossary: false` suppresses generation
