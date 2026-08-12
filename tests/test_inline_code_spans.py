"""How many backticks a code span opens with, and what the renderer does.

CommonMark lets a code span be delimited by any run of backticks, closed
by a run of the same length: ``x`` is one span, not two empty ones.  The
longer form is what a writer reaches for when the code itself contains a
backtick -- and it is also the form RST-trained writers use by habit, so
it turns up throughout docstrings and doc comments across the fleet.

The rest of selfdoc already reads the longer form correctly: the mask the
spell checker and the directive scanner share matches a run of any length
against a closing run of the same length.  Only the renderer disagreed,
splitting on single backticks, so ``x`` came out as two empty ``<code>``
pairs with the text loose between them -- unmarked in the page and, worse,
silently accepted by a spell checker that had already decided it was code.
"""

from __future__ import annotations

import pytest

from selfdoc.html import md_to_html


def _body(markdown):
    return md_to_html(markdown)


@pytest.mark.parametrize("ticks", ["`", "``", "```"])
def test_a_span_of_any_delimiter_length_is_one_code_element(ticks):
    html = _body(f"Reap the {ticks}returncode{ticks} here.")
    assert html.count("<code>") == 1
    assert "<code>returncode</code>" in html


def test_a_double_tick_span_leaves_no_empty_code_elements():
    """The exact defect: two empty pairs around unmarked text."""
    html = _body("Reap the ``returncode`` here.")
    assert "<code></code>" not in html


def test_a_double_tick_span_can_hold_a_backtick():
    """Which is the reason the longer delimiter exists at all."""
    html = _body("Write ``a ` b`` for that.")
    assert "<code>a ` b</code>" in html


def test_one_space_each_side_is_stripped():
    """CommonMark's rule for spanning a literal backtick at an edge."""
    html = _body("Write `` ` `` for that.")
    assert "<code>`</code>" in html


def test_interior_spaces_survive():
    html = _body("Write ``a  b`` for that.")
    assert "<code>a  b</code>" in html


def test_content_is_escaped_and_not_formatted():
    html = _body("Look at ``<b>**x**</b>`` here.")
    assert "<code>&lt;b&gt;**x**&lt;/b&gt;</code>" in html
    assert "<strong>" not in html


def test_prose_around_a_span_is_still_formatted():
    html = _body("A **bold** word, ``code``, and [a link](https://example.com).")
    assert "<strong>bold</strong>" in html
    assert "<code>code</code>" in html
    assert '<a href="https://example.com">a link</a>' in html


def test_an_unclosed_run_is_literal_text():
    """Nothing closes it, so there is no span -- and no stray element."""
    html = _body("A stray `` tick.")
    assert "<code>" not in html
