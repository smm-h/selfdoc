"""Tests for content directives (callouts and glossary)."""

from selfdoc.content import CONTENT_DIRECTIVES, resolve_content, resolve_glossary


# -- CONTENT_DIRECTIVES set ---------------------------------------------------


def test_content_directives_has_all_entries():
    """CONTENT_DIRECTIVES should contain all 14 content directive names."""
    expected = {
        "callout-note", "callout-warning", "callout-tip",
        "callout-danger", "callout-important", "list-glossary",
        "list-tree", "table-dep", "list-features",
        "list-modules", "table-commands", "table-directives",
        "table-config-schema", "var",
    }
    assert CONTENT_DIRECTIVES == expected


# -- Callout directives -------------------------------------------------------


def test_callout_note():
    result = resolve_content("callout-note", {}, ["This is a note."])
    assert '<div class="callout callout-note">' in result
    assert '<p class="callout-title">Note</p>' in result
    assert "<p>This is a note.</p>" in result
    assert "</div>" in result


def test_callout_warning():
    result = resolve_content("callout-warning", {}, ["Be careful."])
    assert '<div class="callout callout-warning">' in result
    assert '<p class="callout-title">Warning</p>' in result
    assert "<p>Be careful.</p>" in result


def test_callout_tip():
    result = resolve_content("callout-tip", {}, ["A helpful tip."])
    assert '<div class="callout callout-tip">' in result
    assert '<p class="callout-title">Tip</p>' in result
    assert "<p>A helpful tip.</p>" in result


def test_callout_danger():
    result = resolve_content("callout-danger", {}, ["Dangerous operation."])
    assert '<div class="callout callout-danger">' in result
    assert '<p class="callout-title">Danger</p>' in result
    assert "<p>Dangerous operation.</p>" in result


def test_callout_important():
    result = resolve_content("callout-important", {}, ["Read this first."])
    assert '<div class="callout callout-important">' in result
    assert '<p class="callout-title">Important</p>' in result
    assert "<p>Read this first.</p>" in result


def test_callout_empty_body():
    """A callout with empty body should produce the div with title but no body paragraph."""
    result = resolve_content("callout-note", {}, [])
    assert '<div class="callout callout-note">' in result
    assert '<p class="callout-title">Note</p>' in result
    assert "<p>" not in result.split("</p>", 1)[1]  # no body <p> after title
    assert "</div>" in result


def test_callout_multiline_body():
    """A callout with multi-line body should join lines with newlines."""
    body = ["Line one.", "Line two.", "Line three."]
    result = resolve_content("callout-warning", {}, body)
    assert '<div class="callout callout-warning">' in result
    assert '<p class="callout-title">Warning</p>' in result
    assert "<p>Line one.\nLine two.\nLine three.</p>" in result


# -- Glossary directive --------------------------------------------------------


def test_glossary_produces_correct_html():
    """list-glossary should produce HTML glossary output with dl/dt/dd."""
    result = resolve_content("list-glossary", {}, [
        "**Term1**: Definition one",
        "**Term2**: Definition two",
    ])
    assert '<div class="glossary">' in result
    assert "<dt><dfn>Term1</dfn></dt>" in result
    assert "<dd>Definition one</dd>" in result
    assert "<dt><dfn>Term2</dfn></dt>" in result
    assert "<dd>Definition two</dd>" in result


def test_glossary_empty_body():
    """list-glossary with empty body should produce empty glossary."""
    result = resolve_content("list-glossary", {}, [])
    assert result == '<div class="glossary"><dl></dl></div>'


def test_glossary_term_without_definition():
    """A glossary entry with no ': ' separator should have an empty definition."""
    result = resolve_content("list-glossary", {}, ["**Solo**"])
    assert "<dt><dfn>Solo</dfn></dt>" in result
    assert "<dd></dd>" in result


def test_glossary_skips_blank_lines():
    """Blank lines in the glossary body should be skipped."""
    result = resolve_content("list-glossary", {}, [
        "**A**: Alpha",
        "",
        "**B**: Beta",
    ])
    assert "<dt><dfn>A</dfn></dt>" in result
    assert "<dt><dfn>B</dfn></dt>" in result


def test_resolve_glossary_directly():
    """resolve_glossary function should be callable directly."""
    result = resolve_glossary(["**X**: cross"])
    assert "<dt><dfn>X</dfn></dt>" in result
    assert "<dd>cross</dd>" in result


# -- Unknown directives -------------------------------------------------------


def test_unknown_directive_returns_none():
    """resolve_content should return None for unknown directive names."""
    assert resolve_content("ref", {}, []) is None
    assert resolve_content("code-test", {}, []) is None
    assert resolve_content("nonexistent", {}, ["body"]) is None
