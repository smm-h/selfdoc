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
from selfdoc_core.themes import get_theme, list_themes

THEMES_DIR = Path(__file__).resolve().parent.parent / "selfdoc_core" / "themes"

# Registry-driven: a theme added without these rules is a theme whose
# sticky header overlaps its own first rows, and the suite should say so
# without anybody remembering to extend a tuple.
THEMES = tuple(f"{name}.css" for name in list_themes())

#: The sticky ``thead`` rule body, in either spelling: the whole row group
#: or the header cells inside it.  A framework theme states it the second
#: way, and both make the header stick.
_THEAD_RULE = re.compile(
    r"(?:^|[,\s])(?:\.tm-table\s+)?thead(?:\s+th)?\s*\{([^}]*)\}",
    re.MULTILINE,
)


def _thead_rules(css: str) -> list[str]:
    return [m.group(1) for m in _THEAD_RULE.finditer(css)]


#: The unit is the **composed** stylesheet, not the theme file.  A theme
#: that declares a framework ships as an overlay on someone else's sheets,
#: and the sticky header is one of the things it stops restating -- reading
#: the overlay alone would report the rule as missing when what happened is
#: that the framework now carries it.
@pytest.fixture(scope="module", params=[n for n in list_themes()])
def theme_css(request) -> str:
    return get_theme(request.param)


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


class TestEmptyParagraphs:
    """A directive's block element leaves empty paragraphs around it.

    ``<p><div class="callout">...</div></p>`` parses as an empty paragraph,
    the div, and another empty paragraph.  Both carry the paragraph margin
    and space out content that is not there.
    """

    def test_the_theme_hides_them(self, theme_css: str) -> None:
        rule = re.search(r"p:empty\s*\{([^}]*)\}", theme_css)
        assert rule, "no p:empty rule"
        assert "display: none" in rule.group(1)
