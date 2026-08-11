"""Lint verdict rules shared by every check entry point.

``selfdoc check``, ``selfblog check`` (unified), the post-build lint pass and
the posts-only check all decide the same question -- does this run pass? --
and they used to decide it with four separate copies of the same three
conditions.  One of the copies had drifted: the unified path compared
``documented < total_public`` directly, hardcoding a 100% coverage
requirement, so a project that lowered ``coverage_threshold`` passed
``selfdoc check`` and failed ``selfblog check`` on identical state.

This module owns the rules.  It lives in selfdoc_core because selfblog
depends on selfdoc-core but not on selfdoc: a posts-only selfblog install
must be able to reach the verdict without the selfdoc package present.
"""

from __future__ import annotations

# Fraction of public symbols that must be documented when a project does not
# say otherwise.  Mirrors the historical CLI default.
DEFAULT_COVERAGE_THRESHOLD = 1.0


def coverage_below_threshold(coverage, config=None) -> bool:
    """True when documented coverage is under the configured threshold.

    Args:
        coverage: A coverage stats object (``total_public``/``documented``),
            or None when the run measured no coverage.
        config: The project configuration dict the run was driven by, read
            for ``coverage_threshold``.  None means "no configuration in
            play", which uses the default threshold.

    Returns:
        False whenever there is nothing to measure -- no coverage object, or
        a project with no public symbols at all.
    """
    if coverage is None or coverage.total_public <= 0:
        return False
    threshold = (config or {}).get(
        "coverage_threshold", DEFAULT_COVERAGE_THRESHOLD,
    )
    return coverage.documented / coverage.total_public < threshold


def check_exit_code(lints, directive_results=(), coverage=None, config=None) -> int:
    """Compute the process exit code for a check run.

    The single definition of "did this check pass": a run fails when a
    directive failed to resolve, when any lint is error-severity, or when
    documented coverage is under the configured threshold.

    Args:
        lints: The lint diagnostics the run produced, already filtered
            through the project's suppression list.
        directive_results: Per-directive resolution results, when the entry
            point resolved directives.  A reduced entry point (the
            post-build lint pass, the posts-only check) passes none.
        coverage: Coverage stats, when the entry point measured coverage.
        config: Project configuration, read for ``coverage_threshold``.

    Returns:
        1 when the run fails, 0 when it passes.
    """
    has_failures = any(dr.status == "FAILED" for dr in directive_results)
    has_errors = any(lint.severity == "error" for lint in lints)
    below = coverage_below_threshold(coverage, config)
    return 1 if (has_failures or has_errors or below) else 0
