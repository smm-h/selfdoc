"""A scrollable table says so at both edges.

``.table-wrap`` is the scrollport for a table wider than the column it sits
in, and a table wider than its wrapper clips mid-word at the edge.  Before
this, the only edge treatment was a fade toward the page background, which
at rest is the page background: nothing on screen said there was more table
to the right, and nothing ever said there was more to the left once the
reader had scrolled.

The affordance is a shadow at each edge, painted only while there is
content hidden on that side.  ``scroll-affordance.js`` owns the state --
``has-overflow`` while the content overflows at all, ``scrolled-start``
while the scrollport sits at its left edge, ``scrolled-end`` while it sits
at its right -- and the themes paint ``::before``/``::after`` off it.
"""

import re
from pathlib import Path

import pytest

from selfdoc_core.themes import get_theme, list_themes

JS = (
    Path(__file__).resolve().parent.parent
    / "selfdoc_core" / "js" / "scroll-affordance.js"
).read_text(encoding="utf-8")


@pytest.fixture(scope="module", params=list(list_themes()))
def theme_css(request) -> str:
    return get_theme(request.param)


class TestTheJSTracksBothEdges:
    def test_it_marks_the_left_edge(self) -> None:
        assert "scrolled-start" in JS

    def test_it_marks_the_right_edge(self) -> None:
        assert "scrolled-end" in JS

    def test_it_publishes_the_offset_of_a_self_scrolling_container(self) -> None:
        """An abspos child of a scroll container scrolls away with content.

        ``.table-wrap`` is its own scrollport, so its edge shadows would
        slide off the side they mark.  The offset is published for the
        theme to translate them back.
        """
        assert "--scroll-x" in JS
        assert "container === scroller" in JS

    def test_both_edge_classes_are_cleared_on_resize(self) -> None:
        """A re-measure that leaves a stale class paints a phantom shadow."""
        cleanup = re.search(r"classList\.remove\(([^)]*)\)", JS)
        assert cleanup, JS
        assert "scrolled-start" in cleanup.group(1)
        assert "scrolled-end" in cleanup.group(1)


class TestEveryThemePaintsBothEdges:
    def test_the_right_edge_is_painted(self, theme_css: str) -> None:
        assert re.search(
            r"\.table-wrap\.has-overflow::after\s*[,{]", theme_css,
        ), "no right-edge shadow on .table-wrap"

    def test_the_left_edge_is_painted(self, theme_css: str) -> None:
        assert re.search(
            r"\.table-wrap\.has-overflow::before\s*[,{]", theme_css,
        ), "no left-edge shadow on .table-wrap"

    def test_the_right_edge_stands_down_at_the_right_end(
        self, theme_css: str,
    ) -> None:
        assert ".table-wrap.scrolled-end::after" in theme_css

    def test_the_left_edge_stands_down_at_the_left_end(
        self, theme_css: str,
    ) -> None:
        assert ".table-wrap.scrolled-start::before" in theme_css

    def test_the_shadow_is_a_token(self, theme_css: str) -> None:
        """No theme states the shadow colour twice, once per mode."""
        assert "--scroll-shadow" in theme_css
        bodies = re.findall(
            r"\.table-wrap\.has-overflow::(?:before|after)[^{]*\{([^}]*)\}",
            theme_css,
        )
        assert bodies, theme_css
        painted = [b for b in bodies if "background:" in b]
        assert len(painted) == 2, painted
        for body in painted:
            assert "var(--scroll-shadow)" in body, body

    def test_the_edges_are_held_against_the_visible_box(
        self, theme_css: str,
    ) -> None:
        assert "translateX(var(--scroll-x, 0px))" in theme_css
