# `selfdoc gen` refuses a Go repo that also carries a private `package.json`

## Symptom

`selfdoc gen` hard-errors before generating anything:

```
ValueError: Schema project_id 'github.com/smm-h/<project>' does not match
project name '<project>-webui-tests'. Wrong schema file?
```

The schema is correct and freshly dumped. The project is a Go module whose
`.strictcli/schema.json` carries `project_id` = the go.mod module path (Go
strictcli reads go.mod at dump time and has no other source for it). The repo
*also* has a root `package.json`, marked `"private": true`, that exists only to
run the project's browser-side test harness (vitest/playwright over an embedded
web UI). It is never published, and the project's only release target is the Go
module.

## Cause

`selfdoc/strictcli_support.py::read_schema_json` validates the identity like
this:

```python
expected = _read_project_field(base_dir, "name")
if expected != "unknown" and project_id != expected:
    raise ValueError(...)
```

and `selfdoc_core/utils.py::_read_project_field` resolves `name` through a fixed
lookup chain: `pyproject.toml`, then `package.json`, then `go.mod` (go.mod is
consulted **only** if neither of the first two files exists). A polyglot repo
therefore gets its identity from whichever manifest happens to sort first in
that chain, not from the toolchain that produced the schema.

The check itself is worth keeping -- it catches a schema copied in from another
project. What is wrong is the single-candidate comparison.

## Effect

Every release of such a project is blocked: `rlsbl release run` runs
`selfdoc gen --no-auto-commit` at its docs step and treats a non-zero exit as a
hard error, so the release aborts before the version bump. There is no local
workaround that does not either rename a package (forbidden without explicit
owner approval) or restructure the repo to get the auxiliary manifest out of the
root.

## Reproduction

1. A Go project with `.strictcli/schema.json` at schema version 2 (strictcli
   go >= 0.33.0 dumps `project_id` from go.mod).
2. Add a root `package.json` whose `name` is anything other than the go.mod
   module path.
3. `selfdoc gen` -> the ValueError above, with nothing generated.

## Candidate fixes (a design decision, not obvious)

1. **Compare against every identity the repo declares.** Collect the names from
   `pyproject.toml`, `package.json` and `go.mod` and accept a `project_id` that
   matches any of them. Simple, and keeps the copied-schema check meaningful;
   slightly weaker than a single-authority comparison.
2. **Ask the source declaration which language produced the schema.**
   `selfdoc.json` already declares `source: [{path, language}]`, so a schema from
   a Go source is compared against go.mod's module path, a Python one against
   `[project].name`, and so on. This is the most correct: the schema's identity
   is compared against the identity of the toolchain that wrote it.
3. **Ignore a `"private": true` manifest** when looking for the project name. A
   narrow fix for this exact shape, and it leaves the general polyglot case
   broken.
4. **Let `selfdoc.json` declare the expected `project_id` explicitly.** Adds a
   config key whose only job is to restate something two manifests already know.

Option 2 looks right and reuses a declaration that already exists; option 1 is
the cheapest complete fix.

## Affected files

- `selfdoc/strictcli_support.py` (`read_schema_json`, the `project_id` check)
- `selfdoc_core/utils.py` (`_read_project_field`, the lookup chain)
- Regression test: a fixture repo with a `go.mod` **and** a differently-named
  root `package.json` plus a v2 schema, asserting `gen` succeeds -- and a second
  fixture asserting a genuinely foreign `project_id` is still refused.

## Effort

Small: one comparison plus a lookup change, and two fixture tests. The
consuming project stays blocked until it is released.
