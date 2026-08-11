"""Check helpers for selfblog: post validation and unified project checks.

Post checks (POST001-POST005) and the unified multi-project check moved
here from selfdoc.check.  ``check_posts`` is registered with
selfdoc_core as the post-check hook, so ``selfdoc check`` can run post
validation without importing selfblog.

Imports from selfdoc are deferred inside functions: selfdoc currently
imports selfblog (temporary delegation shims until the fleet flip), so
top-level imports would be circular.
"""

from __future__ import annotations

import dataclasses
import os

from selfblog.posts import discover_posts


def check_posts(config, dir_path):
    """Check blog posts for validation errors (POST001-POST005).

    Returns a list of ``selfdoc_core.lints.LintResult`` objects (empty when
    posts are absent or valid).  Registered with selfdoc_core as the
    post-check hook.  The POST severities come from the lint registry, so a
    posts-only install never needs the selfdoc package to run this.
    """
    from selfdoc_core.lints import LintResult

    posts_config = config.get("posts") or {}
    posts_dir_rel = posts_config.get("dir", "")
    if not posts_dir_rel:
        return []

    posts_dir = os.path.join(dir_path, posts_dir_rel)
    if not os.path.isdir(posts_dir):
        return []

    manifest_path = os.path.join(dir_path, ".selfdoc", "manifest.json")

    try:
        discover_posts(posts_dir, manifest_path=manifest_path)
    except RuntimeError as exc:
        msg = str(exc)
        if "'title' is required" in msg:
            code = "POST002"
        elif "'date' is required" in msg:
            code = "POST001"
        elif "must be YYYY-MM-DD" in msg:
            code = "POST003"
        elif "Duplicate slug" in msg:
            code = "POST004"
        elif "Slug immutability violation" in msg:
            code = "POST005"
        else:
            code = "POST001"  # fallback
        return [LintResult(
            file=posts_dir_rel,
            line=None,
            code=code,
            message=msg,
        )]

    return []


def check_unified(dir_path=".", config=None, dry_run=False):
    """Check all constituent projects in a unified build.

    Iterates over each project in the ``unified`` config section,
    loads its own selfdoc.json, and runs check_docs on it. Errors
    are prefixed with the project slug for clear attribution.

    Also checks the docs-site's own content (the common pages).

    Args:
        dir_path: The docs-site's project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc.json).
        dry_run: If True, report staleness without writing hashes to disk.

    Returns:
        CheckResult with aggregated results from all projects.
    """
    try:
        from selfdoc.check import CheckResult, CoverageStats, check_docs
    except ImportError as exc:
        raise RuntimeError(
            "selfblog unified checks require the selfdoc package. "
            "Install it with: pip install selfdoc"
        ) from exc
    from selfdoc_core.config import load_config
    from selfdoc_core.lints import LintResult

    from selfblog.unified import _project_slug, _resolve_project_path

    if config is None:
        config = load_config(dir_path)
    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    unified_config = config.get("unified")
    if unified_config is None:
        raise RuntimeError("No 'unified' section in selfdoc.json")

    aggregate = CheckResult()

    # Check each constituent project
    for project_entry in unified_config["projects"]:
        slug = _project_slug(project_entry)
        project_path = _resolve_project_path(project_entry, dir_path)
        proj_config = load_config(project_path)
        if proj_config is None:
            aggregate.lints.append(LintResult(
                file=f"[{slug}]",
                line=None,
                code="UNIFIED001",
                message=f"No selfdoc.json in project '{slug}'",
            ))
            continue

        try:
            proj_result = check_docs(project_path, config=proj_config, dry_run=dry_run)
        except RuntimeError as exc:
            aggregate.lints.append(LintResult(
                file=f"[{slug}]",
                line=None,
                code="UNIFIED002",
                message=str(exc),
            ))
            continue

        # Prefix directive results with project slug
        for dr in proj_result.directive_results:
            dr.file = f"[{slug}] {dr.file}"
            aggregate.directive_results.append(dr)

        # Prefix lint results with project slug
        for lint in proj_result.lints:
            # LintResult is frozen: relabelling produces a new diagnostic.
            aggregate.lints.append(dataclasses.replace(
                lint, file=f"[{slug}] {lint.file}",
            ))

        # Merge coverage stats
        if proj_result.coverage is not None:
            if aggregate.coverage is None:
                aggregate.coverage = CoverageStats()
            aggregate.coverage.total_public += proj_result.coverage.total_public
            aggregate.coverage.referenced += proj_result.coverage.referenced
            aggregate.coverage.documented += proj_result.coverage.documented
            aggregate.coverage.referenced_symbols.extend(
                f"[{slug}] {s}" for s in proj_result.coverage.referenced_symbols
            )
            aggregate.coverage.documented_symbols.extend(
                f"[{slug}] {s}" for s in proj_result.coverage.documented_symbols
            )
            aggregate.coverage.unreferenced_symbols.extend(
                f"[{slug}] {s}" for s in proj_result.coverage.unreferenced_symbols
            )

    # Check the docs-site's own content
    try:
        common_result = check_docs(dir_path, config=config, dry_run=dry_run)
    except RuntimeError as exc:
        aggregate.lints.append(LintResult(
            file="[common]",
            line=None,
            code="UNIFIED002",
            message=str(exc),
        ))
    else:
        for dr in common_result.directive_results:
            dr.file = f"[common] {dr.file}"
            aggregate.directive_results.append(dr)
        for lint in common_result.lints:
            aggregate.lints.append(dataclasses.replace(
                lint, file=f"[common] {lint.file}",
            ))

    return aggregate
