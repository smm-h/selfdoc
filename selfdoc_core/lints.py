"""The lint-code registry and the verdict rules shared by every check entry point.

``lints.toml`` is the single source of truth for every lint code selfdoc and
selfblog can emit: its severity and its one-line description live there and
nowhere else.  :class:`LintResult` derives ``severity`` from the registry, so
a construction site cannot state a severity and cannot emit an unregistered
code -- both are hard errors rather than conventions.  The lint-code enum in
selfdoc's declared check payload schema (``selfdoc/payload_schemas.py``) and
the lint-rule table in ``docs/check-guide.md`` are pinned to the registry by
tests.


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

from dataclasses import dataclass, field
from importlib.resources import files

from selfdoc_core import lint_registry_validator as _validator

# Fraction of public symbols that must be documented when a project does not
# say otherwise.  Mirrors the historical CLI default.
DEFAULT_COVERAGE_THRESHOLD = 1.0


# -- The registry -------------------------------------------------------------

_REGISTRY_DOCUMENT = "lints.toml"


class LintRegistryError(RuntimeError):
    """Raised when ``lints.toml`` fails strictspec validation at load.

    A hard error at import time: the lint registry is malformed, so selfdoc
    cannot know what its own lint codes are.  Subclasses ``RuntimeError`` so
    the CLI's existing handlers surface it cleanly.
    """


class LintSuppressionError(RuntimeError):
    """Base for every refusal of a suppression-list entry.

    A suppression list is refused for one of two reasons -- the code is not
    in the registry, or the code is error-severity and therefore not
    suppressible.  Both are the same event to a caller (the list is bad,
    say so and stop), so one ``except`` clause covers them.
    """


class UnknownLintCode(LintSuppressionError):
    """Raised when a lint is constructed with a code the registry does not carry.

    Every emittable code is declared in ``lints.toml``.  An undeclared code
    would carry no severity, would be rejected by the JSON output schema, and
    would be invisible to the documentation table -- so it is refused at the
    construction site instead.
    """


class UnsuppressableLintCode(LintSuppressionError):
    """Raised when a suppression list names an error-severity code.

    Suppression reaches warning-severity codes only.  An error says the
    build is wrong -- a broken emitted reference, a missing description, a
    post whose slug moved -- and silencing it hides the defect rather than
    resolving it, which is exactly how a genuinely broken build once passed
    its own check.  The registry is the severity authority, so the refusal
    is decided there and nowhere else.
    """


@dataclass(slots=True, frozen=True)
class LintSpec:
    """Registry entry for a single lint code."""

    code: str
    severity: str  # "error" or "warning"
    description: str


def _build_registry(raw: bytes) -> dict[str, LintSpec]:
    """Validate raw registry-document bytes and bind them into LintSpecs.

    strictspec is the boundary validator: the document is validated against
    its schema by the generated validator, and only a fully-valid document is
    bound.  Any diagnostic is a hard error (:class:`LintRegistryError`).
    """
    registry, diags = _validator.validate_bytes(raw, "toml")
    if diags:
        detail = "\n".join(f"  {d.path}: {d.message} [{d.code}]" for d in diags)
        raise LintRegistryError(
            f"{_REGISTRY_DOCUMENT} is not a valid lint registry:\n{detail}"
        )
    return {
        entry.code: LintSpec(
            code=entry.code,
            severity=entry.severity,
            description=entry.description,
        )
        for entry in registry.lints
    }


def _load_registry() -> dict[str, LintSpec]:
    """Read, validate, and bind ``lints.toml`` into the runtime registry."""
    raw = files("selfdoc_core").joinpath(_REGISTRY_DOCUMENT).read_bytes()
    return _build_registry(raw)


# Registry order is documentation order: the table renders in this order.
LINT_REGISTRY: dict[str, LintSpec] = _load_registry()


def lint_severity(code: str) -> str:
    """Return the registered severity for *code*, or raise UnknownLintCode."""
    spec = LINT_REGISTRY.get(code)
    if spec is None:
        raise UnknownLintCode(
            f"lint code {code!r} is not in the registry. Every emittable code "
            f"must be declared in selfdoc_core/{_REGISTRY_DOCUMENT} with its "
            f"severity and description."
        )
    return spec.severity


def validate_lint_codes(codes, *, source: str) -> None:
    """Refuse any code in *codes* the registry rejects for suppression.

    Two refusals, both decided by the registry:

    - An unregistered code suppresses nothing and hides the fact that it
      suppresses nothing, so it is a hard error where the list is read
      rather than a silently inert entry.
    - A registered *error*-severity code is not suppressible at all.
      Suppression reaches warnings only; an error means the build is
      wrong, and silencing it hides the defect.

    Args:
        codes: The lint codes to check, in the order the user wrote them.
        source: Where the codes came from, named in the error message
            (e.g. ``"lint_ignore"`` or ``"--ignore"``).

    Raises:
        UnknownLintCode: Naming every unregistered code, not just the first.
        UnsuppressableLintCode: Naming every error-severity code, with its
            severity.  Checked after the unregistered codes, so a typo is
            reported as a typo.
    """
    unknown = [code for code in codes if code not in LINT_REGISTRY]
    if unknown:
        listed = ", ".join(repr(code) for code in unknown)
        raise UnknownLintCode(
            f"{source} names lint code(s) the registry does not carry: "
            f"{listed}. Every suppressible code is declared in selfdoc_core/"
            f"{_REGISTRY_DOCUMENT}; known codes are: "
            f"{', '.join(sorted(LINT_REGISTRY))}."
        )

    errors = [code for code in codes if LINT_REGISTRY[code].severity == "error"]
    if errors:
        listed = ", ".join(
            f"{code} (severity: {LINT_REGISTRY[code].severity})"
            for code in errors
        )
        suppressible = sorted(
            code for code, spec in LINT_REGISTRY.items()
            if spec.severity == "warning"
        )
        raise UnsuppressableLintCode(
            f"{source} names error-severity lint code(s), which cannot be "
            f"suppressed: {listed}. An error says the build is wrong -- fix "
            f"the defect it reports. Suppression reaches warning-severity "
            f"codes only: {', '.join(suppressible)}."
        )


def parse_ignore_codes(raw, *, source: str = "--ignore") -> set[str]:
    """Parse a comma-separated ``--ignore`` value into a validated code set.

    Args:
        raw: The flag value as given, or None/empty when the flag was not
            passed.
        source: Flag name to attribute a rejection to.

    Returns:
        The set of codes to suppress -- empty when nothing was passed.

    Raises:
        UnknownLintCode: When any code is not in the registry.
        UnsuppressableLintCode: When any code is error-severity.
    """
    if not raw:
        return set()
    codes = [part.strip() for part in raw.split(",") if part.strip()]
    validate_lint_codes(codes, source=source)
    return set(codes)


@dataclass(frozen=True)
class LintResult:
    """A single lint diagnostic (e.g. SEO warning).

    ``severity`` is not a constructor argument: it is read from the registry
    for the given code.  That is what keeps severities out of the ~50
    construction sites scattered across the check modules, and what makes an
    unregistered code impossible to emit.

    The instance is frozen: a diagnostic's severity is the registry's answer
    for its code, and nothing downstream may rewrite it after the fact.
    """

    file: str  # relative path within docs/
    line: int | None
    code: str  # e.g. "SEO001"
    message: str
    severity: str = field(init=False)  # derived from the registry

    def __post_init__(self):
        # Frozen instances refuse ordinary assignment; the derived field is
        # written the one way a frozen dataclass permits.
        object.__setattr__(self, "severity", lint_severity(self.code))


def lint_table_rows() -> list[tuple[str, str, str]]:
    """Return ``(code, severity, description)`` for every registered lint.

    In registry (documentation) order.  The documentation's lint-rule table
    is rendered from exactly this.
    """
    return [
        (spec.code, spec.severity, spec.description)
        for spec in LINT_REGISTRY.values()
    ]


def render_lint_table() -> str:
    """Render the registry as the Markdown table the documentation carries."""
    lines = [
        "| Code | Severity | What it checks |",
        "| ---- | -------- | -------------- |",
    ]
    lines.extend(
        f"| {code} | {severity} | {description} |"
        for code, severity, description in lint_table_rows()
    )
    return "\n".join(lines)


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
