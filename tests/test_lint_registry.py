"""The lint registry is the single source of truth for codes and severities.

``selfdoc_core/lints.toml`` declares every emittable lint code with its
severity and its one-line description.  Two surfaces are DERIVED from it and
must not drift:

- ``schemas/check-output.schema.json`` -- its lint-code enum (pinned by
  tests/test_check_schema.py).
- ``docs/check-guide.md`` -- its lint-rule table (pinned here).

The emission side needs no test to stay honest: :class:`LintResult` takes no
``severity`` argument and refuses an unregistered code.
"""

import os
import re

import pytest

from selfdoc_core.lints import (
    LINT_REGISTRY,
    LintResult,
    UnknownLintCode,
    lint_severity,
    render_lint_table,
)


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CHECK_GUIDE = os.path.join(_REPO_ROOT, "docs", "check-guide.md")


def _guide_lint_table():
    """Extract the lint-rule table from the check guide, verbatim."""
    with open(_CHECK_GUIDE, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    try:
        start = next(
            i for i, ln in enumerate(lines)
            if ln.startswith("| Code | Severity |")
        )
    except StopIteration:
        raise AssertionError(
            f"no lint-rule table found in {_CHECK_GUIDE}"
        ) from None
    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return "\n".join(lines[start:end])


# -- The registry itself ------------------------------------------------------


def test_registry_is_non_empty_and_keyed_by_code():
    """Every entry is keyed by its own code."""
    assert LINT_REGISTRY
    for code, spec in LINT_REGISTRY.items():
        assert spec.code == code


def test_every_severity_is_error_or_warning():
    """Severity is a closed set; the document schema enforces the enum."""
    assert {spec.severity for spec in LINT_REGISTRY.values()} <= {
        "error", "warning",
    }


@pytest.mark.parametrize("code", sorted(LINT_REGISTRY))
def test_every_entry_has_a_description(code):
    """A registered code carries the prose the documentation table renders."""
    assert LINT_REGISTRY[code].description.strip()


# -- Emission is structurally constrained -------------------------------------


def test_lint_result_derives_severity_from_the_registry():
    """The construction site names a code; the registry supplies the severity."""
    assert LintResult(
        file="a.md", line=1, code="SEO001", message="m",
    ).severity == lint_severity("SEO001")
    assert LintResult(
        file="a.md", line=1, code="SEO002", message="m",
    ).severity == lint_severity("SEO002")


def test_lint_result_rejects_a_severity_argument():
    """A severity literal at a construction site is not expressible."""
    with pytest.raises(TypeError):
        LintResult(
            file="a.md", line=1, code="SEO001", message="m",
            severity="warning",
        )


def test_lint_result_rejects_an_unregistered_code():
    """An undeclared code is a hard error, not a lint with no severity."""
    with pytest.raises(UnknownLintCode) as excinfo:
        LintResult(file="a.md", line=1, code="NOPE001", message="m")
    assert "NOPE001" in str(excinfo.value)
    assert "lints.toml" in str(excinfo.value)


def test_lint_severity_rejects_an_unregistered_code():
    with pytest.raises(UnknownLintCode):
        lint_severity("NOPE001")


# -- The documentation table is derived ---------------------------------------


def test_check_guide_table_is_the_rendered_registry():
    """docs/check-guide.md carries exactly the table the registry renders.

    The table is a derived surface. Adding, removing, or re-describing a rule
    happens in selfdoc_core/lints.toml; the guide is then re-rendered from it.
    """
    assert _guide_lint_table() == render_lint_table(), (
        "the lint-rule table in docs/check-guide.md has drifted from the "
        "registry. Regenerate it from selfdoc_core.lints.render_lint_table() "
        "-- do not hand-edit the table."
    )


def test_check_guide_table_covers_every_registered_code():
    """Sanity check on the extraction itself: one row per registered code."""
    rows = _guide_lint_table().split("\n")[2:]
    codes = [re.match(r"\| (\S+) \|", row).group(1) for row in rows]
    assert codes == list(LINT_REGISTRY)
