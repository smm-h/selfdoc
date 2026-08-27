# Project-name detection picks the wrong manifest in polyglot repos

## Context

`selfdoc_core/utils.py` `_read_project_field(base_dir, "name")` resolves the
project name via a fixed file-precedence chain: `pyproject.toml`, then
`package.json`, then `go.mod`. The strictcli support layer
(`selfdoc/strictcli_support.py`, the "Schema project_id ... does not match
project name" check) compares that name against the schema's `project_id`.

## Problem

The chain stops at the first manifest that exists, not at the manifest of the
project's actual language. A Go project (schema `project_id` = the Go module
path, `go.mod` present) whose repo also contains a `package.json` — e.g. a
browser-based test harness for a local web UI, named something like
`<project>-webui-tests` — resolves its "project name" from that package.json.
The name check then hard-errors:

```
ValueError: Schema project_id 'github.com/<owner>/<project>' does not match
project name '<project>-webui-tests'. Wrong schema file?
```

`selfdoc gen` fails for such a repo, which also blocks the release pipeline
step that runs it. This happened live on a Go project with a strictcli schema
and an incidental root package.json. The repo's own `selfdoc.json` declared
`source: [{path: ".", language: "go"}]`, so the correct manifest was knowable.

## Possible solutions

### A. Drive manifest choice from the declared source language

When `selfdoc.json` declares source languages, resolve the name from the
matching manifest: go -> go.mod module path, python -> pyproject.toml, js ->
package.json. Fall back to the existing chain only when no language is
declared.

- Pros: uses information the config already states; deterministic; fixes the
  polyglot case exactly; no heuristics.
- Cons: name resolution becomes config-dependent; multi-language `source`
  lists need a defined priority (e.g. first entry wins) — one small decision.

### B. Match against every manifest present

Collect names from all manifests that exist and accept the schema if
`project_id` matches ANY of them.

- Pros: minimal change; no config coupling.
- Cons: weakens the check (a wrong schema matching a stray manifest passes);
  keeps the conceptually wrong "first file wins" identity for other callers
  of `_read_project_field`.

### C. Prefer go.mod when the schema's project_id looks like a module path

- Pros: tiny.
- Cons: heuristic special-case; leaves the underlying chain wrong for the
  python-project-with-package.json case (a pyproject repo with a JS asset
  toolchain has the same latent bug in reverse order today: pyproject wins,
  which happens to be right — the go case shows the chain design itself is
  the problem).

A is the structural fix; B and C are patches around the chain.

## Affected files

- `selfdoc_core/utils.py` (`_read_project_field`)
- `selfdoc/strictcli_support.py` (the project_id check and its error text)
- `tests/test_strictcli_support.py` (the mismatch test; add a polyglot-repo
  case: go.mod + unrelated package.json must pass)

## Effort estimate

Small-to-medium: the resolution change plus tests; A needs the source-language
plumbing from config into `_read_project_field` or a new resolver beside it.
