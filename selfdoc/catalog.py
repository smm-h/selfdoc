"""Directive catalog: defines all built-in directive names and their status."""

from __future__ import annotations

# -- Core directives (shipped and functional at launch) -----------------------

CORE_DIRECTIVES: set[str] = {
    "ref",
    "table-schema",
    "code-test",
    "code-help",
    "table-config",
    "callout-note",
    "callout-warning",
    "callout-tip",
    "callout-danger",
    "callout-important",
    "list-glossary",
}

# -- Future directives (declared, not yet implemented) ------------------------

FUTURE_DIRECTIVES: set[str] = {
    # Tables
    "table-param",
    "table-endpoint",
    "table-env",
    "table-compare",
    "table-dep",
    "table-error",
    "table-shortcut",
    "table-status",
    "table-registry",
    "table-migration",
    "table-timeline",
    "table-perm",
    "table-plan",
    # Code
    "code-source",
    "code-example",
    "code-session",
    "code-repl",
    "code-config",
    "code-diff",
    "code-error",
    "code-schema",
    "code-template",
    "code-log",
    "code-query",
    "code-wire",
    "code-build",
    # Lists
    "list-toc",
    "list-check",
    "list-steps",
    "list-faq",
    "list-features",
    "list-tree",
    "list-deps",
    "list-breadcrumb",
    "list-related",
    "list-errors",
    "list-decisions",
    "list-reqs",
    "list-api",
    "list-changelog",
    # Callouts
    "callout-example",
    "callout-deprecated",
    "callout-security",
    "callout-perf",
    "callout-compat",
    "callout-experimental",
    "callout-see-also",
    "callout-breaking",
    "callout-success",
    "callout-quote",
    # Prose
    "prose-desc",
    "prose-summary",
    "prose-caption",
    "prose-rationale",
    "prose-caveat",
    "prose-migration",
    "prose-changelog",
    "prose-release",
    "prose-prereq",
    "prose-abstract",
    "prose-deprecation",
    "prose-attribution",
    "prose-definition",
    "prose-annotation",
    "prose-example",
}

# -- Combined set of all built-in directives ----------------------------------

ALL_BUILTIN_DIRECTIVES: set[str] = CORE_DIRECTIVES | FUTURE_DIRECTIVES

# -- Old-to-new name mapping for backward compatibility -----------------------

DIRECTIVE_NAME_MAPPING: dict[str, str] = {
    "module": "ref",
    "schema": "table-schema",
    "test": "code-test",
    "cli": "code-help",
    "config": "table-config",
    "glossary": "list-glossary",
}


# -- Helper functions ---------------------------------------------------------


def is_valid_directive(
    name: str, custom_names: set[str] | None = None
) -> bool:
    """Return True if *name* is a recognized built-in or custom directive."""
    if name in ALL_BUILTIN_DIRECTIVES:
        return True
    if custom_names is not None and name in custom_names:
        return True
    return False


def directive_status(name: str) -> str:
    """Return ``"core"``, ``"future"``, or ``"unknown"`` for a directive name.

    Only checks built-in directives; custom directives are the caller's
    responsibility.
    """
    if name in CORE_DIRECTIVES:
        return "core"
    if name in FUTURE_DIRECTIVES:
        return "future"
    return "unknown"
