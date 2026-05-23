---
title: rlsbl Integration
description: "How selfdoc and rlsbl work together: auto-commit preference chain, changelog detection, docs checks during release, and post-release deploy."
nav_group: "Guides"
nav_order: 11
---

# rlsbl Integration

selfdoc and rlsbl have a bidirectional relationship. selfdoc is aware of rlsbl's commit tooling and changelog conventions, while rlsbl can run selfdoc checks during release and trigger builds and deploys post-release. If both tools are present in a project, they cooperate automatically.

## selfdoc Side

### Auto-commit preference chain

When selfdoc writes files such as hash updates, generated pages, or root files, it auto-commits them using the best available commit tool on the system PATH. This 3-level preference chain ensures selfdoc integrates cleanly with concurrency-safe tools when available and falls back gracefully otherwise:

1. **rlsbl** -- if `rlsbl` is on `PATH`, use `rlsbl commit` (concurrency-safe, changelog-aware).
2. **safegit** -- if `safegit` is on `PATH`, use `safegit commit` (concurrency-safe).
3. **git** -- fall back to plain `git add` + `git commit`.

This means selfdoc plays nicely with rlsbl-managed repos without any configuration. The auto-commit is guarded by the `SELFDOC_AUTO_COMMIT` environment variable to prevent re-entrant loops (e.g., if a git hook triggers selfdoc).

### Changelog auto-detection

When selfdoc builds a site, it looks for `CHANGELOG.md` in the project root. If found, the changelog is included as a documentation page automatically. In rlsbl-managed projects, `CHANGELOG.md` is generated from JSONL changelog entries, so the docs site always reflects the latest release notes without manual copying.

### Version from manifest

selfdoc reads the project version from the language-specific manifest file (`pyproject.toml` for Python, `package.json` for npm, `go.mod` for Go). In rlsbl-managed projects, this version is bumped by `rlsbl release`, so the docs site automatically shows the current version in navigation and search metadata.

## rlsbl Side

### Docs checks during release

If a project has a `selfdoc.json` in its root, rlsbl can run `selfdoc check` as part of its pre-release validation. This catches broken directives, coverage regressions, and SEO errors before the release is tagged. The check runs alongside rlsbl's built-in tests and lint.

> [!TIP]
> Add `selfdoc check` to your `.rlsbl/hooks/pre-checks.sh` to enforce documentation quality on every release. The pre-checks hook runs before tests and lint, so doc issues are caught early.

### Post-release build and deploy

The rlsbl post-release hook is the natural place to rebuild and deploy documentation after a release is published and tagged. This runs after the version bump commit, GitHub Release creation, and tag push are all complete, so the docs reflect the new version. A typical `.rlsbl/hooks/post-release.sh` for a selfdoc project:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Source credentials for Cloudflare deploy
source ~/Projects/.env

# Build the documentation site
selfdoc build

# Deploy to Cloudflare Pages
selfdoc deploy
```

This runs after rlsbl has pushed the release tag and created the GitHub Release. Even if the deploy fails, it does not affect the release itself (post-release hooks are non-fatal).

### Skip flag

If you need to release without running docs checks or builds, rlsbl provides `--skip-docs` to bypass the documentation step. This is useful for hotfix releases where the docs have not changed.

## Credential Handling

For Cloudflare Pages deploys, selfdoc reads 2 environment variables (`CF_PAGES_API_TOKEN` and `CF_ACCOUNT_ID`). These credentials are not stored in the repository or in GitHub secrets since the deploy runs locally inside the post-release hook. In rlsbl-managed projects, the hook sources them from the shared environment file:

```bash
# In post-release.sh
source ~/Projects/.env
selfdoc deploy
```

No GitHub secrets are needed for this flow -- the deploy runs locally in the hook, not in CI. For GitHub Pages deploys, no credentials are needed since the deploy is handled by the CI workflow.

## Setting It Up

If your project already has both `selfdoc.json` and `.rlsbl/`, the integration is automatic since the tools detect each other at runtime. For new projects, the setup takes 4 steps: initialize selfdoc, add the docs check hook, configure post-release deploy, and set the deploy provider in your config. Here is the minimal setup:

1. **Initialize selfdoc** in an rlsbl-managed project:

```bash
selfdoc init
```

2. **Add docs check to pre-checks** (optional but recommended):

```bash
echo 'selfdoc check' >> .rlsbl/hooks/pre-checks.sh
```

3. **Add build and deploy to post-release** (for auto-deploy):

```bash
cat >> .rlsbl/hooks/post-release.sh << 'EOF'
source ~/Projects/.env
selfdoc build
selfdoc deploy
EOF
```

4. **Configure deploy provider** in `selfdoc.json`:

```json
{
  "deploy": {
    "provider": "cloudflare-pages",
    "project": "my-docs-site"
  }
}
```

That is it. On the next `rlsbl release`, docs are checked before release and rebuilt and deployed after.

> [!WARNING]
> Make sure the post-release hook has `source ~/Projects/.env` before `selfdoc deploy`. Without it, the Cloudflare API token is missing and the deploy will fail silently (post-release hooks are non-fatal).

Next: [Atom Feeds](feeds/) -->
