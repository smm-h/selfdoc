#!/usr/bin/env python3
"""Point every roster project's selfdoc.json base_url at its unified-site URL.

Usage: scripts/sweep-base-url.py --dry-run | --apply [--skip slug,slug]

The unified site serves each project at <canonical base>/<slug>/; the
retired per-project hosts (<name>.smmh.dev, docs.smmh.dev/<name>) only
redirect there or no longer resolve. --dry-run prints every change it would
make and asserts one base_url line per file. --apply rewrites the line,
regenerates the project's docs with bare `selfdoc gen` (which commits its
own output), commits selfdoc.json with safegit, and adds a user-facing
changelog entry.
"""

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

CACHE_REPO = "smm-h/selfdoc-cache"
CANONICAL_BASE = "https://smmh.dev"
PROJECTS_ROOT = Path.home() / "Projects"
BASE_URL_LINE = re.compile(r'^(\s*"base_url":\s*)"([^"]*)"(,?)\s*$', re.M)


def roster_slugs() -> tuple[str, list[str]]:
    raw = subprocess.run(
        ["gh", "api", f"repos/{CACHE_REPO}/contents/roster.toml", "--jq", ".content"],
        check=True, capture_output=True, text=True,
    ).stdout
    text = base64.b64decode(raw).decode()
    home = re.search(r'^home = "(.*)"$', text, re.M).group(1)
    slugs = re.findall(r'^slug = "(.*)"$', text, re.M)
    return home, slugs


def checkout_for(slug: str) -> Path | None:
    for candidate in PROJECTS_ROOT.iterdir():
        if candidate.name.lower() == slug and (candidate / ".git").is_dir():
            return candidate
    return None


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] not in ("--dry-run", "--apply"):
        print(__doc__, file=sys.stderr)
        return 2
    apply = args[0] == "--apply"
    skip = set(args[2].split(",")) if len(args) > 2 and args[1] == "--skip" else set()

    home, slugs = roster_slugs()
    planned = 0
    for slug in slugs:
        if slug == home or slug in skip:
            print(f"{slug}: skipped")
            continue
        checkout = checkout_for(slug)
        if checkout is None:
            print(f"{slug}: no local checkout; skipped", file=sys.stderr)
            continue
        manifest = checkout / "selfdoc.json"
        text = manifest.read_text()
        matches = BASE_URL_LINE.findall(text)
        if len(matches) != 1:
            print(f"{slug}: expected one base_url line, found {len(matches)}; skipped", file=sys.stderr)
            continue
        current = matches[0][1]
        wanted = f"{CANONICAL_BASE}/{slug}"
        if current == wanted:
            print(f"{slug}: base_url already {wanted}")
            continue
        planned += 1
        print(f"{slug}: {current} -> {wanted}")
        if not apply:
            continue
        new_text, count = BASE_URL_LINE.subn(lambda m: f'{m.group(1)}"{wanted}"{m.group(3)}', text, count=1)
        assert count == 1
        manifest.write_text(new_text)
        json.loads(new_text)
        run(["selfdoc", "gen"], checkout)
        run(["safegit", "commit", "-m", "selfdoc.json: base_url is the unified-site address", "--", "selfdoc.json"], checkout)
        run([
            "rlsbl", "changelog", "add", "--commits", "HEAD",
            "--description",
            f"**Documentation links point at the unified site.** The declared docs base was the retired per-project host; it is `{wanted}/` now, so generated sitemaps, feeds and llms.txt name the address that serves the pages.",
            "--type", "fix",
        ], checkout)
    print(f"\n{planned} project(s) {'changed' if apply else 'to change'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
