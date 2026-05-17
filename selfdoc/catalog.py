"""Directive catalog: defines all built-in directive names and their status."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DirectiveSpec:
    """Metadata for a single built-in directive."""

    description: str
    category: str  # "code" or "content"
    required_attrs: list[str] = field(default_factory=list)
    optional_attrs: list[str] = field(default_factory=list)
    example: str = ""


# -- Core directives (shipped and functional at launch) -----------------------

CORE_DIRECTIVES: dict[str, DirectiveSpec] = {
    "ref": DirectiveSpec(
        description="Extract module docstring, exported functions, and classes",
        category="code",
        required_attrs=["path"],
        optional_attrs=["target"],
        example=':::ref path="mymodule"',
    ),
    "table-schema": DirectiveSpec(
        description="Extract dataclass/struct fields as a markdown table",
        category="code",
        required_attrs=["path"],
        optional_attrs=["target"],
        example=':::table-schema path="models.py" target="User"',
    ),
    "code-test": DirectiveSpec(
        description="Embed test source code (whole file or specific function)",
        category="code",
        required_attrs=["path"],
        optional_attrs=["target"],
        example=':::code-test path="tests/test_auth.py" target="test_login"',
    ),
    "code-help": DirectiveSpec(
        description="Extract CLI help/usage text and flag definitions",
        category="code",
        required_attrs=["path"],
        example=':::code-help path="cli.py"',
    ),
    "table-config": DirectiveSpec(
        description="Render a config file (JSON/TOML) as a key-value table",
        category="code",
        required_attrs=["path"],
        example=':::table-config path="config.json"',
    ),
    "callout-note": DirectiveSpec(
        description="Styled note callout block",
        category="content",
        example=":::callout-note\nThis is a note.\n:::",
    ),
    "callout-warning": DirectiveSpec(
        description="Styled warning callout block",
        category="content",
        example=":::callout-warning\nProceed with caution.\n:::",
    ),
    "callout-tip": DirectiveSpec(
        description="Styled tip callout block",
        category="content",
        example=":::callout-tip\nHelpful hint here.\n:::",
    ),
    "callout-danger": DirectiveSpec(
        description="Styled danger callout block",
        category="content",
        example=":::callout-danger\nDangerous operation.\n:::",
    ),
    "callout-important": DirectiveSpec(
        description="Styled important callout block",
        category="content",
        example=":::callout-important\nDo not skip this step.\n:::",
    ),
    "list-glossary": DirectiveSpec(
        description="Definition list from **Term**: Definition lines",
        category="content",
        example=":::list-glossary\n**API**: Application Programming Interface\n:::",
    ),
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

ALL_BUILTIN_DIRECTIVES: set[str] = set(CORE_DIRECTIVES) | FUTURE_DIRECTIVES

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
