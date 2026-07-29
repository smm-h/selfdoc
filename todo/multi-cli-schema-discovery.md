# Multi-CLI schema discovery in gen.py

## Problem

`gen.py` only discovers CLI schemas at the project root (`.strictcli/schema.json`). In monorepo projects with multiple CLI packages, each sub-package has its own schema file, but `gen.py` only reads the root one. This means only one CLI's reference pages get auto-generated.

## Context

The function `discover_schema_dirs()` already exists in `selfdoc/strictcli_support.py` and is used by the `table-commands` directive in `content.py`. But `gen.py` (specifically `_generate_cli_pages()` around line 580) only calls `uses_strictcli()` and `extract_cli_structure()` which hardcode the root path.

## Solution

Have `gen.py` call `discover_schema_dirs()` to find all schema files in the project tree. Generate namespaced CLI pages for each discovered schema (e.g., prefixed by the sub-package directory name to avoid filename collisions).

## Impact

Without this, monorepo CLIs require manually creating CLI reference pages that don't stay in sync with schema changes.

## Effort estimate

Medium -- the discovery function exists, the main work is namespace prefixing in page generation and handling multiple schemas in the gen pipeline.
