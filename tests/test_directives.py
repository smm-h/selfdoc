"""Tests for selfdoc.directives — new marker syntax."""

import pytest

from selfdoc.directives import Directive, DirectiveError, parse_directives, resolve_directives


# -- One-liner (:-:) ---------------------------------------------------------


def test_oneliner_no_attrs():
    content = ':-: ref'
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].name == "ref"
    assert result[0].attrs == {}
    assert result[0].body == []
    assert result[0].line_number == 1


def test_oneliner_with_attrs():
    content = ':-: ref src="selfdoc.config" lang="python"'
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].name == "ref"
    assert result[0].attrs == {"src": "selfdoc.config", "lang": "python"}
    assert result[0].body == []


def test_oneliner_single_attr():
    content = ':-: code-help cmd="selfdoc --help"'
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].attrs == {"cmd": "selfdoc --help"}


# -- Block (:<: ... :>:) — attrs only ----------------------------------------


def test_block_attrs_only():
    content = (
        ":<: ref\n"
        ':@: src="selfdoc.config"\n'
        ':@: lang="python"\n'
        ":>:"
    )
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].name == "ref"
    assert result[0].attrs == {"src": "selfdoc.config", "lang": "python"}
    assert result[0].body == []


def test_block_inline_attrs():
    content = (
        ':<: ref src="selfdoc.config"\n'
        ":>:"
    )
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].attrs == {"src": "selfdoc.config"}
    assert result[0].body == []


def test_block_inline_and_line_attrs_merged():
    content = (
        ':<: ref src="selfdoc.config"\n'
        ':@: lang="python"\n'
        ":>:"
    )
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].attrs == {"src": "selfdoc.config", "lang": "python"}


# -- Block — body only -------------------------------------------------------


def test_block_body_only():
    content = (
        ":<: callout-note\n"
        ":=:\n"
        "::: This is a note.\n"
        "::: Second line.\n"
        ":>:"
    )
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].attrs == {}
    assert result[0].body == ["This is a note.", "Second line."]


def test_body_line_prefix_stripped():
    """Body lines have exactly '::: ' (4 chars) stripped."""
    content = (
        ":<: callout-note\n"
        ":=:\n"
        "::: Hello world\n"
        ":>:"
    )
    result = parse_directives(content)
    assert result[0].body == ["Hello world"]


# -- Block — attrs and body --------------------------------------------------


def test_block_attrs_and_body():
    content = (
        ':<: code-test\n'
        ':@: file="tests/test_config.py"\n'
        ':@: class="TestValidConfig"\n'
        ':=:\n'
        '::: Extra context here.\n'
        ':>:'
    )
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].name == "code-test"
    assert result[0].attrs == {"file": "tests/test_config.py", "class": "TestValidConfig"}
    assert result[0].body == ["Extra context here."]


# -- Block — empty (no attrs, no body) ---------------------------------------


def test_empty_block():
    content = ":<: ref\n:>:"
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].name == "ref"
    assert result[0].attrs == {}
    assert result[0].body == []


# -- Multiple directives -----------------------------------------------------


def test_multiple_directives():
    content = (
        "# Heading\n"
        "\n"
        ':-: ref src="selfdoc.config"\n'
        "\n"
        "Some text.\n"
        "\n"
        ":<: code-test\n"
        ':@: file="tests/test_config.py"\n'
        ":>:\n"
    )
    result = parse_directives(content)
    assert len(result) == 2
    assert result[0].name == "ref"
    assert result[0].attrs == {"src": "selfdoc.config"}
    assert result[0].line_number == 3
    assert result[1].name == "code-test"
    assert result[1].attrs == {"file": "tests/test_config.py"}
    assert result[1].line_number == 7


# -- Fence tracking -----------------------------------------------------------


def test_directive_inside_backtick_fence_ignored():
    content = (
        "```\n"
        ':-: ref src="selfdoc.config"\n'
        "```\n"
    )
    result = parse_directives(content)
    assert result == []


def test_directive_inside_tilde_fence_ignored():
    content = (
        "~~~\n"
        ":<: ref\n"
        ":>:\n"
        "~~~\n"
    )
    result = parse_directives(content)
    assert result == []


def test_block_markers_inside_fence_ignored():
    content = (
        "```\n"
        ":<: ref\n"
        ':@: src="foo"\n'
        ":=:\n"
        "::: body\n"
        ":>:\n"
        "```\n"
    )
    result = parse_directives(content)
    assert result == []


def test_directive_after_closed_fence():
    content = (
        "```\n"
        ':-: ref src="inside"\n'
        "```\n"
        "\n"
        ':-: ref src="outside"\n'
    )
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].attrs == {"src": "outside"}


def test_longer_fence_required_to_close():
    """A fence opened with ```` requires at least 4 backticks to close."""
    content = (
        "````\n"
        ':-: ref src="inside"\n'
        "```\n"  # not enough to close
        ':-: ref src="still_inside"\n'
        "````\n"
    )
    result = parse_directives(content)
    assert result == []


# -- Unclosed block -----------------------------------------------------------


def test_unclosed_block_raises():
    content = ":<: ref\n:@: src=\"foo\""
    with pytest.raises(DirectiveError, match="line 1"):
        parse_directives(content)


def test_unclosed_block_in_body_raises():
    content = ":<: ref\n:=:\n::: body line"
    with pytest.raises(DirectiveError, match="line 1"):
        parse_directives(content)


# -- Name validation ----------------------------------------------------------


def test_valid_names_accepts_known():
    valid = {"ref", "code-test"}
    content = ':-: ref src="foo"'
    result = parse_directives(content, valid_names=valid)
    assert len(result) == 1


def test_valid_names_rejects_unknown():
    valid = {"ref", "code-test"}
    content = ':-: unknown-thing src="foo"'
    with pytest.raises(DirectiveError, match="Unknown directive 'unknown-thing'"):
        parse_directives(content, valid_names=valid)


def test_valid_names_rejects_unknown_block():
    valid = {"ref"}
    content = ":<: bad-name\n:>:"
    with pytest.raises(DirectiveError, match="Unknown directive 'bad-name'"):
        parse_directives(content, valid_names=valid)


def test_valid_names_none_accepts_anything():
    content = ':-: totally-made-up-name src="whatever"'
    result = parse_directives(content, valid_names=None)
    assert len(result) == 1
    assert result[0].name == "totally-made-up-name"


# -- Empty file ---------------------------------------------------------------


def test_empty_file():
    assert parse_directives("") == []


# -- Non-directive content ----------------------------------------------------


def test_non_directive_content():
    content = "# Heading\n\nSome paragraph.\n\n- list item\n"
    assert parse_directives(content) == []


# -- resolve_directives -------------------------------------------------------


def test_resolve_replaces_oneliner():
    content = (
        "# Title\n"
        "\n"
        ':-: ref src="selfdoc.config"\n'
        "\n"
        "Footer.\n"
    )

    def resolver(name, attrs, body):
        return f"[RESOLVED {name}: {attrs.get('src', '')}]"

    result = resolve_directives(content, resolver)
    assert "[RESOLVED ref: selfdoc.config]" in result
    assert ":-:" not in result
    assert "# Title" in result
    assert "Footer." in result


def test_resolve_replaces_block():
    content = (
        ":<: code-test\n"
        ':@: file="tests/test_foo.py"\n'
        ":>:\n"
    )

    def resolver(name, attrs, body):
        return f"[{name} file={attrs.get('file', '')}]"

    result = resolve_directives(content, resolver)
    assert "[code-test file=tests/test_foo.py]" in result
    assert ":<:" not in result


def test_resolve_passes_attrs_and_body():
    content = (
        ":<: callout-note\n"
        ':@: style="info"\n'
        ":=:\n"
        "::: Important note here.\n"
        ":>:\n"
    )
    captured = {}

    def resolver(name, attrs, body):
        captured["name"] = name
        captured["attrs"] = attrs
        captured["body"] = body
        return "replaced"

    resolve_directives(content, resolver)
    assert captured["name"] == "callout-note"
    assert captured["attrs"] == {"style": "info"}
    assert captured["body"] == ["Important note here."]


def test_resolve_non_directive_passthrough():
    content = "# Just markdown\n\nNo directives here.\n"

    def resolver(name, attrs, body):
        raise AssertionError("Should not be called")

    result = resolve_directives(content, resolver)
    assert result == content


def test_resolve_fence_passthrough():
    content = (
        "```\n"
        ':-: ref src="inside"\n'
        "```\n"
    )

    def resolver(name, attrs, body):
        raise AssertionError("Should not be called for fenced content")

    result = resolve_directives(content, resolver)
    assert ':-: ref src="inside"' in result


def test_resolve_with_valid_names():
    content = ':-: ref src="foo"'

    def resolver(name, attrs, body):
        return "ok"

    result = resolve_directives(content, resolver, valid_names={"ref"})
    assert result == "ok"


def test_resolve_unclosed_raises():
    content = ":<: ref"
    with pytest.raises(DirectiveError, match="Unclosed"):
        resolve_directives(content, lambda n, a, b: "")


# -- Error cases: unexpected lines in block -----------------------------------


def test_attr_after_body_sep_raises():
    """:@: after :=: is an error."""
    content = (
        ":<: ref\n"
        ":=:\n"
        ':@: src="foo"\n'
        ":>:"
    )
    with pytest.raises(DirectiveError, match="Unexpected line"):
        parse_directives(content)


def test_body_line_before_sep_raises():
    """::: before :=: is an error (in attrs state)."""
    content = (
        ":<: ref\n"
        "::: body without separator\n"
        ":>:"
    )
    with pytest.raises(DirectiveError, match="Unexpected line"):
        parse_directives(content)


def test_plain_text_in_block_attrs_raises():
    content = (
        ":<: ref\n"
        "just some random text\n"
        ":>:"
    )
    with pytest.raises(DirectiveError, match="Unexpected line"):
        parse_directives(content)


def test_plain_text_in_block_body_raises():
    content = (
        ":<: ref\n"
        ":=:\n"
        "text without ::: prefix\n"
        ":>:"
    )
    with pytest.raises(DirectiveError, match="Unexpected line"):
        parse_directives(content)


# -- Multiple attributes parsed correctly ------------------------------------


def test_multiple_attrs_on_one_line():
    content = ':-: ref src="a.py" lang="python" version="3"'
    result = parse_directives(content)
    assert result[0].attrs == {"src": "a.py", "lang": "python", "version": "3"}


# -- Directive dataclass has no 'arg' field -----------------------------------


def test_directive_has_no_arg_field():
    d = Directive(name="ref")
    assert not hasattr(d, "arg")
    assert hasattr(d, "attrs")


# -- Body line with empty content after prefix --------------------------------


def test_body_line_empty_after_prefix():
    content = (
        ":<: callout-note\n"
        ":=:\n"
        "::: \n"
        ":>:"
    )
    result = parse_directives(content)
    assert result[0].body == [""]


# -- Inline directives (pass 2) -----------------------------------------------


def test_inline_directive_basic():
    content = 'has :-: var key="x" features'

    def resolver(name, attrs, body):
        return f"[{name}:{attrs.get('key', '')}]"

    result = resolve_directives(content, resolver)
    assert result == "has [var:x] features"


def test_inline_directive_mid_sentence():
    content = 'The value is :-: version and more text.'

    def resolver(name, attrs, body):
        return "1.2.3"

    result = resolve_directives(content, resolver)
    assert result == "The value is 1.2.3 and more text."


def test_inline_multiple_per_line():
    content = 'A :-: foo then :-: bar end'

    def resolver(name, attrs, body):
        return f"[{name}]"

    result = resolve_directives(content, resolver)
    assert result == "A [foo] then [bar] end"


def test_standalone_not_affected():
    """Standalone :-: on its own line still works as before (pass 1)."""
    content = ':-: ref src="selfdoc.config"'

    def resolver(name, attrs, body):
        return f"[RESOLVED {name}: {attrs.get('src', '')}]"

    result = resolve_directives(content, resolver)
    assert result == "[RESOLVED ref: selfdoc.config]"


# -- Inline directives: code fence and backtick safety -------------------------


def test_inline_in_code_fence_not_resolved():
    """:-: inside a fenced code block is literal, not resolved."""
    content = (
        "```\n"
        'use :-: var key="x" here\n'
        "```\n"
    )

    def resolver(name, attrs, body):
        raise AssertionError("Should not be called for fenced content")

    result = resolve_directives(content, resolver)
    assert ':-: var key="x"' in result


def test_inline_in_backtick_span_not_resolved():
    """:-: inside a single-backtick code span is literal, not resolved."""
    content = 'see `:-: var key="x"` for details'

    def resolver(name, attrs, body):
        raise AssertionError("Should not be called for backtick span content")

    result = resolve_directives(content, resolver)
    assert result == 'see `:-: var key="x"` for details'


def test_inline_outside_backtick_resolved():
    """:-: outside backtick spans is resolved, backtick content is preserved."""
    content = 'text `code` then :-: var end'

    def resolver(name, attrs, body):
        return "[VAR]"

    result = resolve_directives(content, resolver)
    assert result == "text `code` then [VAR] end"


# -- Inline directives: multi-line output guard --------------------------------


def test_inline_multiline_output_error():
    """Inline directive returning multi-line output raises RuntimeError."""
    content = 'text :-: var end'

    def resolver(name, attrs, body):
        return "line1\nline2"

    with pytest.raises(RuntimeError, match="multi-line output"):
        resolve_directives(content, resolver)


# -- parse_directives: inline detection (Directive dataclass) ------------------


def test_parse_directives_finds_inline():
    """parse_directives returns inline directives with inline=True."""
    content = 'text :-: var end'
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].name == "var"
    assert result[0].inline is True
    assert result[0].body == []


def test_parse_directives_inline_has_column():
    """Column field is set correctly for inline directives."""
    content = 'prefix :-: var end'
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].column == 7  # "prefix " is 7 chars
    assert result[0].line_number == 1


def test_parse_directives_inline_in_fence_excluded():
    """Inline directives inside fenced code blocks are not detected."""
    content = (
        "```\n"
        'text :-: var end\n'
        "```\n"
    )
    result = parse_directives(content)
    assert result == []


def test_parse_directives_standalone_not_inline():
    """Standalone directives have inline=False and column=None."""
    content = ':-: ref src="foo"'
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].inline is False
    assert result[0].column is None


def test_parse_directives_mixed_standalone_and_inline():
    """Both standalone and inline directives are detected."""
    content = (
        ':-: ref src="foo"\n'
        'text :-: var end\n'
    )
    result = parse_directives(content)
    assert len(result) == 2
    assert result[0].name == "ref"
    assert result[0].inline is False
    assert result[1].name == "var"
    assert result[1].inline is True


def test_parse_directives_inline_with_attrs():
    """Inline directives parse attributes correctly."""
    content = 'see :-: var key="val" here'
    result = parse_directives(content)
    assert len(result) == 1
    assert result[0].attrs == {"key": "val"}
    assert result[0].inline is True


def test_parse_directives_inline_in_backtick_excluded():
    """Inline directives inside backtick spans are not detected."""
    content = 'see `:-: var` here'
    result = parse_directives(content)
    assert result == []


# -- Inline directives: double-backtick spans ----------------------------------


def test_inline_in_double_backtick_not_resolved():
    """:-: inside a double-backtick code span is literal, not resolved."""
    content = 'see ``:-: var key="x"`` for details'

    def resolver(name, attrs, body):
        raise AssertionError("Should not be called for double-backtick span content")

    result = resolve_directives(content, resolver)
    assert result == 'see ``:-: var key="x"`` for details'


def test_inline_outside_double_backtick_resolved():
    """:-: outside double-backtick spans is resolved, span content preserved."""
    content = 'text ``code`` then :-: var end'

    def resolver(name, attrs, body):
        return "[VAR]"

    result = resolve_directives(content, resolver)
    assert result == "text ``code`` then [VAR] end"


def test_mixed_single_double_backtick():
    """Both single and double backtick spans mask correctly on the same line."""
    content = '`single` and ``double :-: var`` then :-: ref end'

    def resolver(name, attrs, body):
        return "[RESOLVED]"

    result = resolve_directives(content, resolver)
    assert result == '`single` and ``double :-: var`` then [RESOLVED] end'


def test_parse_directives_inline_in_double_backtick_excluded():
    """Inline directives inside double-backtick spans are not detected."""
    content = 'see ``:-: var`` here'
    result = parse_directives(content)
    assert result == []


def test_parse_inline_directive_validates_name():
    """Inline directives must validate names against valid_names, like standalone ones."""
    content = "text :-: valid-name more text"
    with pytest.raises(DirectiveError, match="Unknown directive 'valid-name'"):
        parse_directives(content, valid_names={"other-name"})
