# ref path='.' ambiguity in multi-language projects

## Problem

`selfdoc gen` crashes during doc site generation with:

```
RuntimeError: Ambiguous directive :::ref path='.' resolves in multiple languages: go, typescript, zig
```

Root file generation (CLAUDE.md, README.md) completes fine. The crash happens in `resolve_all_docs` when processing auto-generated doc pages.

## Context

Discovered while updating gamehome (multi-language monorepo) to use selfdoc 0.13.0's multi-language source config. The project has 13 source paths across Python, Go, TypeScript, and Zig. Root files generate correctly because the template only uses explicit paths. But doc page generation produces a `ref path='.'` directive that's ambiguous because `.` matches multiple source paths.

## Root cause

Likely an auto-generated doc page for a source root (e.g., `router/`, `sdk-go/`, `runtime/src/`) that emits `ref path='.'` to document the package/module at the root of that source path. In single-language mode this was unambiguous. In multi-language mode, `.` matches every source path, and the resolver can't pick one.

## Proposed fix

When resolving `ref path='.'` in a doc page, the resolver should know which source path the doc page belongs to (from its filesystem location or generation context) and dispatch to that source path's language, rather than searching all source paths.

## Affected files

- `selfdoc/resolver.py` — ambiguity detection logic
- `selfdoc/docs.py` — `resolve_all_docs` context passed to resolver

## Effort estimate

Small — the resolver needs the source-path context that's already available in the doc generation pipeline.
