# selfblog assembly retire <slug>

## Context

The assembly tooling is strictly additive: `push_files_to_repo` cannot delete, and no
subcommand removes a project from the unified site. When a project is retired, its section
lingers at docs.smmh.dev/<slug>/ (one retired project's stale section is live today), its
manifest stays in projects.json, and shared elements keep listing it.

## Problem

Retirement currently has no sanctioned completion: the fleet-side cleanup (topology links,
portfolio card) is doable, but the deployed site itself cannot be corrected without
out-of-band hand-edits to the assembly repo.

## Solution

`selfblog assembly retire <slug>`: delete the slug subtree + its manifest from the assembly
repo (Git API, single commit), regenerate shared elements (nav, blog index, sitemap,
projects.json), redeploy. Consequential command; `--dry-run` renders the would-do plan.
Consider a `--tombstone` variant that leaves a one-page retirement notice at the slug root.

## Effort

Small-medium (one selfblog command + tests; the deletion path through the Git API is the
new piece).
