"""Tests for selfdoc.directives."""

import pytest

from selfdoc.directives import Directive, DirectiveError, parse_directives, resolve_directives


# -- parse: single directive --


def test_parse_single_directive():
    content = ":::module selfdoc.config\n:::"
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].name == "module"
    assert result[0].arg == "selfdoc.config"
    assert result[0].line_number == 1


def test_parse_directive_no_arg():
    """Directive with no arg should have arg as empty string."""
    content = ":::module\n:::"
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].name == "module"
    assert result[0].arg == ""


# -- parse: multiple directives --


def test_parse_multiple_directives():
    content = (
        "# Heading\n"
        "\n"
        ":::module selfdoc.config\n"
        ":::\n"
        "\n"
        "Some text.\n"
        "\n"
        ":::test tests/test_config.py TestValidConfig\n"
        ":::\n"
    )
    result = parse_directives(content)
    assert len(result) == 2
    assert result[0].name == "module"
    assert result[0].arg == "selfdoc.config"
    assert result[0].line_number == 3
    assert result[1].name == "test"
    assert result[1].arg == "tests/test_config.py TestValidConfig"
    assert result[1].line_number == 8


# -- parse: body --


def test_parse_directive_body():
    content = (
        ":::schema selfdoc.json\n"
        "line one\n"
        "line two\n"
        ":::\n"
    )
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].body == ["line one", "line two"]


# -- parse: code fence --


def test_directive_inside_code_fence_ignored():
    """:::name inside a fenced code block is NOT a directive."""
    content = (
        "```\n"
        ":::module selfdoc.config\n"
        ":::\n"
        "```\n"
    )
    result = parse_directives(content)
    assert result == []


def test_directive_inside_tilde_fence_ignored():
    """:::name inside a ~~~ fenced code block is NOT a directive."""
    content = (
        "~~~\n"
        ":::module selfdoc.config\n"
        ":::\n"
        "~~~\n"
    )
    result = parse_directives(content)
    assert result == []


def test_real_directive_after_code_fence():
    """A directive after a closed code fence should be parsed normally."""
    content = (
        "```\n"
        ":::fake inside.fence\n"
        ":::\n"
        "```\n"
        "\n"
        ":::real outside.fence\n"
        ":::\n"
    )
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].name == "real"
    assert result[0].arg == "outside.fence"


# -- parse: unclosed directive --


def test_unclosed_directive_raises():
    content = ":::module selfdoc.config\nsome body\n"
    with pytest.raises(DirectiveError, match="line 1"):
        parse_directives(content)


# -- parse: empty file --


def test_empty_file_no_directives():
    assert parse_directives("") == []


# -- parse: non-directive content --


def test_non_directive_content():
    content = "# Heading\n\nSome paragraph.\n\n- list item\n"
    assert parse_directives(content) == []


# -- resolve_directives --


def test_resolve_replaces_directives():
    content = (
        "# Title\n"
        "\n"
        ":::module selfdoc.config\n"
        ":::\n"
        "\n"
        "Footer.\n"
    )

    def resolver(name, arg, body):
        return f"[RESOLVED {name}: {arg}]"

    result = resolve_directives(content, resolver)
    assert "[RESOLVED module: selfdoc.config]" in result
    assert ":::module" not in result
    assert "# Title" in result
    assert "Footer." in result


def test_resolve_passes_body_to_resolver():
    content = (
        ":::schema selfdoc.json\n"
        "option_a\n"
        "option_b\n"
        ":::\n"
    )
    captured = {}

    def resolver(name, arg, body):
        captured["body"] = body
        return "replaced"

    resolve_directives(content, resolver)
    assert captured["body"] == ["option_a", "option_b"]


def test_resolve_non_directive_passthrough():
    content = "# Just markdown\n\nNo directives here.\n"

    def resolver(name, arg, body):
        raise AssertionError("Should not be called")

    result = resolve_directives(content, resolver)
    # split/join round-trip preserves trailing newlines, so output == input
    assert result == content


def test_resolve_code_fence_passthrough():
    """Directives inside code fences pass through without resolving."""
    content = (
        "```\n"
        ":::module selfdoc.config\n"
        ":::\n"
        "```\n"
    )

    def resolver(name, arg, body):
        raise AssertionError("Should not be called for fenced content")

    result = resolve_directives(content, resolver)
    assert ":::module selfdoc.config" in result
