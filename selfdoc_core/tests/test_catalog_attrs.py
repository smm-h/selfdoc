"""Tests for catalog attribute enforcement (validate_directive_attrs)."""

import pytest

from selfdoc_core.catalog import (
    DirectiveAttrError,
    validate_directive_attrs,
)


def test_accepts_valid_attrs():
    # No exception for a well-formed directive.
    validate_directive_attrs(
        "ref", {"path": "pkg.mod", "lang": "python"}, file="a.md", line=3
    )
    validate_directive_attrs(
        "table-schema",
        {"path": "m.py", "target": "User", "exclude": "x"},
        file="a.md",
        line=1,
    )


def test_unknown_attr_raises_with_context():
    with pytest.raises(DirectiveAttrError) as exc:
        validate_directive_attrs(
            "ref", {"path": "m", "bogus": "1"}, file="docs/x.md", line=7
        )
    msg = str(exc.value)
    assert "docs/x.md:7" in msg
    assert "ref" in msg
    assert "bogus" in msg
    # Allowed list is surfaced for actionability.
    assert "path" in msg and "lang" in msg


def test_missing_required_attr_raises():
    with pytest.raises(DirectiveAttrError) as exc:
        validate_directive_attrs("ref", {}, file="docs/x.md", line=2)
    msg = str(exc.value)
    assert "docs/x.md:2" in msg
    assert "missing required" in msg
    assert "path" in msg


def test_var_requires_key():
    with pytest.raises(DirectiveAttrError):
        validate_directive_attrs("var", {}, file="a.md", line=1)
    validate_directive_attrs("var", {"key": "project.name"}, file="a.md", line=1)


def test_callout_rejects_any_attr():
    with pytest.raises(DirectiveAttrError):
        validate_directive_attrs(
            "callout-note", {"title": "hi"}, file="a.md", line=1
        )
    # Bare callout is fine.
    validate_directive_attrs("callout-note", {}, file="a.md", line=1)


def test_custom_and_future_directives_are_skipped():
    # Not a core directive -> no spec -> no enforcement (custom directives
    # define their own attribute schemas).
    validate_directive_attrs(
        "my-widget", {"anything": "goes"}, file="a.md", line=1
    )
    # Future directive names have no spec either.
    validate_directive_attrs(
        "code-source", {"whatever": "x"}, file="a.md", line=1
    )


def test_table_commands_path_gives_migration_hint():
    # `path` was removed from table-commands (schema is auto-discovered), so a
    # leftover path= is an unknown attr with an actionable migration message.
    with pytest.raises(DirectiveAttrError) as exc:
        validate_directive_attrs(
            "table-commands", {"path": "."}, file="docs/_README.md", line=9
        )
    msg = str(exc.value)
    assert "docs/_README.md:9" in msg
    assert "no longer takes" in msg
    assert "schema-dir" in msg


def test_table_commands_accepts_schema_dir():
    validate_directive_attrs(
        "table-commands", {"schema-dir": "."}, file="a.md", line=1
    )
    # Bare table-commands (auto-discovery) is valid.
    validate_directive_attrs("table-commands", {}, file="a.md", line=1)
