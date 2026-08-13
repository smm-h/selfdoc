"""The curated project cards render in the framework's card vocabulary.

The listing is one fragment shared by two surfaces -- the front page's
``projects-cards`` directive and the generated ``/projects/`` page -- so
everything asserted here holds on both by construction.

The regression this file pins down: the fragment used to emit
``.project-card`` articles and a ``.version-badge`` span that no theme
styled, so every card painted as a full-width unstyled box with the version
as body text and the repository as a bare link.  The cards are now stated in
the classes the themes really carry -- ``.card-grid``/``.card`` for the grid
and the box, ``.badge`` for the version chip -- with the selfdoc-specific
hooks riding alongside for the rules only a project card needs.
"""

import re

import pytest

from selfblog.listing import parse_listing, render_listing_html
from selfdoc_core.themes import get_theme, list_themes

LISTING = (
    '[[category]]\nname = "Developer tools"\n'
    '[[category.project]]\nslug = "alpha"\nblurb = "Does the alpha thing."\n'
    'repo = "https://github.com/someone/alpha"\n'
    '[[category.project]]\nslug = "out"\nname = "Outside"\nblurb = "Elsewhere."\n'
    'url = "https://example.org/outside"\n'
)


def _manifest(slug, name, version):
    return {"slug": slug, "name": name, "version": version}


@pytest.fixture(scope="module")
def listing_html() -> str:
    return render_listing_html(
        parse_listing(LISTING),
        [_manifest("alpha", "Alpha", "1.0.0")],
        "",
        home_slug="home",
    )


class TestTheCardsAreAGrid:
    def test_each_category_holds_a_card_grid(self, listing_html: str) -> None:
        assert 'class="card-grid project-grid"' in listing_html

    def test_a_card_is_the_frameworks_card(self, listing_html: str) -> None:
        assert 'class="card project-card"' in listing_html

    def test_the_title_is_a_card_title_in_its_row(self, listing_html: str) -> None:
        assert 'class="card-title-row"' in listing_html
        assert 'class="card-title"' in listing_html


class TestTheVersionIsABadge:
    def test_the_version_is_stamped_as_a_badge_chip(self, listing_html: str) -> None:
        assert (
            '<span class="badge badge-neutral version-badge">v1.0.0</span>'
            in listing_html
        )

    def test_the_external_marker_is_a_badge_too(self, listing_html: str) -> None:
        assert 'class="badge badge-neutral external-badge"' in listing_html

    def test_badges_sit_in_the_frameworks_badge_row(self, listing_html: str) -> None:
        assert 'class="card-badges"' in listing_html


class TestTheRepositoryIsAnAffordance:
    def test_the_repository_link_keeps_its_hook(self, listing_html: str) -> None:
        assert 'class="project-repo"' in listing_html

    def test_the_repository_link_names_its_destination(
        self, listing_html: str,
    ) -> None:
        """A bare word "Repository" reads as text; the arrow reads as a link."""
        assert re.search(
            r'class="project-repo"[^>]*>Repository\s*<span aria-hidden="true">',
            listing_html,
        ), listing_html


@pytest.fixture(scope="module", params=list(list_themes()))
def theme_css(request) -> str:
    """The composed stylesheet, framework sheets included."""
    return get_theme(request.param)


class TestEveryThemeStylesTheCards:
    """A class no theme styles is the defect that produced this file."""

    def test_the_grid_is_a_grid(self, theme_css: str) -> None:
        bodies = re.findall(r"\.project-grid\s*\{([^}]*)\}", theme_css)
        assert bodies, "no .project-grid rule"
        joined = "\n".join(bodies)
        assert "grid-template-columns" in joined or "grid-auto-rows" in joined

    def test_the_grid_holds_more_than_one_column(self, theme_css: str) -> None:
        """One card per row is the regression; the columns are responsive."""
        joined = "\n".join(re.findall(r"\.project-grid\s*\{([^}]*)\}", theme_css))
        assert "repeat(auto-fill" in joined or "grid-auto-rows: auto" in joined

    def test_the_card_box_is_styled(self, theme_css: str) -> None:
        assert re.search(r"\.project-card[\s,{]", theme_css), (
            "no .project-card rule"
        )

    def test_the_repository_link_is_styled(self, theme_css: str) -> None:
        assert re.search(r"\.project-repo[\s,:{]", theme_css), (
            "no .project-repo rule"
        )
