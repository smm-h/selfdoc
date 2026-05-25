# strictcli dependency: stale pin and local override

## Problem

Two issues in `pyproject.toml`:

1. The strictcli dependency is pinned to `>=0.7.0`. Per the project policy ("always use unpinned dependencies"), it should be just `"strictcli"` with no version constraint. The current pin is functional (resolves to 0.8.3) but inconsistent with the policy.

2. A `[tool.uv.sources]` section still has `strictcli = { path = "../strictcli/python", editable = true }` (line 22-23). This was a development override for when strictcli was being actively developed locally. It should be removed now that strictcli 0.8.2+ is published on PyPI, so the project installs from the registry like all other consumers.

## What's needed

- Remove the version floor from the strictcli dependency (change `>=0.7.0` to just `strictcli`)
- Remove the `[tool.uv.sources]` strictcli override
- Verify the project still installs and works with the PyPI version
