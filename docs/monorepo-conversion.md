---
title: Monorepo Conversion Plan
description: Plan for converting selfdoc from a standalone repo to a monorepo with three rlsbl releasables
date: 2026-07-06
---

# Monorepo Conversion Plan

This document describes the conversion of selfdoc from a standalone rlsbl-managed repo to a monorepo with three releasables: `selfdoc_core`, `selfdoc`, and `selfblog`.

## Current State

- Single repo with `.rlsbl/` directory (standalone mode)
- Three Python packages already exist: `selfdoc/`, `selfdoc_core/`, `selfblog/`
- Single `pyproject.toml` at root builds all three via hatch `packages` config
- Single version (`0.26.1`) shared across all packages
- Published to PyPI as `selfdoc` and npm as `selfdoc`

## Target State

- Monorepo with `.rlsbl-monorepo/` and `workspace.toml`
- Three releasables, each with independent versioning and changelogs
- Each releasable has its own `pyproject.toml` (already created in `selfblog/` and `selfdoc_core/`)

### Releasable: selfdoc_core

- **Path:** `selfdoc_core/`
- **Target:** PyPI (`selfdoc_core`)
- **Dependencies:** none (pure stdlib)
- **Contains:** build engine, HTML generation, directive parsing, extractors, config, theming, utilities

### Releasable: selfdoc

- **Path:** `selfdoc/`
- **Dependencies:** `selfdoc_core`, `strictcli`
- **Targets:** PyPI (`selfdoc`), npm (`selfdoc`)
- **Contains:** CLI (init, build, serve, deploy, check, gen, gen-data), re-export shims

### Releasable: selfblog

- **Path:** `selfblog/`
- **Target:** PyPI (`selfblog`)
- **Dependencies:** `selfdoc_core`, `strictcli`
- **Contains:** CLI (post, assembly, build --target posts), assembly infrastructure, shared elements, unified builder

## Conversion Steps

### 1. Initialize monorepo structure

```
rlsbl monorepo init
```

This creates `.rlsbl-monorepo/workspace.toml`. The standalone `.rlsbl/` directory must be removed or migrated.

### 2. Configure workspace.toml

```toml
[[releasables]]
name = "selfdoc_core"
path = "selfdoc_core/"
targets = ["pypi"]

[[releasables]]
name = "selfdoc"
path = "selfdoc/"  # or root
targets = ["pypi", "npm"]

[[releasables]]
name = "selfblog"
path = "selfblog/"
targets = ["pypi"]
```

### 3. Migrate changelog history

The existing `.rlsbl/changes/*.jsonl` files contain history for the unified package. These need to be attributed to the appropriate releasable:

- Most entries are about selfdoc CLI or core functionality
- Blog/assembly entries belong to selfblog
- Core engine entries belong to selfdoc_core

### 4. Per-package pyproject.toml activation

Currently the per-package `pyproject.toml` files (in `selfblog/` and `selfdoc_core/`) are inert documentation. To activate them:

- Remove `[tool.hatch.build.targets.wheel] packages` from root `pyproject.toml`
- Each package gets its own build, its own version, its own wheel
- Cross-dependencies use registry versions (not path sources)

### 5. CI/CD scaffolding

Each releasable needs its own publish workflow. `rlsbl scaffold` in monorepo mode generates per-releasable workflows.

## Open Questions

- **First-of-kind:** `rlsbl monorepo` has been used for fresh monorepos but never for standalone-to-monorepo conversion. The migration tooling may need enhancements.
- **Changelog attribution:** How to split unified changelog entries across releasables without losing history.
- **npm target:** Only selfdoc has the npm target. The npm wrapper (`bin/cli.js`) calls `python3 -m selfdoc`. Does it also need to support `python3 -m selfblog`?

## rlsbl Call-Site Flip

When the monorepo conversion is complete, external consumers (rlsbl post-release hooks, CI workflows) need to switch from `selfdoc` to `selfblog` for blog-related operations:

| Current call site | Current command | Target command |
|---|---|---|
| `publish.py:65` (rlsbl post-release hook) | `selfdoc post generate --from-release` | `selfblog post generate --from-release` |
| Guard scripts | Require `selfdoc` | Require `selfblog` for post operations |
| Assembly workflow | `selfdoc build --target posts` | `selfblog build --target posts` |
| Assembly workflow | `selfdoc assembly generate-shared` | `selfblog assembly generate-shared` |

Commands that stay with `selfdoc`:
- `selfdoc gen` (generates docs pages from source)
- `selfdoc check` (validates directives and coverage)
- `selfdoc build` (full documentation build)
- `selfdoc deploy` (deploys to hosting provider)

For unified configs that have both docs and blog content, `selfdoc check` should detect blog-only issues and hard-error with a message directing users to `selfblog check` (when that command exists).

## Assembly Workflow Update

The per-line assembly workflow (`.github/workflows/deploy.yml` in the assembly repo) needs these changes:

### Install step

```yaml
- name: Install tools
  run: pip install selfdoc selfblog 'pagefind[bin]'
```

### Build step

```yaml
- name: Build documentation
  run: |
    cd "source/$SLUG"
    if [ "$SCOPE" = "posts" ]; then
      selfblog build --target posts --no-auto-commit
    else
      selfdoc build --no-auto-commit
    fi
```

### Shared elements step

```yaml
- name: Generate shared elements
  run: selfblog assembly generate-shared --site-dir site/ --manifests-dir manifests/ --docs-base '' $PORTFOLIO_FLAG
```

Full project builds stay `selfdoc`. Posts-only builds and `generate-shared` move to `selfblog`.
