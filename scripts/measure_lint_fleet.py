#!/usr/bin/env python3
"""Measure what two SEO rule changes do to every selfdoc project on this machine.

Read-only. Walks a projects root, and for each directory carrying a
``selfdoc.json`` runs the SEO lint pass over that project's docs templates
twice: once as the rules stand now, and once with the two pre-change
behaviors restored --

- SEO007 skipped generated ``cli-*`` pages entirely (a per-page-type
  exemption that no longer exists).
- SEO008 counted any token containing a digit as a statistic, including
  version strings and calendar years.

The difference is what the fleet will see the first time it upgrades. The
script never writes to a project it measures.

Usage:
    python scripts/measure_lint_fleet.py [PROJECTS_ROOT]
"""

import os
import shutil
import sys
import tempfile

from selfdoc_core.fleet import (
    load_docs_bodies,
    load_project_config,
    project_dirs,
)


def _was_seo007_exempt(all_docs, rel_path):
    """True when the removed per-page-type exemption would have hidden this page."""
    entry = all_docs.get(rel_path)
    if entry is None:
        return False
    metadata = entry[0]
    return metadata.get("generated") is True and rel_path.startswith("cli-")


def measure_project(project_dir, scratch_dir):
    """Return the SEO007/SEO008 deltas for one project.

    Args:
        project_dir: Directory holding a ``selfdoc.json``.
        scratch_dir: Where a sanitized config copy may be written.

    Returns:
        A dict with the per-project counts, or raises if the project cannot
        be loaded or linted (the caller lists those separately).
    """
    import selfdoc.check as check_mod

    config, sanitized = load_project_config(project_dir, scratch_dir)
    if config is None:
        raise RuntimeError("no selfdoc.json")
    docs_dir = os.path.join(project_dir, config.get("docs", "docs/"))
    if not os.path.isdir(docs_dir):
        raise RuntimeError(f"docs directory not found: {docs_dir}")

    all_docs = load_docs_bodies(docs_dir)
    if not all_docs:
        raise RuntimeError("no markdown templates")

    cwd = os.getcwd()
    os.chdir(project_dir)
    try:
        current = check_mod._run_lints(all_docs, docs_dir, None, config)
        original = check_mod.counts_as_statistic
        check_mod.counts_as_statistic = lambda w: any(c.isdigit() for c in w)
        try:
            before = check_mod._run_lints(all_docs, docs_dir, None, config)
        finally:
            check_mod.counts_as_statistic = original
    finally:
        os.chdir(cwd)

    seo007 = [r for r in current if r.code == "SEO007"]
    new_seo007 = [r for r in seo007 if _was_seo007_exempt(all_docs, r.file)]
    seo008_now = {r.file for r in current if r.code == "SEO008"}
    seo008_before = {r.file for r in before if r.code == "SEO008"}

    return {
        "sanitized": sanitized,
        "pages": len(all_docs),
        "seo007_total": len(seo007),
        "seo007_new": len(new_seo007),
        "seo007_new_files": sorted({r.file for r in new_seo007}),
        "seo008_before": len(seo008_before),
        "seo008_now": len(seo008_now),
        "seo008_newly_failing": sorted(seo008_now - seo008_before),
        "seo008_no_longer_failing": sorted(seo008_before - seo008_now),
    }


def main(argv):
    """Measure every project under the given root and print a summary table."""
    root = argv[1] if len(argv) > 1 else os.path.expanduser("~/Projects")
    projects = [os.path.basename(path) for path in project_dirs(root)]

    scratch_dir = tempfile.mkdtemp(prefix="selfdoc-fleet-measure-")
    measured = []
    skipped = []
    try:
        for name in projects:
            try:
                measured.append(
                    (name, measure_project(os.path.join(root, name), scratch_dir))
                )
            except Exception as exc:  # noqa: BLE001 -- reported, never fatal
                skipped.append((name, f"{type(exc).__name__}: {exc}"))
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)

    print(f"{'project':24} {'pages':>5} {'SEO007':>7} {'new':>4} "
          f"{'SEO008 was':>10} {'now':>4}  config")
    for name, m in measured:
        note = "sanitized" if m["sanitized"] else ""
        print(f"{name:24} {m['pages']:5} {m['seo007_total']:7} "
              f"{m['seo007_new']:4} {m['seo008_before']:10} {m['seo008_now']:4}"
              f"  {note}")

    for name, m in measured:
        if m["seo007_new_files"] or m["seo008_newly_failing"]:
            print(f"\n{name}:")
            if m["seo007_new_files"]:
                print(f"  SEO007 newly warning on: {', '.join(m['seo007_new_files'])}")
            if m["seo008_newly_failing"]:
                print(f"  SEO008 newly warning on: {', '.join(m['seo008_newly_failing'])}")
            if m["seo008_no_longer_failing"]:
                print("  SEO008 no longer warning on: "
                      f"{', '.join(m['seo008_no_longer_failing'])}")

    if skipped:
        print("\nnot measured:")
        for name, reason in skipped:
            print(f"  {name}: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
