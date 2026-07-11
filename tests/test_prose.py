"""Tests for the shared prose unit-pickers (selfdoc_core.prose).

Pins the single sentence-boundary semantics used everywhere: no character
caps, no ellipses, no synthesized punctuation.
"""

from selfdoc_core.prose import (
    first_paragraph,
    first_sentence,
    join_wrapped_lines,
)


class TestFirstSentence:
    def test_basic_period(self):
        assert first_sentence("Hello world. More text.") == "Hello world."

    def test_exclamation(self):
        assert first_sentence("Watch out! Then relax.") == "Watch out!"

    def test_question(self):
        assert first_sentence("Ready? Set. Go.") == "Ready?"

    def test_no_terminator_returns_whole_paragraph(self):
        # No caps, no synthesized period -- whole unit returned unchanged.
        assert first_sentence("Just some words here") == "Just some words here"

    def test_does_not_split_decimal(self):
        assert first_sentence("Pi is 3.14 exactly. Next.") == "Pi is 3.14 exactly."

    def test_does_not_split_version(self):
        assert first_sentence("Requires v1.0 or newer. Also.") == (
            "Requires v1.0 or newer."
        )

    def test_abbreviation_eg(self):
        assert first_sentence("See e.g. the docs. Done.") == (
            "See e.g. the docs."
        )

    def test_abbreviation_ie(self):
        assert first_sentence("The core, i.e. the engine, runs. Yes.") == (
            "The core, i.e. the engine, runs."
        )

    def test_abbreviation_etc(self):
        assert first_sentence("Apples, oranges, etc. are fruit. Ok.") == (
            "Apples, oranges, etc. are fruit."
        )

    def test_abbreviation_vs(self):
        assert first_sentence("Cats vs. dogs is old. Next.") == (
            "Cats vs. dogs is old."
        )

    def test_abbreviation_title(self):
        assert first_sentence("Ask Dr. Smith today. Later.") == (
            "Ask Dr. Smith today."
        )

    def test_no_synthesized_punctuation(self):
        # Terminator present but no whitespace after -> no boundary; and no
        # period is ever appended.
        assert first_sentence("word") == "word"

    def test_operates_on_first_paragraph_only(self):
        text = "First para start. First para end.\n\nSecond paragraph."
        assert first_sentence(text) == "First para start."

    def test_empty(self):
        assert first_sentence("") == ""

    def test_terminator_at_end_of_text(self):
        assert first_sentence("Only one sentence.") == "Only one sentence."


class TestFirstParagraph:
    def test_single_paragraph(self):
        assert first_paragraph("Line one. Line two.") == "Line one. Line two."

    def test_joins_soft_wrapped_lines(self):
        text = "This paragraph is\nwrapped across three\nphysical lines."
        assert first_paragraph(text) == (
            "This paragraph is wrapped across three physical lines."
        )

    def test_stops_at_blank_line(self):
        text = "First paragraph line one.\nline two.\n\nSecond paragraph."
        assert first_paragraph(text) == (
            "First paragraph line one. line two."
        )

    def test_skips_leading_blank_lines(self):
        assert first_paragraph("\n\nActual content.") == "Actual content."

    def test_empty(self):
        assert first_paragraph("") == ""

    def test_no_length_cap(self):
        long_para = " ".join(["word"] * 200)
        assert first_paragraph(long_para) == long_para


class TestJoinWrappedLines:
    def test_joins_wrapped_paragraph(self):
        text = "Package config manages the\nloading of configuration from\ndisk."
        assert join_wrapped_lines(text) == (
            "Package config manages the loading of configuration from disk."
        )

    def test_preserves_blank_line_paragraph_break(self):
        text = "First paragraph\nwrapped.\n\nSecond paragraph\nwrapped."
        assert join_wrapped_lines(text) == (
            "First paragraph wrapped.\n\nSecond paragraph wrapped."
        )

    def test_leaves_fenced_code_verbatim(self):
        text = "Intro line\ncontinues.\n\n```\ncode line 1\ncode line 2\n```"
        result = join_wrapped_lines(text)
        assert "Intro line continues." in result
        assert "code line 1\ncode line 2" in result

    def test_leaves_indented_preformatted_verbatim(self):
        text = "Example usage below:\n\n    go run main.go\n    ./binary"
        result = join_wrapped_lines(text)
        assert "    go run main.go\n    ./binary" in result

    def test_leaves_list_items_verbatim(self):
        text = "Features:\n\n- item one\n- item two"
        result = join_wrapped_lines(text)
        assert "- item one\n- item two" in result

    def test_leaves_doctest_verbatim(self):
        text = "Example.\n\n>>> f(1)\n2"
        result = join_wrapped_lines(text)
        assert ">>> f(1)" in result

    def test_idempotent(self):
        joined = "A single already-joined sentence."
        assert join_wrapped_lines(joined) == joined

    def test_empty(self):
        assert join_wrapped_lines("") == ""

    def test_go_wrapped_first_sentence_then_first_sentence(self):
        # A wrapped Go-style package comment: first sentence spans lines.
        text = (
            "Package config loads and validates the tool's configuration\n"
            "from disk, applying defaults and reporting errors clearly."
        )
        normalized = join_wrapped_lines(text)
        assert first_sentence(normalized) == (
            "Package config loads and validates the tool's configuration "
            "from disk, applying defaults and reporting errors clearly."
        )
