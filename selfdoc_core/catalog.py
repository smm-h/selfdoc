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


# -- Shared cross-cutting attributes ------------------------------------------

# Attributes accepted by every code-category directive regardless of name.
# The multi-language resolver (selfdoc_core.resolver.Resolver) reads ``lang``
# to disambiguate which language extractor handles a path-dispatched directive,
# so it is valid on any code directive. gen emits it on every generated ``ref``
# page. Declared once here and spread into each code spec's optional_attrs so
# the set stays DRY.
SHARED_CODE_ATTRS: list[str] = ["lang"]


# -- Core directives (shipped and functional at launch) -----------------------

CORE_DIRECTIVES: dict[str, DirectiveSpec] = {
    "ref": DirectiveSpec(
        description="Extract module docstring, exported functions, and classes",
        category="code",
        required_attrs=["path"],
        optional_attrs=["target", *SHARED_CODE_ATTRS],
        example=':::ref path="mymodule"',
    ),
    "table-schema": DirectiveSpec(
        description="Extract dataclass/struct fields as a markdown table",
        category="code",
        required_attrs=["path"],
        optional_attrs=["target", "exclude", *SHARED_CODE_ATTRS],
        example=':::table-schema path="models.py" target="User"',
    ),
    "code-test": DirectiveSpec(
        description="Embed test source code (whole file or specific function)",
        category="code",
        required_attrs=["path"],
        optional_attrs=["target", *SHARED_CODE_ATTRS],
        example=':::code-test path="tests/test_auth.py" target="test_login"',
    ),
    "code-help": DirectiveSpec(
        description="Extract CLI help/usage text and flag definitions",
        category="code",
        required_attrs=["path"],
        optional_attrs=[*SHARED_CODE_ATTRS],
        example=':::code-help path="cli.py"',
    ),
    "table-config": DirectiveSpec(
        description="Render a config file (JSON/TOML) as a key-value table",
        category="code",
        required_attrs=["path"],
        optional_attrs=["exclude", *SHARED_CODE_ATTRS],
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
    "prose-desc": DirectiveSpec(
        description="Extract module/package docstring as prose text",
        category="code",
        required_attrs=["path"],
        optional_attrs=[*SHARED_CODE_ATTRS],
        example=':::prose-desc path="mymodule"',
    ),
    "list-tree": DirectiveSpec(
        description="File/directory tree listing",
        category="content",
        required_attrs=["path"],
        optional_attrs=["depth"],
        example=':::list-tree path="src/"',
    ),
    "table-dep": DirectiveSpec(
        description="Dependencies table from pyproject.toml",
        category="content",
        required_attrs=["path"],
        example=':::table-dep path="pyproject.toml"',
    ),
    "list-modules": DirectiveSpec(
        description="List source modules with file paths and docstring summaries",
        category="content",
        required_attrs=["path"],
        optional_attrs=["files"],
        example=':-: list-modules path="selfdoc/"',
    ),
    "table-commands": DirectiveSpec(
        description="CLI command summary table from strictcli structure",
        category="content",
        optional_attrs=["schema-dir"],
        example=":-: table-commands",
    ),
    "table-endpoint": DirectiveSpec(
        description="REST API endpoint table from OpenAPI spec",
        category="content",
        required_attrs=["path"],
        optional_attrs=["endpoint", "method"],
        example=':-: table-endpoint path="openapi.json"',
    ),
    "table-directives": DirectiveSpec(
        description="Table of all core built-in directives",
        category="content",
        example=':-: table-directives',
    ),
    "table-config-schema": DirectiveSpec(
        description="Configuration field reference table from schema",
        category="content",
        example=':-: table-config-schema',
    ),
    "var": DirectiveSpec(
        description="Interpolate project metadata value",
        category="content",
        required_attrs=["key"],
        example=':-: var key="project.name"',
    ),
}

# -- Future directives (declared, not yet implemented) ------------------------

FUTURE_DIRECTIVES: set[str] = {
    # Tables
    "table-param",
    "table-env",
    "table-compare",
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


class DirectiveAttrError(RuntimeError):
    """Raised when a directive uses an unknown attribute or omits a required one.

    This is a hard error (exit 1), distinct from resolution failures which are
    warning-level. It subclasses ``RuntimeError`` so the CLI's existing
    ``RuntimeError`` handlers surface it with a clean message and a non-zero
    exit code.
    """


def validate_directive_attrs(
    name: str, attrs: dict[str, str], *, file: str, line: int
) -> None:
    """Enforce a directive's attribute contract against its catalog spec.

    Raises :class:`DirectiveAttrError` if *attrs* contains an attribute the
    directive does not accept, or omits one it requires. Only core directives
    with a known spec are enforced; custom and future directives are skipped
    because they define their own attribute schemas.

    Args:
        name: Directive name (e.g. ``"ref"``).
        attrs: Parsed attribute dict for this directive occurrence.
        file: Source file path, for the error message.
        line: 1-based line number within *file*, for the error message.
    """
    spec = CORE_DIRECTIVES.get(name)
    if spec is None:
        return

    allowed = set(spec.required_attrs) | set(spec.optional_attrs)

    for attr in attrs:
        if attr in allowed:
            continue
        # Actionable migration hint for the removed table-commands path attr.
        if name == "table-commands" and attr == "path":
            raise DirectiveAttrError(
                f"{file}:{line}: directive 'table-commands' no longer takes "
                "'path'; the schema is discovered automatically. Use "
                'schema-dir="<dir>" only if discovery reports ambiguity.'
            )
        allowed_display = ", ".join(sorted(allowed)) if allowed else "(none)"
        raise DirectiveAttrError(
            f"{file}:{line}: directive '{name}' has unknown attribute "
            f"'{attr}'. Allowed attributes: {allowed_display}."
        )

    for req in spec.required_attrs:
        if req not in attrs:
            required_display = ", ".join(spec.required_attrs)
            raise DirectiveAttrError(
                f"{file}:{line}: directive '{name}' is missing required "
                f"attribute '{req}'. Required attributes: {required_display}."
            )


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
