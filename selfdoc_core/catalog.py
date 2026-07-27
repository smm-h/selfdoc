"""Directive catalog: defines all built-in directive names and their status.

The ``CORE_DIRECTIVES`` catalogue is no longer a hand-maintained dict literal.
It is BUILT at import time from ``selfdoc_core/directives.toml`` -- a declarative
descriptor document governed by ``.strictspec/directive-descriptor.schema.toml``
and validated by the strictspec-generated ``directive_descriptor_validator``.
The document is the single source of truth; this module is a thin loader.

A malformed catalogue document (bad name grammar, unknown key, missing required
field, duplicate name, absent format_version gate, ...) is a hard error at import
-- selfdoc fails to load before any directive is dispatched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files

from selfdoc_core import directive_descriptor_validator as _validator


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
# page. Each code directive's ``optional_attrs`` in ``directives.toml`` lists it
# explicitly; this constant names the invariant a test enforces.
SHARED_CODE_ATTRS: list[str] = ["lang"]


# -- Core directives (built from the validated descriptor document) -----------

_CATALOGUE_DOCUMENT = "directives.toml"


class CatalogDocumentError(RuntimeError):
    """Raised when ``directives.toml`` fails strictspec validation at load.

    A hard error at import time: the built-in directive catalogue is malformed,
    so selfdoc cannot know what its own directives are. Subclasses
    ``RuntimeError`` so the CLI's existing handlers surface it cleanly.
    """


def _build_catalogue(raw: bytes) -> dict[str, DirectiveSpec]:
    """Validate raw catalogue-document bytes and bind them into DirectiveSpecs.

    strictspec is the boundary validator: the document is validated against its
    schema by the generated validator, and only a fully-valid document is bound.
    Any diagnostic is a hard error (:class:`CatalogDocumentError`).
    """
    catalogue, diags = _validator.validate_bytes(raw, "toml")
    if diags:
        detail = "\n".join(f"  {d.path}: {d.message} [{d.code}]" for d in diags)
        raise CatalogDocumentError(
            f"{_CATALOGUE_DOCUMENT} is not a valid directive catalogue:\n{detail}"
        )
    return {
        d.name: DirectiveSpec(
            description=d.description,
            category=d.category,
            required_attrs=list(d.required_attrs),
            optional_attrs=list(d.optional_attrs),
            example=d.example,
        )
        for d in catalogue.directives
    }


def _load_core_directives() -> dict[str, DirectiveSpec]:
    """Read, validate, and bind ``directives.toml`` into the runtime catalogue."""
    raw = files("selfdoc_core").joinpath(_CATALOGUE_DOCUMENT).read_bytes()
    return _build_catalogue(raw)


CORE_DIRECTIVES: dict[str, DirectiveSpec] = _load_core_directives()

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
