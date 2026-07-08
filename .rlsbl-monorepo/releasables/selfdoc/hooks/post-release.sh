#!/usr/bin/env bash
# Post-release hook for the selfdoc releasable. Runs after a successful
# release (non-fatal). Environment: RLSBL_VERSION is the released version.
#
# The selfdoc docs site lives at the REPO ROOT (selfdoc.json, docs/),
# while the member dir is selfdoc/. The docs deploy therefore happens
# here instead of a cloudflare-pages pipeline entry in the member config:
# pipeline publishes run with cwd = member dir, where selfdoc deploy
# cannot find selfdoc.json.

set -euo pipefail

echo "Post-release: v$RLSBL_VERSION"

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Deploy secrets (CF_ACCOUNT_ID, CF_PAGES_API_TOKEN) come from the shared
# env file; rlsbl only sources it for pipeline env validation, not hooks.
if [ -f "$HOME/Projects/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$HOME/Projects/.env"
  set +a
fi

# Deploy docs to Cloudflare Pages
if [ -f selfdoc.json ]; then
  echo "Deploying docs to Cloudflare Pages..."
  uv run selfdoc deploy || echo "Warning: docs deploy failed (non-fatal); re-run 'uv run selfdoc deploy' manually"
fi

# Push to assembly for unified documentation site
if [ -f selfdoc.json ]; then
  if python3 -c "import json; c=json.load(open('selfdoc.json')); exit(0 if c.get('assembly') or (c.get('topology') or {}).get('assembly') else 1)" 2>/dev/null; then
    echo "Pushing to documentation assembly..."
    uv run selfdoc assembly push || echo "Warning: assembly push failed (non-fatal)"
  fi
fi
