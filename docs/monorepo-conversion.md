---
title: Monorepo Conversion Plan
description: "Converting selfdoc into three releasables: workspace setup, changelog migration, CI scaffolding, the rlsbl call-site flip and the assembly workflow update."
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

The existing `.rlsbl/changes/*.jsonl` files contain the full changelog history for the unified package, covering all three components in a single stream. During conversion, each entry needs to be attributed to the appropriate releasable based on which source files the entry's commits touched, so that each releasable carries only its own history forward:

- Most entries are about selfdoc CLI or core functionality
- Blog/assembly entries belong to selfblog
- Core engine entries belong to selfdoc_core

### 4. Per-package pyproject.toml activation

Currently the per-package `pyproject.toml` files in `selfblog/` and `selfdoc_core/` are inert documentation that describe the intended package metadata but are not used by the build system. Activating them means switching from a single root-level build to independent per-package builds, each producing its own versioned wheel:

- Remove `[tool.hatch.build.targets.wheel] packages` from root `pyproject.toml`
- Each package gets its own build, its own version, its own wheel
- Cross-dependencies use registry versions (not path sources)

### 5. CI/CD scaffolding

Each releasable needs its own CI publish workflow so that releases are independent. Running `rlsbl scaffold` in monorepo mode generates per-releasable GitHub Actions workflows, each configured with the correct build target, registry credentials, and test commands for that specific package.

## Open Questions

- **First-of-kind:** `rlsbl monorepo` has been used for fresh monorepos but never for standalone-to-monorepo conversion. The migration tooling may need enhancements.
- **Changelog attribution:** How to split unified changelog entries across releasables without losing history.
- **npm target:** Only selfdoc has the npm target. The npm wrapper (`bin/cli.js`) calls `python3 -m selfdoc`. Does it also need to support `python3 -m selfblog`?

## rlsbl Call-Site Flip

When the monorepo conversion is complete, external consumers such as rlsbl post-release hooks and CI workflows need to update their command invocations. Blog-related operations that currently use the `selfdoc` CLI must switch to the `selfblog` CLI, since the blog functionality moves to its own independently versioned package:

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

The assembly workflow at `.github/workflows/deploy.yml` in the assembly repo needs to install both packages and route build commands to the correct CLI. Full documentation builds remain with `selfdoc`, while posts-only builds and shared element generation move to `selfblog`. The specific changes are listed below:

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
  run: >
    selfblog assembly generate-shared --site-dir site/ --manifests-dir manifests/
    --docs-base '' --canonical-base "$DOCS_BASE" --home-slug "$HOME_SLUG"
```

When this plan was written the step also carried a `--portfolio-file` flag holding a hand-written HTML front page. That flag is gone: the site's front page is the roster's declared `home` project, named by `--home-slug`, whose own pages are emitted at the site root. `--canonical-base` is required and has no default.

Full project builds stay `selfdoc`. Posts-only builds and `generate-shared` move to `selfblog`.
