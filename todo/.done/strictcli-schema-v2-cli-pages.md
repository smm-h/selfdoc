# CLI reference pages are wrong for strictcli schema v2

## Context

strictcli 0.41.0 writes `.strictcli/schema.json` at `schema_version: 2`. The v2
encoding is not a superset of v1 — it deletes keys selfdoc reads and adds
constructs selfdoc has no rendering for. Every CLI reference page selfdoc
generates for a consumer on strictcli >= 0.41 is now inaccurate, and the
inaccuracy is silent: `selfdoc gen` succeeds, `selfdoc check` passes once the
DRIFT001 baselines are accepted, and the wrong page ships.

## Problem

### 1. Every flag renders as `str`

`selfdoc/strictcli_support.py:640` reads `fl.get("type", "str")`. Schema v2
**removed the `type` key** (and `repeatable`) from flag and arg entries: a value's
shape is now a real JSON Schema fragment under `value_schema`, from a closed
subset of `type` / `items` / `additionalProperties` / `enum` using JSON Schema's
own type names.

The `.get(..., "str")` default means the loss is not an error — every bool, int
and float flag in every consumer's docs now claims to be a string.

Mapping needed (v2 fragment -> rendered type):

| `value_schema` | render |
| --- | --- |
| `{"type": "string"}` | `str` |
| `{"type": "boolean"}` | `bool` |
| `{"type": "integer"}` | `int` |
| `{"type": "number"}` | `float` |
| `{"type": "array", "items": {...}}` | repeatable / `list[T]` |
| `{"type": "object", "additionalProperties": {...}}` | `dict[str, T]` |
| absent entirely | a choice flag — see (3) |

### 2. Presence is published and not rendered

v2 emits a `presence` key on **every** flag and arg entry (`required` /
`optional` / `default`), plus a `default` key exactly when presence is
`default`. The pages have a `Default` column that is now empty for every
required and every optional flag, with nothing saying which of the two it is.
strictcli's own `--help` renders exactly one presence marker per line
(`[required]` / `[optional]` / `[default: v]`); the generated page should carry
the same fact.

### 3. Choice flags are rendered as if their own name were typed

A choice flag has **no** `value_schema` — its value is a variant the closed
subset cannot express — and instead publishes nested `choices` plus `elect_by`,
each scoped entry a full flag entry with its own `value_schema`, `presence` and
`default`. Choice flags sit in the command's one `flags` array in declaration
order.

Rendering one as an ordinary row produces actively misleading documentation.
Under `elect_by: "member-flags"` the choice flag's own name is **never typed** —
it is only the handler key and the noun errors use — so a page listing

```
| `--mode` | | str | | | Which scrub mode to run |
```

tells a reader to type `--mode pattern`, which is not a thing. The tokens that
exist are the members (`--pattern`, `--file`, `--recipe`), each with its own
help, and each owning a **scope** of flags that are legal only while it is
elected. Under `elect_by: "selector-token"` the flag's name IS typed
(`--via email`), so the two spellings render differently.

Scopes nest to unlimited depth, so this is a recursive rendering, not a flat
one.

### 4. `choices` on a plain value flag are dropped

v2 splits a value flag's `choices=` in two: the values as an `enum` inside
`value_schema`, and the value-plus-help records beside it under `choices`
(`help` omitted when an entry declares none). Neither is rendered, so a page
loses the allowed values entirely — including cases where the help text used to
carry them in prose and no longer does, because the declaration now carries them.

### 5. `constraints` are published and not rendered

Each command entry carries a `constraints` array in declaration order, encoded
completely rather than indicatively: `{type, name, members}` where a member is
`{kind, name, when}` and `kind` is already resolved. The four kinds are
`at_least_one`, `all_or_none`, `requires`, `implies`. strictcli's `--help`
renders these under a `Constraints:` section; the generated page shows nothing,
so a rule like "at least one of `--commits`, `--id`" is invisible to a reader
of the docs.

### 6. `update_of` / `write_mode` / `nullable` are published and not rendered

A command declaring an update carries `update_of` (an object with `resource`,
`identity` and `properties`) and `write_mode` (`sparse` / `full_replace`),
emitted exactly together and never alone. A nullable property carries
`nullable` on its own flag entry, and the framework-minted `--unset-<prop>`
gets no entry of its own — exactly as `negatable` publishes `--no-<x>`, the
reader has to be told it exists.

The at-least-one-property rule and the meaning of an unsupplied property
(untouched under `sparse`, re-sent as read under `full_replace`) are the two
facts a reader most needs and neither appears.

### 7. Other v2 additions with no rendering

`config_format`, `config_path`, `config_conflict_mode`, per-flag `prefixed`,
per-command `flag_sets`, and a rewritten `defaults` block (the complete map of
what an omitted key means). Each appears exactly when a declaration departs
from the framework's own behavior, which makes them precisely the things worth
documenting.

## Suggested solutions

**A. Version-gate the reader, render v2 fully.** Read `schema_version` and
dispatch. Keep the v1 path for consumers still on the old floor, add a v2 path
that renders `value_schema` -> type, `presence`, `choices`, nested choice-flag
scopes, `constraints`, and `update_of`. Pro: correct for both, no consumer is
forced to upgrade in lockstep. Con: two renderers to keep alive; the v1 path is
dead weight the moment every consumer has migrated.

**B. Hard-error on an unrecognized `schema_version`.** Refuse to generate a CLI
page from a schema whose version the reader does not know, instead of silently
defaulting. This is the smallest change and should happen **regardless of which
of A/C is chosen**: the current `.get("type", "str")` is exactly the silent
degradation that let this ship. A schema selfdoc cannot read is a hard error,
not a page full of `str`.

**C. v2 only.** Drop the v1 path and require the new floor. Pro: one renderer,
and the v2 encoding is strictly more informative. Con: a consumer on an older
strictcli cannot generate CLI docs at all until it migrates.

Recommendation: **B immediately** (it converts a silent wrong page into a
visible refusal), then **A or C** depending on how many consumers are still
below the floor.

## Affected files

- `selfdoc/strictcli_support.py` — the schema reader and the page renderer;
  line 640 is the `type` read, and the flag-table emitter around it is where
  presence/choices/scopes/constraints/update_of all belong.
- Whatever emits the `| Name | Short | Type | Default | Env | Description |`
  table header — the column set itself needs revisiting, since `Default` alone
  cannot express three presence states.
- The DRIFT001 baseline mechanism: a schema-version change should arguably
  force a re-review rather than be acceptable as a description-only baseline.

## Reference

The v2 encoding is specified in strictcli's `docs/architecture.md` (the choice
flag encoding, constraint serialization) and `docs/flag-system.md` (presence,
choices records, choice flags, constraints, update commands). strictcli's
0.41.0 changelog entry for `--dump-schema` enumerates every key that moved.

## Effort

Medium. The reading side is mechanical once `value_schema` is mapped; the
rendering side needs a real design decision for nested choice-flag scopes and
for how three presence states fit a table that currently has one `Default`
column. Solution B alone is small and worth doing first.
