# selfdoc scans .venv directories inside source paths

## Problem

When a selfdoc source path like `games/cubeconnect/` contains a `.venv/` directory, selfdoc generates doc pages for every Python package in site-packages (anyio, asyncpg, websockets, etc.). This produces hundreds of spurious doc pages and crashes the coverage check.

## Reproduction

In gamehome, `selfdoc.json` doesn't list `games/cubeconnect/` as a source path, but selfdoc still finds it because the cubeconnect game has Python source files and a `.venv/`. The `selfdoc gen` step during `rlsbl release run` generates 486 doc files for third-party packages.

## Expected behavior

selfdoc should always skip `.venv/`, `node_modules/`, `__pycache__/`, `.git/`, and similar well-known non-source directories, regardless of whether they're inside a configured source path.

## Context

Hit during gamehome 0.2.0 release. The release is blocked because selfdoc generates hundreds of pages for vendored dependencies, which then fail coverage checks.
