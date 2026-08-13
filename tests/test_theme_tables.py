"""Structural checks on how the themes present a table.

A table is emitted inside ``.table-wrap``, which sets ``overflow-x: auto``
and therefore becomes the table's scroll container.  A sticky ``thead``
offset from the top of *that* container is offset from the top of the
table, not from the topbar -- so the header row slides down over the first
body rows and overlaps them.  The offset only ever made sense when the
viewport was the scrollport, which it never is here.
"""

import re
from pathlib import Path

import pytest

from selfdoc.html import md_to_html

THEMES_DIR = Path(__file__).resolve().parent.parent / "selfdoc_core" / "themes"

THEMES = ("minimal.css", "clean.css")

#: The sticky ``thead`` rule body, per theme file.
_THEAD_RULE = re.compile(r"\bthead\s*\{([^}]*)\}", re.MULTILINE)


def _thead_rules(css: str) -> list[str]:
    return [m.group(1) for m in _THEAD_RULE.finditer(css)]


@pytest.fixture(scope="module", params=THEMES)
def theme_css(request) -> str:
    return (THEMES_DIR / request.param).read_text()


class TestStickyTableHeader:
    def test_the_theme_has_exactly_one_thead_rule(self, theme_css: str) -> None:
        assert len(_thead_rules(theme_css)) == 1

    def test_the_sticky_header_is_flush_with_its_scrollport(
        self, theme_css: str,
    ) -> None:
        """``top`` is 0: the scrollport is the wrapper, not the viewport."""
        body = _thead_rules(theme_css)[0]
        assert "position: sticky" in body
        assert re.search(r"top:\s*0;", body), body

    def test_no_topbar_compensation_survives_in_the_thead_rule(
        self, theme_css: str,
    ) -> None:
        """A pixel offset here is the viewport-topbar assumption returning."""
        body = _thead_rules(theme_css)[0]
        assert not re.search(r"top:\s*\d+px", body), body

    def test_the_wrapper_is_the_scrollport(self, theme_css: str) -> None:
        """The premise of the rule above: ``.table-wrap`` scrolls."""
        match = re.search(r"\.table-wrap\s*\{([^}]*)\}", theme_css)
        assert match, "no .table-wrap rule"
        assert "overflow-x: auto" in match.group(1)


class TestRenderedTableStructure:
    def test_a_rendered_table_sits_inside_the_wrapper(self) -> None:
        html = md_to_html(
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| alpha | 1 |\n"
        )
        assert '<div class="table-wrap">' in html
        assert "<thead>" in html
