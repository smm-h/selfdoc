"""Tests for selfdoc.catalog."""

from selfdoc.catalog import (
    ALL_BUILTIN_DIRECTIVES,
    CORE_DIRECTIVES,
    DIRECTIVE_NAME_MAPPING,
    FUTURE_DIRECTIVES,
    directive_status,
    is_valid_directive,
)


# -- Set invariants -----------------------------------------------------------


def test_core_and_future_do_not_overlap():
    overlap = CORE_DIRECTIVES & FUTURE_DIRECTIVES
    assert overlap == set(), f"overlapping directives: {overlap}"


def test_all_builtin_is_core_union_future():
    assert ALL_BUILTIN_DIRECTIVES == CORE_DIRECTIVES | FUTURE_DIRECTIVES


# -- is_valid_directive -------------------------------------------------------


def test_is_valid_core_directive():
    assert is_valid_directive("ref") is True
    assert is_valid_directive("table-schema") is True


def test_is_valid_future_directive():
    assert is_valid_directive("code-source") is True
    assert is_valid_directive("prose-desc") is True


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
