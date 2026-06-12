# Read version from primary manifest instead of selfdoc.json

## Context

selfdoc.json currently maintains its own `version` field that must be kept in sync with the project's primary version source (pyproject.toml, package.json, etc.). This creates a version drift risk -- if the primary manifest is bumped but selfdoc.json is not, the documentation version is wrong.

rlsbl previously handled this via DocsTarget, which detected selfdoc.json and bumped it during releases. As of rlsbl's Phase 10, DocsTarget has been removed and the selfdoc.json version bump is inlined directly in the release flow. This works but is a workaround for the real problem: selfdoc should not need its own version copy.

## Problem

- Dual-source-of-truth: the project version lives in the primary manifest AND in selfdoc.json.
- Every release tool that bumps versions must know about selfdoc.json as a special case.
- If a project is released without rlsbl (manual tag, different CI), selfdoc.json drifts silently.

## Proposed solution

selfdoc should read the project version from the primary manifest file at build/gen/check time, not from selfdoc.json. The detection order could be:

1. pyproject.toml (`[project].version`)
2. package.json (`version`)
3. Cargo.toml (`[package].version`)
4. VERSION file
5. Fall back to selfdoc.json `version` field (for projects with no standard manifest)

The `version` field in selfdoc.json would become optional/deprecated -- only needed if none of the standard manifests exist. The `versions` array entries would still be managed by selfdoc itself (they track documentation versioning, not project versioning).

## Affected files

- selfdoc's config loader (wherever selfdoc.json is parsed)
- selfdoc's version resolution logic
- Documentation referencing the version field in selfdoc.json

## Effort

Small -- the manifest parsers are straightforward (JSON for package.json, TOML for pyproject.toml/Cargo.toml, plain text for VERSION). The main work is deciding the detection order and handling edge cases (monorepos, workspaces).
