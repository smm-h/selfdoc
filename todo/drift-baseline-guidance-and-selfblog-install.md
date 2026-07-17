# DRIFT001 should point at `baseline accept`; install selfblog on this machine

Two related items discovered while resolving a failed release in a consumer project.

## Item 1: DRIFT001 resolution path is a trap

### Context

`selfdoc gen` advances the `content` and `description` baselines for a page, but NOT the `source_docstring` baseline (gen hashes without source directives). Clearing a `DRIFT001` (source docstrings changed but page description not updated) on a source-derived ref page therefore requires the separate, deliberate `selfdoc baseline accept <page>` step. This split is arguably intentional — docstring drift should require a reviewed acceptance rather than being auto-cleared by regeneration.

### Problem

The workflow is non-obvious and cost a consumer project a failed release attempt plus a debugging detour: the natural response to DRIFT001 is "update the description and run `selfdoc gen`", which clears STALE001 but leaves DRIFT001 standing, because gen advanced the description baseline to the new text while the source_docstring baseline stayed stale. Nothing in the error output points at `baseline accept`. An agent (or human) has to reverse-engineer the baseline mechanics to find the fix.

### Solutions

1. **Improve the DRIFT001 error message (recommended, minimal).** Append remediation guidance: "after reviewing the page against the changed docstrings, run `selfdoc baseline accept <page>` to accept". Pros: one-line change, preserves the deliberate-acceptance design. Cons: none significant.
2. **Document the baseline model.** A docs section explaining which baselines `gen` advances vs which require `accept`, and the intended DRIFT001 workflow. Pros: helps all baseline-related confusion, not just DRIFT001. Cons: docs alone are easy to miss at error time — best combined with option 1.
3. **Behavior change: have `gen` advance the source_docstring baseline too.** Pros: DRIFT001 becomes self-healing via the common workflow. Cons: destroys the reviewed-acceptance property — docstring drift would be silently accepted by any regeneration, which is likely the opposite of the check's intent. Not recommended unless the acceptance property is considered dead weight.

Options 1 + 2 together are the most correct outcome.

## Item 2: selfblog is not installed on this machine

### Context

selfblog (this monorepo's blog/assembly package, published on PyPI and npm) provides `selfblog assembly push`, which dispatches a `repository_dispatch` event to the documentation-assembly repo to rebuild a project's section of the unified multi-project docs site (`selfblog/assembly.py`, `assembly_push`). Roughly ten consumer projects carry a post-release hook line invoking it, and their `selfdoc.json` files actively configure `assembly.repo` — the capability is intended and wired, not abandoned.

### Problem

`selfblog` is not on PATH on this machine, so every consumer release logs `selfblog: command not found` / "Warning: assembly push failed (non-fatal)" and the unified docs site silently stops receiving updates from released projects. This is a missing install masked by a non-fatal guard — silent degradation of a configured capability.

### Solution

Install selfblog on this machine as an editable install from this monorepo, per the local-projects convention:

```bash
pip install -e /home/m/Projects/selfdoc/selfblog --break-system-packages
```

Then verify: `selfblog --help` resolves, and `selfblog assembly status` (or equivalent) works against a configured consumer. Pros: restores the assembly push for every consumer at once; editable install picks up source changes immediately. Cons: none — this is the standard convention for local packages.

Consider also whether the selfdoc/selfblog docs should list selfblog as a required install for machines that release selfdoc-configured projects, so the gap cannot silently reappear on a fresh machine.

## Affected files

- Item 1: the check implementation emitting DRIFT001 (drift check in the check/lint module), docs pages covering baselines/checks
- Item 2: no repo files strictly required (machine-level install); optionally install/setup documentation

## Effort

Item 1: small (error-message string plus a docs section). Item 2: minutes (one install command plus verification).
