#!/usr/bin/env python3
"""Fleet flip: rewrite post-release hooks from `selfdoc assembly push` to
`selfblog assembly push`.

The assembly push command moved from the selfdoc CLI to the selfblog CLI
(selfdoc monorepo split). This script enumerates every post-release hook in
the fleet that dispatches an assembly rebuild and rewrites the CLI name.

Dry-run by default; pass --fix to apply edits. The script never commits --
commits are the caller's responsibility, per-repo.

Usage:
    ./scripts/fleet_flip_selfblog.py            # dry run: report what would change
    ./scripts/fleet_flip_selfblog.py --fix      # apply edits in place
"""

import argparse
import sys
from pathlib import Path

PROJECTS = Path.home() / "Projects"

OLD = "selfdoc assembly push"
NEW = "selfblog assembly push"

# Standalone repos: hook lives at <repo>/.rlsbl/hooks/post-release.sh
STANDALONE_REPOS = [
    "claudestream",
    "claudewheel",
    "go-toml-edit",
    "howmuchleft",
    "migrable",
    "pgdesign",
    "predraw",
    "safegit",
    "saferm",
    "wesktop",
]

# Monorepo releasables: hook lives at
# <repo>/.rlsbl-monorepo/releasables/<name>/hooks/post-release.sh
# selfdoc's own hook moved here in its monorepo conversion.
RELEASABLE_HOOKS = [
    ("orxtra", "orxtra"),
    ("strictcli", "strictcli"),
    ("strictcli", "go-strictcli"),
    ("selfdoc", "selfdoc"),
]


def hook_paths() -> list[Path]:
    paths = [
        PROJECTS / repo / ".rlsbl" / "hooks" / "post-release.sh"
        for repo in STANDALONE_REPOS
    ]
    paths += [
        PROJECTS / repo / ".rlsbl-monorepo" / "releasables" / name / "hooks" / "post-release.sh"
        for repo, name in RELEASABLE_HOOKS
    ]
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="apply edits in place (default is dry run)",
    )
    args = parser.parse_args()

    missing = []
    already = []
    flipped = []

    for path in hook_paths():
        if not path.is_file():
            missing.append(path)
            continue
        text = path.read_text()
        if OLD not in text:
            if NEW in text:
                already.append(path)
            else:
                # Hook exists but has neither string -- treat as an error so
                # nothing silently escapes the flip.
                missing.append(path)
            continue
        if args.fix:
            path.write_text(text.replace(OLD, NEW))
        flipped.append(path)

    verb = "flipped" if args.fix else "would flip"
    for path in flipped:
        print(f"{verb}: {path}")
    for path in already:
        print(f"already flipped: {path}")
    for path in missing:
        print(f"ERROR: missing hook or no assembly-push line: {path}")

    print(f"\n{len(flipped)} {verb}, {len(already)} already done, {len(missing)} errors")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
