# Generated CLI pages never say which commands ask before they run

Filed 2026-08-05, found while re-sweeping both CLIs onto strictcli's redesigned
confirmation protocol.

## Problem

`selfdoc gen` builds a reference page per command from `.strictcli/schema.json`.
The schema carries a mandatory `effect` field on every command
(`read_only` | `mutating`) and, since strictcli 0.36.0, an optional
`consequential` boolean. `selfdoc/strictcli_support.py` translates neither: the
docstring on `read_schema_json` lists the fields it deliberately preserves
(`choices`, `hidden`, `deprecated`, `variadic`, `passthrough`, `repeatable`,
`negatable`) and `effect` is not among them.

The result, verbatim, is the whole of the generated `docs/cli-deploy.md` body:

```
# selfdoc deploy

Deploy the built documentation site to the configured provider
```

`selfdoc deploy` is `consequential`: it prompts before dispatch, and it refuses
outright on non-interactive stdin with
`error: stdin is not interactive; pass --approve-consequential to confirm`. A
reader of the published documentation cannot learn either fact. The first time
they find out is when their CI job dies.

This is not a selfdoc-only gap. selfdoc generates the CLI reference for every
strictcli project in the fleet, so every consequential command everywhere is
undocumented as such, and every `--dry-run` story is undocumented too.

## Work

1. Preserve `effect`, `consequential` and `grants` through `read_schema_json`'s
   translation.
2. Render them on the command page. Sketch, to be designed properly:
   - `consequential` commands get a prominent callout naming the exact non-TTY
     error and `--approve-consequential`, since that string is what a user will
     paste into a search box.
   - `mutating` commands get a line stating that `--dry-run` previews instead of
     performing.
   - `grants`, when present, are the authored one-line reasons for each
     dangerous step -- already written for a reader, and currently thrown away.
3. Decide whether `effect` also belongs on the CLI index page as a column, so
   the classification of a whole CLI is legible at a glance.
4. Pin the rendering in `tests/test_strictcli_support.py` alongside the existing
   flag/arg table tests.

## Affected files

- `selfdoc/strictcli_support.py` (translation + rendering)
- `tests/test_strictcli_support.py`
- every project's generated `docs/cli-*.md`, on the next `selfdoc gen`

## Effort

A day, including the callout wording -- which is the part worth getting right,
because it is the text that will appear on fourteen projects' documentation
sites.
