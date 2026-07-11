"""Tests for selfdoc.catalog."""

from selfdoc.catalog import (
    ALL_BUILTIN_DIRECTIVES,
    CORE_DIRECTIVES,
    DIRECTIVE_NAME_MAPPING,
    DirectiveSpec,
    FUTURE_DIRECTIVES,
    directive_status,
    is_valid_directive,
)


# -- Set invariants -----------------------------------------------------------


def test_core_and_future_do_not_overlap():
    overlap = set(CORE_DIRECTIVES) & FUTURE_DIRECTIVES
    assert overlap == set(), f"overlapping directives: {overlap}"


def test_all_builtin_is_core_union_future():
    assert ALL_BUILTIN_DIRECTIVES == set(CORE_DIRECTIVES) | FUTURE_DIRECTIVES


# -- is_valid_directive -------------------------------------------------------


def test_is_valid_core_directive():
    assert is_valid_directive("ref") is True
    assert is_valid_directive("table-schema") is True


def test_is_valid_future_directive():
    assert is_valid_directive("code-source") is True
    assert is_valid_directive("prose-summary") is True


def test_is_valid_custom_directive():
    custom = {"my-widget", "project-badge"}
    assert is_valid_directive("my-widget", custom_names=custom) is True
    assert is_valid_directive("project-badge", custom_names=custom) is True


def test_is_valid_unknown_directive():
    assert is_valid_directive("nonexistent") is False


def test_is_valid_unknown_with_empty_custom():
    assert is_valid_directive("nonexistent", custom_names=set()) is False


# -- directive_status ---------------------------------------------------------


def test_directive_status_core():
    for name in CORE_DIRECTIVES:
        assert directive_status(name) == "core", f"{name} should be core"


def test_directive_status_future():
    for name in FUTURE_DIRECTIVES:
        assert directive_status(name) == "future", f"{name} should be future"


def test_directive_status_unknown():
    assert directive_status("nonexistent") == "unknown"
    assert directive_status("my-custom") == "unknown"


# -- DIRECTIVE_NAME_MAPPING ---------------------------------------------------


def test_mapping_targets_are_core_directives():
    for old_name, new_name in DIRECTIVE_NAME_MAPPING.items():
        assert new_name in CORE_DIRECTIVES, (
            f"mapping {old_name!r} -> {new_name!r} but {new_name!r} "
            f"is not in CORE_DIRECTIVES"
        )


def test_mapping_covers_all_old_names():
    expected_old = {"module", "schema", "test", "cli", "config", "glossary"}
    assert set(DIRECTIVE_NAME_MAPPING.keys()) == expected_old


# -- DirectiveSpec metadata ---------------------------------------------------

EXPECTED_CORE_NAMES = {
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
    "prose-desc",
    "list-tree",
    "table-dep",
    "list-modules",
    "table-commands",
    "table-directives",
    "table-config-schema",
    "table-endpoint",
    "var",
}


def test_all_core_directives_have_metadata():
    assert set(CORE_DIRECTIVES) == EXPECTED_CORE_NAMES


def test_directive_spec_fields_populated():
    for name, spec in CORE_DIRECTIVES.items():
        assert isinstance(spec, DirectiveSpec), f"{name}: not a DirectiveSpec"
        assert spec.description, f"{name}: empty description"
        assert spec.category in ("code", "content"), (
            f"{name}: invalid category {spec.category!r}"
        )
        assert spec.example, f"{name}: empty example"


def test_code_directives_require_path():
    for name, spec in CORE_DIRECTIVES.items():
        if spec.category == "code":
            assert "path" in spec.required_attrs, (
                f"{name}: code directive missing required 'path' attr"
            )


# Content directives that take body content (callouts, glossary) have no
# required attrs.  Filesystem-aware content directives (list-tree, table-dep)
# require a path attribute.
_BODY_ONLY_CONTENT = {
    "callout-note", "callout-warning", "callout-tip",
    "callout-danger", "callout-important", "list-glossary",
}


def test_body_only_content_directives_have_no_required_attrs():
    for name in _BODY_ONLY_CONTENT:
        spec = CORE_DIRECTIVES[name]
        assert spec.required_attrs == [], (
            f"{name}: body-only content directive should have no required attrs"
        )


def test_filesystem_content_directives_require_path():
    fs_content = {"list-tree", "table-dep"}
    for name in fs_content:
        spec = CORE_DIRECTIVES[name]
        assert "path" in spec.required_attrs, (
            f"{name}: filesystem content directive should require 'path'"
        )


def test_is_valid_directive_with_dict_core():
    """is_valid_directive still works after CORE_DIRECTIVES became a dict."""
    for name in CORE_DIRECTIVES:
        assert is_valid_directive(name) is True


def test_directive_status_core_with_dict():
    """directive_status returns 'core' for all core directives (dict keys)."""
    for name in CORE_DIRECTIVES:
        assert directive_status(name) == "core", f"{name} should be core"
