#!/usr/bin/env python3
"""Regenerate the assembly repo's tool-owned artifacts and push them.

The assembly repo (``assembly.repo``) holds two files that selfblog
generates rather than a human writing them: the deploy workflow and the
redirect worker that the deployed site serves.  ``assembly init`` writes
them once at creation time; when the generators change, an existing
assembly repo has to be brought back in sync -- that is what this does.

Both files are rendered from the current project's ``selfdoc.json``, so
the assembly repo never carries values that disagree with the config.

Usage::

    python3 scripts/push_assembly_artifacts.py --dry-run
    python3 scripts/push_assembly_artifacts.py
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selfblog.assembly import (  # noqa: E402
    generate_workflow_yaml,
    generate_worker_js,
    push_files_to_repo,
)
from selfdoc_core.config import load_config  # noqa: E402


def render_artifacts(config: dict) -> dict[str, str]:
    """Return the assembly-repo path -> content map for the tool-owned files."""
    assembly = config.get("assembly") or {}
    topology = config.get("topology") or {}

    repo = assembly.get("repo")
    pages_project = assembly.get("pages_project")
    canonical_base = topology.get("docs_base")
    legacy_blog_host = topology.get("legacy_blog_host") or ""
    portfolio_canonical = assembly.get("portfolio_canonical") or ""

    missing = [
        name for name, value in (
            ("assembly.repo", repo),
            ("assembly.pages_project", pages_project),
            ("topology.docs_base", canonical_base),
        ) if not value
    ]
    if missing:
        raise SystemExit(
            f"error: selfdoc.json is missing {', '.join(missing)}"
        )

    return {
        ".github/workflows/deploy.yml": generate_workflow_yaml(
            pages_project, canonical_base, legacy_blog_host,
            portfolio_canonical,
        ),
        "site/_worker.js": generate_worker_js(canonical_base, legacy_blog_host),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the rendered artifacts instead of pushing them",
    )
    parser.add_argument(
        "--project-dir", default=".",
        help="directory containing selfdoc.json (default: cwd)",
    )
    args = parser.parse_args()

    config = load_config(args.project_dir)
    if config is None:
        raise SystemExit(f"error: no selfdoc.json in {args.project_dir!r}")

    repo = (config.get("assembly") or {}).get("repo")
    files = render_artifacts(config)

    if args.dry_run:
        for path, content in files.items():
            print(f"--- {repo}:{path}")
            print(content)
        return 0

    sha = push_files_to_repo(
        repo, files, "assembly: regenerate tool-owned artifacts from config",
    )
    print(f"Pushed {len(files)} file(s) to {repo} ({sha})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
