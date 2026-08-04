#!/usr/bin/env bash
# Pre-checks hook for the selfdoc releasable (user-owned).
#
# The selfdoc docs site lives at the REPO ROOT (selfdoc.json, docs/),
# while the selfdoc package/member dir is selfdoc/. rlsbl's built-in
# selfdoc.json version bump and selfdoc gen/check steps only look in the
# member dir, so this hook performs the root-level equivalents:
#
#   1. Sync root selfdoc.json "version" to the version being released.
#   2. Regenerate docs (selfdoc gen) so the release ships fresh docs.
#   3. Run selfdoc check as a hard freshness/validity gate.
#
# Files modified here are picked up by rlsbl's hook-generated-file
# snapshot and included in the release commit.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "pre-checks: syncing selfdoc.json version to $RLSBL_VERSION"
python3 - "$RLSBL_VERSION" <<'PY'
import json, os, sys, tempfile

version = sys.argv[1]
with open("selfdoc.json", "r", encoding="utf-8") as f:
    config = json.load(f)
config["version"] = version

# Also sync the last entry in the versions array (single-version site)
if "versions" in config and config["versions"]:
    config["versions"][-1]["version"] = version

fd, tmp = tempfile.mkstemp(dir=".", prefix=".selfdoc.json.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
    f.write("\n")
os.replace(tmp, "selfdoc.json")
PY

# Both run bare. strictcli prompts only for commands that declare themselves
# `consequential`, and neither gen nor check does -- regenerating and
# validating docs in the working tree is ordinary, git-recoverable work. This
# hook has no TTY, so a gate on either would abort every release.
echo "pre-checks: regenerating docs (selfdoc gen)"
uv run selfdoc gen --no-auto-commit

echo "pre-checks: validating docs (selfdoc check)"
uv run selfdoc check
