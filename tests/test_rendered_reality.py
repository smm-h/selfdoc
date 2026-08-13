"""Rendered reality: the built site, in a real browser, asserted as painted.

**The pipeline is never mocked.**  That is the design principle of this
suite, and it is not negotiable: every page asserted below was produced by
:func:`~selfblog.assembly.build_source_project`,
:func:`~selfblog.assembly.split_build_output`,
:func:`~selfblog.assembly.generate_shared_files` and a real Pagefind index,
grafted into a real assembly tree and served by the production preview
server.  Dependency injection is for genuine external seams -- the network,
the clock, another repository -- and for nothing else.  A suite that
rendered through a second implementation would be a picture of something
that is not going to be published, which is worse than no picture at all.

The suite exists because mocked-flow tests are how visual defects shipped.
Six of them reached readers while 4,600 unit tests and every grep-level
check passed:

1. a sticky table header that overlapped the first data row,
2. a table of contents visible only inside one band of viewport widths,
3. a shared page served with no stylesheet at all,
4. a duplicated "Last updated" element,
5. absolute links that walked the reader off the site,
6. a glossary term that no page had ever defined.

Not one of those is visible to a test that asserts on a string of HTML.
Every one is obvious to a browser.  Each test below names the defect class
it stands for.

Two trees are built and served, because a project has two published
shapes and they differ in what they carry: the **assembled site**, where
every project is mounted under its slug and only its current version is
published, and the **standalone site** a project deploys on its own, which
is where the archive under ``v/<version>/`` lives.

Run just this suite with ``-m e2e_rendered``; run everything else with
``-m 'not e2e_rendered'``.
"""

from __future__ import annotations

import collections
import os

import pytest

from selfdoc_core.themes import theme_framework as _theme_framework

from rendered_site import (
    ALLOWED_EXTERNAL,
    EXTERNAL_ALLOWLIST,
    build_fixture_site,
    build_standalone_project,
    serve,
)

pytestmark = pytest.mark.e2e_rendered

#: Every theme the toolchain ships.  Kept in step with
#: ``selfdoc_core.themes.list_themes`` by a fixture guard below rather than
#: by memory: a theme that ships without joining the sweep is a theme
#: nothing looks at.
THEMES = ["clean", "minimal", "tinymoon"]

#: The widths the layout sweep visits, in order -- the monotonicity
#: assertion reads them as a series.
WIDTHS = [700, 1000, 1280, 1440, 1920]

#: One address per page class the assembled site serves.  The suite asserts
#: against page *classes*, not against pages, so a class nobody listed here
#: is a class the browser never looks at.
ASSEMBLY_PAGES = {
    "home": "/",
    "docs": "/alpha/",
    "docs-tables": "/alpha/tables/",
    "docs-terms": "/alpha/terms/",
    "docs-glossary": "/alpha/glossary/",
    "docs-unversioned": "/beta/",
    "post": "/blog/the-first-post/",
    "shared-projects": "/projects/",
    "shared-blog": "/blog/",
    "cv": "/cv/",
}

#: The page classes only a project's own standalone site carries.
STANDALONE_PAGES = {
    "standalone-current": "/",
    "standalone-archive": "/v/0.1.0/",
}

#: Every page class, wherever it is served from.
ALL_PAGES = sorted(ASSEMBLY_PAGES) + sorted(STANDALONE_PAGES)

#: The page classes that carry a documentation table of contents.  A post
#: reads top to bottom and carries none at any width -- defect 2.
TOC_PAGES = [
    "docs", "docs-tables", "docs-terms", "docs-unversioned",
    "standalone-current", "standalone-archive",
]


# -- the one build per theme --------------------------------------------------------


class Fixture:
    """The two served trees of one theme's fixture site."""

    def __init__(self, theme, assembly, standalone):
        self.theme = theme
        self.assembly = assembly
        self.standalone = standalone


@pytest.fixture(scope="session", params=THEMES)
def fixture(request, tmp_path_factory):
    """One real assembly plus one real standalone site, per theme.

    Session-scoped and parametrized, so each theme's trees are built
    exactly once and every test in that theme's sweep looks at the same
    bytes.  Building is the expensive part -- three documentation builds,
    a graft, the shared generation and two Pagefind runs per theme -- and
    it happens three times per session rather than once per test.
    """
    theme = request.param
    root = tmp_path_factory.mktemp(f"rendered-{theme}")
    summary = build_fixture_site(str(root), theme)
    standalone_dir = build_standalone_project(str(root), theme)
    with serve(summary["site_dir"], theme) as assembly:
        with serve(standalone_dir, theme) as standalone:
            yield Fixture(theme, assembly, standalone)


@pytest.fixture()
def page(chromium_browser, fixture):
    """A fresh browser context per test, off conftest's one browser.

    The browser is shared for the whole suite -- Playwright's sync API
    allows exactly one open launcher -- and the isolation that matters is
    the context: each test gets its own localStorage, so a dismissed
    notice or a stored theme choice never leaks into the next one.
    """
    context = chromium_browser.new_context(
        viewport={"width": 1280, "height": 900},
    )
    pg = context.new_page()
    yield pg
    context.close()


# -- helpers ------------------------------------------------------------------------


#: The allowlist, normalized the way the collected hrefs are.
_ALLOWED = {url.rstrip("/") for url in EXTERNAL_ALLOWLIST}


def _served(fixture, label):
    """The tree *label* is served from, and its path on that tree."""
    if label in ASSEMBLY_PAGES:
        return fixture.assembly, ASSEMBLY_PAGES[label]
    return fixture.standalone, STANDALONE_PAGES[label]


def _open(pg, fixture, label):
    """Navigate to the page class *label*, wherever it is served from."""
    site, path = _served(fixture, label)
    response = pg.goto(site.url(path), wait_until="load")
    assert response is not None and response.ok, (
        f"[{fixture.theme}] {label} ({path}) answered "
        f"{response.status if response else 'nothing'}"
    )
    return site


def _goto(pg, site, path):
    response = pg.goto(site.url(path), wait_until="load")
    assert response is not None and response.ok, (
        f"{path} answered {response.status if response else 'nothing'}"
    )
    return response


def _boxes_intersect(a, b, *, tolerance=0.5):
    """Whether two bounding boxes overlap by more than *tolerance* pixels."""
    if a is None or b is None:
        return False
    return (
        a["x"] < b["x"] + b["width"] - tolerance
        and b["x"] < a["x"] + a["width"] - tolerance
        and a["y"] < b["y"] + b["height"] - tolerance
        and b["y"] < a["y"] + a["height"] - tolerance
    )


def _settle_animations(pg):
    """Wait for every finite animation to finish.

    tinymoon's precedent: a computed style sampled mid-fade is the
    composite of the element over whatever is behind it, which turns a
    passing contrast ratio into a failing one at random.  Infinite
    animations are skipped so this can never hang.
    """
    pg.evaluate(
        """() => Promise.all(
            document.getAnimations()
              .filter(a => {
                  const t = a.effect && a.effect.getTiming();
                  return t && t.iterations !== Infinity;
              })
              .map(a => a.finished.catch(() => {}))
        )"""
    )


def _visible_count(pg, selector):
    """How many elements matching *selector* the browser actually paints."""
    return pg.evaluate(
        """(sel) => Array.from(document.querySelectorAll(sel)).filter(el => {
            const style = getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            if (parseFloat(style.opacity) === 0) return false;
            const box = el.getBoundingClientRect();
            return box.width > 0 && box.height > 0;
        }).length""",
        selector,
    )


# -- 1. sticky table headers ----------------------------------------------------------


#: The width the table assertions run at. The fixture table overflows its
#: wrapper here in every theme -- the fixture guard below asserts exactly
#: that, so none of these can pass by having nothing to scroll.
TABLE_WIDTH = 700


def _scroll_page_to(page, top):
    """Scroll the document to *top* and wait until it has arrived.

    The pages set ``scroll-behavior: smooth``, so ``window.scrollTo``
    starts an animation rather than moving the document, and a geometry
    reading taken a fixed number of milliseconds later is a reading of
    some frame in the middle of it -- a layout no reader ever sees.  What
    every assertion here is about is the layout at rest, so the animation
    is turned off for the jump and the arrival is waited for.

    (The animation only started happening once the block that re-enables
    smooth scrolling stopped being commented out by the JS minifier.
    Before that it was suppressed on every page from load onwards, which
    is why a fixed 40ms wait used to be enough.)
    """
    page.evaluate(
        """(t) => {
            document.documentElement.style.scrollBehavior = 'auto';
            window.scrollTo(0, t);
        }""",
        top,
    )
    page.wait_for_function(
        "(t) => Math.abs(window.scrollY - t) < 2"
        " || window.scrollY >= document.documentElement.scrollHeight"
        " - window.innerHeight - 2",
        arg=top,
        timeout=5000,
    )


class TestStickyTables:
    """Defect 1: a sticky ``thead`` that overlapped the first data row.

    The header sticks against the table's own scrolling box
    (``.table-wrap``) rather than against the viewport -- the offset it
    used to carry was a topbar's height, which pushed it down over the
    first body rows. The only way to see that is to scroll the box and the
    page and measure what the browser painted.
    """

    def _table_page(self, page, fixture):
        _open(page, fixture, "docs-tables")
        page.set_viewport_size({"width": TABLE_WIDTH, "height": 900})
        page.wait_for_timeout(80)
        wrap = page.locator(".table-wrap").first
        wrap.wait_for(state="visible")
        return wrap

    def test_the_header_never_covers_the_first_row(self, page, fixture):
        """Scroll the box and the page; the header must never sit on a row."""
        wrap = self._table_page(page, fixture)
        head = page.locator(".table-wrap thead tr").first
        first_row = page.locator(".table-wrap tbody tr").first

        overlaps = []
        for box_top in (0, 60, 200, 600):
            for page_top in (0, 120, 400, 900):
                wrap.evaluate("(el, t) => { el.scrollTop = t; }", box_top)
                _scroll_page_to(page, page_top)
                head_box = head.bounding_box()
                row_box = first_row.bounding_box()
                if _boxes_intersect(head_box, row_box):
                    overlaps.append((box_top, page_top, head_box, row_box))

        assert not overlaps, (
            f"[{fixture.theme}] the sticky table header overlapped the first "
            f"data row at (box, page) scroll offsets "
            f"{[(a, b) for a, b, _, _ in overlaps]}: {overlaps[:2]}"
        )

    def test_the_header_cells_stay_over_their_columns_when_scrolled_sideways(
        self, page, fixture,
    ):
        """A header that does not travel with its column is unreadable."""
        wrap = self._table_page(page, fixture)
        drift = wrap.evaluate(
            """(el) => {
                const col = 4;
                const head = el.querySelector(
                    `thead tr th:nth-child(${col})`);
                const cell = el.querySelector(
                    `tbody tr td:nth-child(${col})`);
                el.scrollLeft = 0;
                const before = head.getBoundingClientRect().x
                             - cell.getBoundingClientRect().x;
                el.scrollLeft = Math.floor(
                    (el.scrollWidth - el.clientWidth) / 2);
                const after = head.getBoundingClientRect().x
                            - cell.getBoundingClientRect().x;
                return {before, after, scrolled: el.scrollLeft};
            }"""
        )
        assert abs(drift["after"] - drift["before"]) < 1, (
            f"[{fixture.theme}] a header cell drifted {drift} away from the "
            f"column it labels when the table scrolled sideways"
        )

    def test_the_pinned_first_column_stays_on_top_when_scrolled_sideways(
        self, page, fixture,
    ):
        """The pinned column overlaps the row it pins -- and must paint above it.

        A sticky first column is *supposed* to have the rest of the row
        slide under it; that is the feature. What must not happen is the
        row painting over the pinned cell, which is the same defect as the
        sticky header overlap read along the other axis. So the assertion
        is on paint order at the cell's own centre, not on geometry.
        """
        wrap = self._table_page(page, fixture)
        wrap.evaluate("(el) => { el.scrollLeft = el.scrollWidth; }")
        page.wait_for_timeout(80)
        topmost = page.evaluate(
            """() => {
                const cell = document.querySelector(
                    '.table-wrap tbody tr td:first-child');
                const box = cell.getBoundingClientRect();
                const hit = document.elementFromPoint(
                    box.x + box.width / 2, box.y + box.height / 2);
                return {
                    inside: !!hit && (hit === cell || cell.contains(hit)),
                    hit: hit ? hit.className || hit.tagName : null,
                };
            }"""
        )
        assert topmost["inside"], (
            f"[{fixture.theme}] with the table scrolled fully sideways, the "
            f"element painted at the centre of the first column's cell is "
            f"{topmost['hit']!r} -- another column is covering it"
        )


# -- 2. one date -----------------------------------------------------------------------


class TestOneDate:
    """Defect 4: a page that rendered its "Last updated" element twice."""

    @pytest.mark.parametrize("label", ALL_PAGES)
    def test_every_page_shows_at_most_one_last_updated(
        self, page, fixture, label,
    ):
        """No page paints two "Last updated" elements."""
        _open(page, fixture, label)
        painted = page.evaluate(
            """() => Array.from(
                    document.querySelectorAll('.page-meta span, .cv-updated'))
                .filter(el => /last updated/i.test(el.textContent || ''))
                .filter(el => {
                    const s = getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden';
                })
                .map(el => (el.textContent || '').trim())"""
        )
        assert len(painted) <= 1, (
            f"[{fixture.theme}] {label} painted {len(painted)} "
            f"'Last updated' elements: {painted}"
        )

    def test_a_documentation_page_shows_exactly_one(self, page, fixture):
        """A page with a date shows it once -- not zero times, not twice."""
        _open(page, fixture, "docs")
        painted = page.evaluate(
            """() => Array.from(document.querySelectorAll('.page-meta span'))
                .filter(el => /last updated/i.test(el.textContent || '')).length"""
        )
        assert painted == 1, (
            f"[{fixture.theme}] a documentation page painted {painted} "
            f"'Last updated' elements; exactly one is right"
        )


# -- 3. table of contents consistency ---------------------------------------------------


class TestTableOfContents:
    """Defect 2: a table of contents visible only inside a band of widths.

    The desktop aside and the mobile disclosure are the same feature at two
    widths.  Suppressing only one of them left a table of contents that
    appeared below 1280px and nowhere else, which no unit test could see:
    both elements were in the HTML either way.
    """

    @pytest.mark.parametrize("label", TOC_PAGES)
    def test_exactly_one_variant_is_visible_at_every_width(
        self, page, fixture, label,
    ):
        """Wide or narrow, one variant shows -- never both, never neither."""
        _open(page, fixture, label)
        seen = {}
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(60)
            seen[width] = (
                _visible_count(page, "aside.toc"),
                _visible_count(page, "details.mobile-toc"),
            )

        missing = [w for w, (desk, mob) in seen.items() if desk + mob == 0]
        doubled = [w for w, (desk, mob) in seen.items() if desk and mob]
        assert not missing, (
            f"[{fixture.theme}] {label} showed no table of contents at "
            f"{missing} -- the readings were {seen}"
        )
        assert not doubled, (
            f"[{fixture.theme}] {label} showed both the desktop aside and the "
            f"mobile disclosure at {doubled} -- the readings were {seen}"
        )

    @pytest.mark.parametrize("label", TOC_PAGES)
    def test_the_aside_is_the_wide_variant_and_the_disclosure_the_narrow_one(
        self, page, fixture, label,
    ):
        _open(page, fixture, label)
        page.set_viewport_size({"width": 1920, "height": 900})
        page.wait_for_timeout(60)
        assert _visible_count(page, "aside.toc") == 1, (
            f"[{fixture.theme}] {label} has no desktop table of contents at 1920px"
        )
        page.set_viewport_size({"width": 700, "height": 900})
        page.wait_for_timeout(60)
        assert _visible_count(page, "aside.toc") == 0, (
            f"[{fixture.theme}] {label} still shows the desktop aside at 700px"
        )
        assert _visible_count(page, "details.mobile-toc") == 1, (
            f"[{fixture.theme}] {label} has no mobile table of contents at 700px"
        )

    def test_a_post_has_no_table_of_contents_at_any_width(self, page, fixture):
        """A post carries neither variant at any width -- the whole of defect 2."""
        _open(page, fixture, "post")
        offenders = {}
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(60)
            desk = _visible_count(page, "aside.toc")
            mob = _visible_count(page, "details.mobile-toc")
            if desk or mob:
                offenders[width] = (desk, mob)
        assert not offenders, (
            f"[{fixture.theme}] a post rendered a table of contents at {offenders}"
        )

    def test_a_post_carries_no_toc_element_in_the_dom_at_all(self, page, fixture):
        """Not merely hidden: a post's HTML has no table-of-contents element.

        Hiding one variant with CSS at one breakpoint is exactly how the
        band-limited table of contents came about.
        """
        _open(page, fixture, "post")
        present = page.evaluate(
            "() => document.querySelectorAll('aside.toc, details.mobile-toc').length"
        )
        assert present == 0, (
            f"[{fixture.theme}] a post carries {present} table-of-contents "
            f"element(s) in its DOM"
        )


# -- 4. styles applied --------------------------------------------------------------------


class TestStylesApplied:
    """Defect 3: a shared page served with no stylesheet at all.

    The page was valid HTML with a ``<link>`` in it; the link named an
    address the assembled site does not carry.  Only a browser that
    fetched it knows.
    """

    @pytest.mark.parametrize("label", ALL_PAGES)
    def test_no_stylesheet_the_page_names_fails_to_load(
        self, page, fixture, label,
    ):
        """Network capture: every stylesheet request must succeed."""
        failures = []
        page.on(
            "response",
            lambda r: failures.append((r.url, r.status))
            if r.status >= 400
            and (r.request.resource_type == "stylesheet" or r.url.endswith(".css"))
            else None,
        )
        _open(page, fixture, label)
        page.wait_for_load_state("networkidle")

        declared = page.evaluate(
            """() => Array.from(
                document.querySelectorAll('link[rel~="stylesheet"]')
            ).map(l => l.href)"""
        )
        assert declared, f"[{fixture.theme}] {label} declares no stylesheet at all"
        assert not failures, (
            f"[{fixture.theme}] {label} names stylesheet(s) that do not "
            f"resolve: {failures}"
        )

    @pytest.mark.parametrize("label", ALL_PAGES)
    def test_the_computed_body_style_is_not_the_browser_default(
        self, page, fixture, label,
    ):
        """A page whose stylesheet never applied looks exactly like the opposite of this."""
        _open(page, fixture, label)
        page.wait_for_load_state("networkidle")
        computed = page.evaluate(
            """() => {
                const s = getComputedStyle(document.body);
                return {background: s.backgroundColor, font: s.fontFamily};
            }"""
        )
        # An unstyled Chromium body is transparent and set in Times.
        assert computed["background"] not in ("rgba(0, 0, 0, 0)", ""), (
            f"[{fixture.theme}] {label} has a transparent body background -- "
            f"its stylesheet did not apply: {computed}"
        )
        assert "Times" not in computed["font"], (
            f"[{fixture.theme}] {label} renders in the browser's default "
            f"serif -- its stylesheet did not apply: {computed}"
        )

    def test_the_shared_pages_are_styled_like_the_project_pages(
        self, page, fixture,
    ):
        """Defect 3 exactly.

        The shared generator writes ``projects/index.html`` and
        ``blog/index.html`` itself, so they miss whatever the per-project
        graft is responsible for -- including, once, the stylesheet.
        """
        readings = {}
        for label in ("home", "docs", "shared-projects", "shared-blog"):
            _open(page, fixture, label)
            page.wait_for_load_state("networkidle")
            readings[label] = page.evaluate(
                "() => getComputedStyle(document.body).backgroundColor"
            )
        assert len(set(readings.values())) == 1, (
            f"[{fixture.theme}] the shared pages do not share the site's body "
            f"background: {readings}"
        )


class TestTheFrameworkPayloadIsServed:
    """A theme may ship someone else's sheets and faces.

    The tinymoon theme stopped imitating the framework and started
    consuming it: the stylesheet is the framework's own bytes, and its
    ``@font-face`` rules address ``../fonts/`` relative to wherever that
    stylesheet was written.  That is a whole class of defect a string
    assertion cannot see -- the CSS is byte-perfect and the fonts 404,
    the page renders in a fallback face, and every unit test passes.

    Skipped for a theme that ships no payload; there is nothing to serve.
    """

    @pytest.fixture(autouse=True)
    def _only_framework_themes(self, fixture):
        from selfdoc_core.themes import theme_framework

        if not theme_framework(fixture.theme):
            pytest.skip(f"{fixture.theme} ships no framework payload")

    @pytest.mark.parametrize("label", ALL_PAGES)
    def test_every_font_the_page_asks_for_arrives(self, page, fixture, label):
        """Network capture on the font requests, on both served trees."""
        seen = []
        page.on(
            "response",
            lambda r: seen.append((r.url, r.status))
            if r.request.resource_type == "font" or r.url.endswith(".woff2")
            else None,
        )
        _open(page, fixture, label)
        page.wait_for_load_state("networkidle")
        # A font is fetched only when something on the page needs that face,
        # so an empty list is not a failure -- a failed fetch is.
        failed = [(url, status) for url, status in seen if status >= 400]
        assert not failed, (
            f"[{fixture.theme}] {label} asked for fonts that do not resolve: "
            f"{failed}"
        )

    @pytest.mark.parametrize("label", ["docs", "standalone-current"])
    def test_the_body_is_set_in_the_framework_face(self, page, fixture, label):
        """Not a fallback: the face the framework ships is the one painted."""
        _open(page, fixture, label)
        page.wait_for_load_state("networkidle")
        loaded = page.evaluate(
            """() => {
                const out = [];
                document.fonts.forEach(f => { if (f.status === 'loaded')
                    out.push(f.family); });
                return out;
            }"""
        )
        assert any("Plex" in family for family in loaded), (
            f"[{fixture.theme}] {label} loaded no framework face; "
            f"loaded={sorted(set(loaded))}"
        )

    @pytest.mark.parametrize("label", ["docs", "docs-tables", "standalone-current"])
    def test_a_page_taller_than_the_viewport_still_scrolls(
        self, page, fixture, label,
    ):
        """The framework's globals are written for the framework's shell.

        ``base.css`` gives the viewport to an application frame: the body
        is ``overflow: hidden`` because the scroller is ``#tm-content``, and
        ``user-select: none`` because the selectable carve-out is
        ``.doc-body``.  A selfdoc page has neither element, so inheriting
        those globals unchanged means everything below the fold is
        unreachable and no passage can be copied -- and both look perfect
        in a screenshot of the top of the page.
        """
        _open(page, fixture, label)
        page.wait_for_load_state("networkidle")
        page.set_viewport_size({"width": 1280, "height": 500})
        page.wait_for_timeout(80)
        metrics = page.evaluate(
            """() => {
                const el = document.scrollingElement;
                window.scrollTo(0, 100000);
                return {
                    scrollable: el.scrollHeight > el.clientHeight + 4,
                    moved: el.scrollTop > 0,
                    select: getComputedStyle(document.body).userSelect,
                };
            }"""
        )
        assert metrics["scrollable"], (
            f"[{fixture.theme}] {label} is not taller than a 500px viewport; "
            f"the fixture cannot measure scrolling on it"
        )
        assert metrics["moved"], (
            f"[{fixture.theme}] {label} does not scroll -- everything below "
            f"the fold is unreachable"
        )
        assert metrics["select"] != "none", (
            f"[{fixture.theme}] {label} renders unselectable text "
            f"(user-select: {metrics['select']})"
        )

    @pytest.mark.parametrize("label", ALL_PAGES)
    def test_nothing_is_fetched_from_off_origin(self, page, fixture, label):
        """The framework vendors everything; a CDN request means it did not."""
        offsite = []
        page.on(
            "request",
            lambda r: offsite.append(r.url)
            if not r.url.startswith(("http://127.0.0.1", "http://localhost",
                                     "data:", "blob:"))
            else None,
        )
        _open(page, fixture, label)
        page.wait_for_load_state("networkidle")
        assert not offsite, (
            f"[{fixture.theme}] {label} fetched from off-origin: {offsite}"
        )


# -- 5. on-origin navigation ----------------------------------------------------------------


class TestOnOriginNavigation:
    """Defect 5: absolute links that walked the reader off the site.

    A link written against the deployed base is right in the HTML and
    wrong in the browser -- it leaves the origin being served.  The only
    way to see it is to resolve every href a reader can click.
    """

    def test_every_visible_link_stays_on_this_origin(self, page, fixture):
        offenders = collections.defaultdict(list)
        for label in ALL_PAGES:
            site = _open(page, fixture, label)
            hrefs = page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const s = getComputedStyle(a);
                        if (s.display === 'none' || s.visibility === 'hidden') return false;
                        const box = a.getBoundingClientRect();
                        return box.width > 0 || box.height > 0;
                    })
                    .map(a => a.href)"""
            )
            for href in sorted(set(hrefs)):
                if href.startswith(("mailto:", "tel:", "javascript:")):
                    continue
                if href.split("#")[0].rstrip("/") in _ALLOWED:
                    continue
                if not href.startswith(site.origin):
                    offenders[label].append(href)

        assert not offenders, (
            f"[{fixture.theme}] links leave the origin being served. The "
            f"fixture declares its off-origin addresses one by one "
            f"({', '.join(sorted(EXTERNAL_ALLOWLIST))}); everything else has "
            f"to stay local: {dict(offenders)}"
        )

    def test_every_on_origin_link_resolves_to_a_page(self, page, fixture):
        """A same-origin link that answers 404 is a dead link a reader will hit."""
        dead = {}
        for label in ALL_PAGES:
            site = _open(page, fixture, label)
            hrefs = page.evaluate(
                """() => Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const s = getComputedStyle(a);
                        return s.display !== 'none' && s.visibility !== 'hidden';
                    })
                    .map(a => a.href)"""
            )
            for href in sorted(set(hrefs)):
                if not href.startswith(site.origin):
                    continue
                target = href.split("#")[0]
                status = page.request.head(target).status
                if status >= 400:
                    dead.setdefault(label, []).append((target, status))
        assert not dead, f"[{fixture.theme}] dead same-origin links: {dead}"


# -- 6. glossary -------------------------------------------------------------------------------


class TestGlossary:
    """Defect 6: a glossary term no page had ever defined.

    A term exists only because an author declared it, and its Source link
    has to land on that declaration.  Both halves are browser facts: the
    fragment must resolve to an element that is really in the viewport,
    and the definition site must be something a reader can act on.
    """

    def test_the_glossary_lists_exactly_the_declared_terms(self, page, fixture):
        _open(page, fixture, "docs-glossary")
        terms = page.evaluate(
            "() => Array.from(document.querySelectorAll('.glossary dt dfn'))"
            ".map(el => el.textContent.trim())"
        )
        assert sorted(terms) == ["Anchor", "Archive", "Manifest"], (
            f"[{fixture.theme}] the glossary lists {terms}; the fixture "
            f"declares exactly three terms and nothing may invent a fourth"
        )

    def test_each_source_link_lands_on_the_element_that_defines_the_term(
        self, page, fixture,
    ):
        """Click Source; the target must exist and be scrolled into view."""
        _open(page, fixture, "docs-glossary")
        count = page.locator(".glossary dd a").count()
        assert count == 3, (
            f"[{fixture.theme}] {count} Source link(s) for three terms"
        )

        for index in range(count):
            _open(page, fixture, "docs-glossary")
            link = page.locator(".glossary dd a").nth(index)
            href = link.get_attribute("href")
            assert "#" in href, (
                f"[{fixture.theme}] Source link {index} carries no fragment: {href}"
            )
            link.click()
            page.wait_for_load_state("load")
            fragment = page.evaluate("() => location.hash.slice(1)")
            assert fragment, (
                f"[{fixture.theme}] Source link {index} went to {page.url} "
                f"with no fragment"
            )
            target = page.locator(f"#{fragment}")
            assert target.count() == 1, (
                f"[{fixture.theme}] {page.url} carries no element #{fragment} "
                f"-- the Source link names a definition site that is not there"
            )
            box = target.bounding_box()
            assert box is not None and box["height"] > 0, (
                f"[{fixture.theme}] #{fragment} on {page.url} has no box"
            )
            viewport = page.viewport_size["height"]
            assert -1 <= box["y"] < viewport, (
                f"[{fixture.theme}] #{fragment} on {page.url} sits at "
                f"y={box['y']} in a {viewport}px viewport -- the browser did "
                f"not scroll the definition into view"
            )

    def test_the_definition_site_offers_something_to_act_on(self, page, fixture):
        """The term on its own page is an affordance, not inert text."""
        _open(page, fixture, "docs-glossary")
        page.locator(".glossary dd a").first.click()
        page.wait_for_load_state("load")
        fragment = page.evaluate("() => location.hash.slice(1)")
        reading = page.evaluate(
            """(id) => {
                const el = document.getElementById(id);
                if (!el) return null;
                const scope = el.closest('dt, p, li') || el;
                const link = scope.querySelector('a[href]') ||
                             (el.tagName === 'A' ? el : null);
                if (!link) return {found: false, html: scope.outerHTML.slice(0, 300)};
                return {found: true, href: link.getAttribute('href'),
                        cursor: getComputedStyle(link).cursor};
            }""",
            fragment,
        )
        assert reading is not None, (
            f"[{fixture.theme}] #{fragment} does not exist on {page.url}"
        )
        assert reading["found"], (
            f"[{fixture.theme}] the definition site for #{fragment} on "
            f"{page.url} offers nothing to click: {reading['html']}"
        )


# -- 7. search ---------------------------------------------------------------------------------


#: Two search surfaces, because a theme that composes the framework draws
#: its own.  A framework theme loads the framework's command palette over
#: Pagefind's query API and never loads Pagefind's shipped widget; every
#: other theme mounts the widget in selfdoc's own dialog.  The selectors
#: differ, what a reader does does not, so the assertions below take the
#: surface from the theme and are otherwise one set of tests.
SEARCH_SURFACES = {
    "framework": {
        "overlay": "dialog.tm-palette",
        "input": ".tm-palette-input",
        "result": ".tm-palette-item",
    },
    "widget": {
        "overlay": "#search-dialog",
        "input": ".pagefind-ui__search-input",
        "result": ".pagefind-ui__result",
    },
}

#: The themes that compose a framework, and therefore draw their own
#: search.  Read from the theme registry rather than listed, so a theme
#: that starts or stops composing one joins the right sweep by itself.
FRAMEWORK_THEMES = {
    name for name in THEMES if _theme_framework(name)
}


def _surface(fixture):
    kind = "framework" if fixture.theme in FRAMEWORK_THEMES else "widget"
    return SEARCH_SURFACES[kind]


def _await_overlay(page, surface):
    """Wait until the search overlay is really painted, not merely present.

    The framework's palette animates in, so an assertion sampled the
    instant its input appears reads an opacity of 0 and calls a perfectly
    open overlay invisible.  Waiting on what the assertion measures is the
    honest wait: the same predicate, given time to become true.
    """
    page.wait_for_function(
        """(sel) => Array.from(document.querySelectorAll(sel)).some(el => {
            const style = getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            if (parseFloat(style.opacity) === 0) return false;
            const box = el.getBoundingClientRect();
            return box.width > 0 && box.height > 0;
        })""",
        arg=surface["overlay"],
        timeout=15000,
    )


def _open_search(page, fixture):
    """Open search the way a reader does, and wait for it to be there."""
    surface = _surface(fixture)
    page.keyboard.press("Control+k")
    page.wait_for_selector(surface["input"], timeout=15000)
    _await_overlay(page, surface)
    return surface


class TestSearch:
    """The search overlay, driven the way a reader drives it.

    Pagefind really ran over the fixture tree in the session fixture, so
    the index the overlay queries is the index a deploy would ship.
    """

    def test_ctrl_k_opens_the_overlay(self, page, fixture):
        _open(page, fixture, "docs")
        surface = _surface(fixture)
        assert _visible_count(page, surface["overlay"]) == 0
        _open_search(page, fixture)
        assert _visible_count(page, surface["overlay"]) == 1, (
            f"[{fixture.theme}] the overlay opened but paints nothing"
        )

    def test_the_trigger_opens_the_overlay(self, page, fixture):
        """The topbar's magnifier is a control, not decoration."""
        _open(page, fixture, "docs")
        surface = _surface(fixture)
        page.click(".search-trigger, .search-bar-trigger")
        page.wait_for_selector(surface["input"], timeout=15000)
        _await_overlay(page, surface)
        assert _visible_count(page, surface["overlay"]) == 1

    def test_escape_closes_the_overlay(self, page, fixture):
        _open(page, fixture, "docs")
        surface = _open_search(page, fixture)
        page.keyboard.press("Escape")
        page.wait_for_selector(
            surface["overlay"], state="hidden", timeout=5000,
        )

    # One page class per depth the index can be addressed from. The depth
    # is the whole point: the bundle path used to be computed at build
    # time from the page's own hop, and a dynamic import resolves that hop
    # against the *bundle's* URL instead -- so search worked at exactly the
    # depths where the two mistakes cancelled and silently returned nothing
    # everywhere else, the front page and every project landing page
    # included.
    @pytest.mark.parametrize(
        "label", ["home", "docs", "docs-tables", "post", "standalone-archive"],
    )
    def test_a_query_against_the_real_index_returns_a_result(
        self, page, fixture, label,
    ):
        _open(page, fixture, label)
        page.wait_for_load_state("networkidle")
        failures = []
        page.on(
            "console",
            lambda m: failures.append(m.text) if m.type == "error" else None,
        )
        surface = _open_search(page, fixture)
        page.fill(surface["input"], "fixture")
        try:
            page.wait_for_selector(surface["result"], timeout=20000)
        except Exception:
            raise AssertionError(
                f"[{fixture.theme}] searching from {label} returned nothing "
                f"for a word the fixture content certainly carries. Console: "
                f"{failures[:3]}"
            ) from None
        assert page.locator(surface["result"]).count() >= 1
        assert not failures, (
            f"[{fixture.theme}] the search on {label} logged errors: "
            f"{failures[:3]}"
        )

    def test_the_facets_render(self, page, fixture):
        """The build declares filter facets; the widget has to offer them.

        Only the widget: the framework's palette is a ranked list with no
        filter surface, so a framework theme's search offers no facets and
        this is the one capability the two surfaces do not share.  The
        facet elements are still emitted and still indexed -- what changes
        is that nothing on the page exposes them as controls.
        """
        if fixture.theme in FRAMEWORK_THEMES:
            pytest.skip("the framework's palette offers no filter controls")
        _open(page, fixture, "docs")
        page.wait_for_load_state("networkidle")
        surface = _open_search(page, fixture)
        page.fill(surface["input"], "fixture")
        page.wait_for_selector(surface["result"], timeout=20000)
        facets = page.locator(
            ".pagefind-ui__filter-panel, .pagefind-ui__drawer, .pagefind-ui__filter-group"
        ).count()
        assert facets >= 1, (
            f"[{fixture.theme}] the search UI rendered no filter controls, "
            f"though the build declares facets for them to read"
        )

    def test_a_framework_theme_ships_no_pagefind_widget(self, page, fixture):
        """Nothing loads it, so the deploy does not carry it."""
        if fixture.theme not in FRAMEWORK_THEMES:
            pytest.skip("this theme mounts the widget")
        site, _path = _served(fixture, "docs")
        for asset in ("pagefind-ui.css", "pagefind-ui.js"):
            response = page.request.get(site.url(f"/pagefind/{asset}"))
            assert response.status >= 400, (
                f"[{fixture.theme}] {asset} is still served, though no page "
                f"references it"
            )
        # The query API the palette calls is a different file, and stays.
        assert page.request.get(site.url("/pagefind/pagefind.js")).ok


# -- 8. theme toggle -------------------------------------------------------------------------------


class TestThemeToggle:
    """Light and dark are what the browser paints, not what localStorage says."""

    def test_toggling_changes_the_painted_background(self, page, fixture):
        _open(page, fixture, "docs")
        toggle = page.locator(".theme-toggle").first
        toggle.wait_for(state="visible")

        seen = {}
        for _ in range(3):
            state = page.evaluate(
                "() => document.querySelector('.theme-toggle')"
                ".getAttribute('data-state')"
            )
            _settle_animations(page)
            seen[state] = page.evaluate(
                "() => getComputedStyle(document.body).backgroundColor"
            )
            toggle.click()
            page.wait_for_timeout(80)

        assert set(seen) == {"system", "light", "dark"}, (
            f"[{fixture.theme}] the toggle cycled through {sorted(seen)}"
        )
        assert seen["light"] != seen["dark"], (
            f"[{fixture.theme}] light and dark paint the same body "
            f"background: {seen}"
        )

    def test_the_choice_survives_a_reload(self, page, fixture):
        _open(page, fixture, "docs")
        page.evaluate("() => localStorage.setItem('selfdoc-theme', 'dark')")
        _open(page, fixture, "docs")
        _settle_animations(page)
        assert page.evaluate(
            "() => document.documentElement.getAttribute('data-theme')"
        ) == "dark", (
            f"[{fixture.theme}] a stored dark choice did not survive a reload"
        )

    def test_the_resting_state_follows_an_emulated_dark_preference(
        self, chromium_browser, fixture,
    ):
        """With no stored choice, a dark preference must reach the page.

        tinymoon is a dark theme, so its resting state under a dark
        preference has to be dark; the other two are asserted for the
        weaker property that nothing pins ``data-theme`` behind the
        reader's back.
        """
        context = chromium_browser.new_context(
            viewport={"width": 1280, "height": 900}, color_scheme="dark",
        )
        pg = context.new_page()
        try:
            _goto(pg, fixture.assembly, ASSEMBLY_PAGES["docs"])
            _settle_animations(pg)
            reading = pg.evaluate(
                """() => {
                    const s = getComputedStyle(document.body);
                    const rgb = s.backgroundColor.match(/\\d+/g).map(Number);
                    return {
                        background: s.backgroundColor,
                        luminance: (0.299*rgb[0] + 0.587*rgb[1] + 0.114*rgb[2]) / 255,
                        attr: document.documentElement.getAttribute('data-theme'),
                    };
                }"""
            )
            assert reading["attr"] is None, (
                f"[{fixture.theme}] the page pinned data-theme="
                f"{reading['attr']} with no stored choice; the resting state "
                f"must follow the reader's preference"
            )
            if fixture.theme == "tinymoon":
                assert reading["luminance"] < 0.5, (
                    f"[{fixture.theme}] with a dark preference emulated, "
                    f"tinymoon rests light: {reading}"
                )
        finally:
            context.close()


# -- 9. version UI ------------------------------------------------------------------------------------


class TestVersionUI:
    """The archive notice, its dismissal, the picker, and the unversioned case.

    Asserted against the standalone site, because that is the tree that
    carries an archive: an assembly build takes ``--version <latest>``, so
    an assembled subtree publishes the current version and nothing else.
    """

    def test_the_archive_page_shows_the_superseded_notice(self, page, fixture):
        _open(page, fixture, "standalone-archive")
        notice = page.locator(".version-notice")
        assert notice.count() == 1, (
            f"[{fixture.theme}] an archive page carries {notice.count()} "
            f"superseded notices"
        )
        assert notice.first.is_visible(), (
            f"[{fixture.theme}] the superseded notice is in the DOM but is "
            f"not painted"
        )
        assert "0.1.0" in notice.first.inner_text()

    def test_the_current_version_shows_no_notice(self, page, fixture):
        _open(page, fixture, "standalone-current")
        assert page.locator(".version-notice").count() == 0, (
            f"[{fixture.theme}] the current version claims to be superseded"
        )

    def test_dismissing_the_notice_persists_across_a_reload(self, page, fixture):
        _open(page, fixture, "standalone-archive")
        page.evaluate("() => localStorage.clear()")
        _open(page, fixture, "standalone-archive")
        notice = page.locator(".version-notice")
        assert notice.first.is_visible()
        page.locator(".version-notice-dismiss").first.click()
        assert not notice.first.is_visible(), (
            f"[{fixture.theme}] the notice stayed visible after Dismiss"
        )

        _open(page, fixture, "standalone-archive")
        assert not page.locator(".version-notice").first.is_visible(), (
            f"[{fixture.theme}] the dismissal did not survive a reload"
        )

    def test_the_notice_links_back_to_the_current_version(self, page, fixture):
        _open(page, fixture, "standalone-archive")
        page.evaluate("() => localStorage.clear()")
        _open(page, fixture, "standalone-archive")
        page.locator(".version-notice a").first.click()
        page.wait_for_load_state("load")
        assert page.locator(".version-notice").count() == 0, (
            f"[{fixture.theme}] the notice's link went to {page.url}, which "
            f"also claims to be superseded"
        )

    def test_every_version_the_picker_offers_resolves(self, page, fixture):
        site = _open(page, fixture, "standalone-current")
        picker = page.locator(".version-picker")
        assert picker.count() == 1, (
            f"[{fixture.theme}] a versioned page has {picker.count()} "
            f"version pickers"
        )
        options = page.evaluate(
            """() => Array.from(
                document.querySelectorAll('.version-picker .sel-opt')
            ).map(o => ({value: o.dataset.value, href: o.dataset.href}))"""
        )
        assert {o["value"] for o in options} == {"0.1.0", "0.2.0"}, (
            f"[{fixture.theme}] the picker offers {options}"
        )
        for option in options:
            resolved = page.evaluate(
                "(href) => new URL(href, location.href).href", option["href"],
            )
            assert resolved.startswith(site.origin), (
                f"[{fixture.theme}] the picker sends v{option['value']} off "
                f"the origin, to {resolved}"
            )
            status = page.request.head(resolved).status
            assert status < 400, (
                f"[{fixture.theme}] the picker offers v{option['value']} at "
                f"{resolved}, which answers {status}"
            )

    def test_an_unversioned_project_shows_no_version_ui(self, page, fixture):
        """Version chrome must not leak onto a project that declares none."""
        _open(page, fixture, "docs-unversioned")
        readings = {
            "badge": page.locator(".version-badge").count(),
            "picker": page.locator(".version-picker").count(),
            "notice": page.locator(".version-notice").count(),
        }
        assert readings == {"badge": 0, "picker": 0, "notice": 0}, (
            f"[{fixture.theme}] an unversioned project's page carries version "
            f"chrome: {readings}"
        )

    def test_an_assembled_page_offers_no_picker_it_cannot_honour(
        self, page, fixture,
    ):
        """The assembly publishes one version, so it must offer no other.

        A picker on an assembled page would name ``v/<older>/`` addresses
        the assembled site does not serve -- dead links by construction.
        """
        _open(page, fixture, "docs")
        assert page.locator(".version-picker").count() == 0, (
            f"[{fixture.theme}] the assembled page offers a version picker, "
            f"but the assembly publishes only the current version"
        )
        assert page.locator(".version-badge").count() == 1, (
            f"[{fixture.theme}] the assembled page of a versioned project "
            f"carries no version badge"
        )


# -- 10. the band guard --------------------------------------------------------------------------------


class TestViewportMonotonicity:
    """Defect 2, generalized: an element visible only inside a middle band.

    For each page class, the set of visible major layout elements must be
    a monotone function of viewport width -- the run of widths at which an
    element is visible has to touch one end of the sweep and have no gaps
    in it.  An element that appears, disappears and reappears, or that is
    visible only in the middle, is two breakpoints disagreeing.
    """

    ELEMENTS = {
        "topbar": ".topbar",
        "sidebar": ".sidebar",
        "desktop-toc": "aside.toc",
        "mobile-toc": "details.mobile-toc",
        "footer": ".site-footer, footer.page-footer",
        "search-trigger": ".search-trigger",
    }

    @pytest.mark.parametrize("label", ALL_PAGES)
    def test_visibility_is_monotone_in_viewport_width(
        self, page, fixture, label,
    ):
        _open(page, fixture, label)
        readings = {}
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(60)
            readings[width] = {
                name: bool(_visible_count(page, selector))
                for name, selector in self.ELEMENTS.items()
            }

        bands = []
        for name in self.ELEMENTS:
            series = [readings[w][name] for w in WIDTHS]
            if True not in series:
                continue
            first = series.index(True)
            last = len(series) - 1 - series[::-1].index(True)
            interior = first > 0 and last < len(series) - 1
            gaps = any(not value for value in series[first:last + 1])
            if interior or gaps:
                bands.append((name, dict(zip(WIDTHS, series))))

        assert not bands, (
            f"[{fixture.theme}] {label}: element(s) visible only inside a "
            f"band of viewport widths, never at either end -- the signature "
            f"of two breakpoints that disagree: {bands}"
        )

    @pytest.mark.parametrize("label", ALL_PAGES)
    def test_nothing_overflows_the_viewport_horizontally(
        self, page, fixture, label,
    ):
        """A page that scrolls sideways at any width is a layout defect."""
        _open(page, fixture, label)
        offenders = {}
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 900})
            page.wait_for_timeout(60)
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - "
                "document.documentElement.clientWidth"
            )
            if overflow > 1:
                offenders[width] = overflow
        assert not offenders, (
            f"[{fixture.theme}] {label} overflows horizontally by "
            f"{offenders} px"
        )


# -- 11. the CV -------------------------------------------------------------------------------------------


class TestCV:
    """The CV page: a portrait that decodes, and a header laid out as a row."""

    def test_the_photo_renders(self, page, fixture):
        _open(page, fixture, "cv")
        page.locator(".cv-photo img").first.wait_for(state="visible")
        natural = page.evaluate(
            """() => {
                const img = document.querySelector('.cv-photo img');
                return {w: img.naturalWidth, h: img.naturalHeight,
                        src: img.currentSrc || img.src, complete: img.complete};
            }"""
        )
        assert natural["complete"] and natural["w"] > 0 and natural["h"] > 0, (
            f"[{fixture.theme}] the CV portrait did not decode: {natural}"
        )

    def test_the_header_block_puts_the_photo_beside_the_identity(
        self, page, fixture,
    ):
        """At desktop width the portrait and the identity share a row."""
        _open(page, fixture, "cv")
        page.set_viewport_size({"width": 1280, "height": 900})
        page.wait_for_timeout(60)
        photo = page.locator(".cv-photo").first.bounding_box()
        identity = page.locator(".cv-identity").first.bounding_box()
        assert photo and identity, (
            f"[{fixture.theme}] the CV header is missing a half: "
            f"photo={photo} identity={identity}"
        )
        overlap = min(
            photo["y"] + photo["height"], identity["y"] + identity["height"],
        ) - max(photo["y"], identity["y"])
        assert overlap > 0, (
            f"[{fixture.theme}] the CV photo and identity are stacked rather "
            f"than in a row: photo={photo} identity={identity}"
        )
        assert identity["x"] >= photo["x"] + photo["width"] - 1, (
            f"[{fixture.theme}] the identity block is not beside the "
            f"portrait: photo={photo} identity={identity}"
        )

    def test_the_cv_renders_every_declared_section(self, page, fixture):
        _open(page, fixture, "cv")
        headings = page.evaluate(
            "() => Array.from(document.querySelectorAll('main h2'))"
            ".map(h => h.textContent.replace('#', '').trim())"
        )
        for section in ("Skills", "Projects", "Hobbies & interests",
                        "Education", "Work experience", "Languages",
                        "Contact information"):
            assert section in headings, (
                f"[{fixture.theme}] the CV page has no {section!r} section: "
                f"{headings}"
            )


# -- 12. accessibility ---------------------------------------------------------------------------------------


#: axe rules that fail across the fixture today, each with what it is.
#:
#: This is a record, not a suppression, and it is checked in both
#: directions: a serious or critical rule that is NOT listed here fails the
#: page it appears on, and a rule listed here that no longer appears
#: anywhere in the sweep fails the session, so a fix cannot quietly leave a
#: stale entry behind. Every one of these is a real finding reported to the
#: maintainer; none is a defect a test may decide to fix, because each is a
#: change to the visual design of all three themes.
KNOWN_SERIOUS = {
    "link-in-text-block": (
        "links in prose are distinguished from surrounding text by colour "
        "alone (WCAG 1.4.1). Fixing it means underlining prose links, or "
        "raising link/text contrast to 3:1, in every theme."
    ),
    "color-contrast": (
        "the topbar page title and the active nav item fall under 4.5:1 in "
        "the clean and minimal palettes (WCAG 1.4.3). Fixing it means "
        "moving a colour token in those themes."
    ),
    "scrollable-region-focusable": (
        "the table's scrolling box takes no keyboard focus, so a table "
        "wider than its column can only be scrolled with a pointer "
        "(WCAG 2.1.1). Fixing it means a focusable, labelled scroll region "
        "on every .table-wrap."
    ),
}


class TestAccessibility:
    """axe over one page per page class per theme.

    The blocking severities are ``serious`` and ``critical``. Findings
    below those are advisory here -- a stance taken deliberately rather
    than a silence, and one this suite can raise once the serious ones are
    settled.
    """

    SEVERITY = ("serious", "critical")

    @pytest.mark.parametrize("label", ALL_PAGES)
    def test_no_unrecorded_serious_or_critical_violations(
        self, page, fixture, label,
    ):
        from axe_playwright_python.sync_playwright import Axe

        _open(page, fixture, label)
        page.wait_for_load_state("networkidle")
        # Contrast is computed from live computed styles, so it is sampled
        # only once entrance motion has settled -- tinymoon's precedent,
        # and the same intermittent failure without it.
        _settle_animations(page)

        found = [
            {
                "id": v["id"],
                "impact": v["impact"],
                "help": v["help"],
                "nodes": [n["target"] for n in v["nodes"]][:4],
            }
            for v in Axe().run(page).response["violations"]
            if v.get("impact") in self.SEVERITY
        ]
        for violation in found:
            _AXE_SEEN.add(violation["id"])

        unrecorded = [v for v in found if v["id"] not in KNOWN_SERIOUS]
        assert not unrecorded, (
            f"[{fixture.theme}] {label} has {len(unrecorded)} unrecorded "
            f"{'/'.join(self.SEVERITY)} accessibility violation(s):\n"
            + "\n".join(
                f"  {v['id']} ({v['impact']}): {v['help']} at {v['nodes']}"
                for v in unrecorded
            )
        )


#: Every axe rule the sweep really saw, filled in as it runs.
_AXE_SEEN: set[str] = set()


def test_every_recorded_accessibility_finding_is_still_real():
    """A recorded finding that has been fixed must leave the record.

    The other half of ``KNOWN_SERIOUS``: without this, a fixed rule would
    sit in the list forever and quietly re-admit the same defect later.
    """
    if not _AXE_SEEN:
        pytest.skip("the accessibility sweep did not run in this session")
    stale = sorted(set(KNOWN_SERIOUS) - _AXE_SEEN)
    assert not stale, (
        f"KNOWN_SERIOUS records {stale}, which the sweep no longer sees. "
        f"They are fixed -- delete the entries, so the rule blocks again."
    )


# -- the tree the browser is looking at --------------------------------------------------------------------------


class TestTheFixtureItself:
    """Guards on the fixture, so a silently thin site cannot pass everything.

    Every assertion above is only as good as the tree it runs against. A
    build that quietly stopped emitting archives, or a Pagefind run that
    indexed nothing, would turn most of this suite green by leaving it
    nothing to be wrong about.
    """

    def test_the_sweep_covers_every_theme_the_toolchain_ships(self):
        from selfdoc_core.themes import list_themes

        assert sorted(THEMES) == sorted(list_themes()), (
            f"the sweep visits {sorted(THEMES)} but the toolchain ships "
            f"{sorted(list_themes())}; a theme nothing renders is a theme "
            f"nothing checks"
        )

    @pytest.mark.parametrize("label", ALL_PAGES)
    def test_every_page_class_is_served(self, page, fixture, label):
        site, path = _served(fixture, label)
        status = page.request.head(site.url(path)).status
        assert status < 400, (
            f"[{fixture.theme}] the fixture does not serve {label} at "
            f"{path}: {status}"
        )

    def test_both_search_indexes_were_really_built(self, fixture):
        for site in (fixture.assembly, fixture.standalone):
            entry = os.path.join(site.site_dir, "pagefind", "pagefind-entry.json")
            assert os.path.isfile(entry), (
                f"[{fixture.theme}] Pagefind produced no index over "
                f"{site.site_dir}"
            )

    def test_the_standalone_tree_really_carries_an_archive(self, fixture):
        archive = os.path.join(fixture.standalone.site_dir, "v", "0.1.0", "index.html")
        assert os.path.isfile(archive), (
            f"[{fixture.theme}] the standalone build emitted no archive, so "
            f"every version-UI assertion above would pass vacuously"
        )

    def test_the_table_really_overflows_its_own_box(self, page, fixture):
        """Every table assertion is vacuous against a table that fits.

        Measured at ``TABLE_WIDTH``, which is where the table assertions
        run, and in the axis that is really there: ``.table-wrap`` is
        ``overflow-x: auto`` with no height constraint, so it scrolls
        sideways and never vertically. The pinned first column and the
        header-alignment assertion both need that sideways room, and the
        sticky header is exercised against the page's scroll as well as
        the box's.
        """
        _open(page, fixture, "docs-tables")
        page.set_viewport_size({"width": TABLE_WIDTH, "height": 900})
        page.wait_for_timeout(80)
        wrap = page.locator(".table-wrap").first
        wrap.wait_for(state="visible")
        room = wrap.evaluate(
            "(el) => ({down: el.scrollHeight - el.clientHeight,"
            " across: el.scrollWidth - el.clientWidth,"
            " overflowing: el.classList.contains('has-overflow')})"
        )
        assert room["across"] > 0, (
            f"[{fixture.theme}] the fixture table fits inside its own box at "
            f"{TABLE_WIDTH}px, so nothing above scrolled anything: {room}"
        )
        assert room["overflowing"], (
            f"[{fixture.theme}] the wrapper overflows but was never marked "
            f"`has-overflow`, so the pinned first column is not applied: "
            f"{room}"
        )

    def test_the_page_itself_scrolls_past_the_table(self, page, fixture):
        """The sticky header is asserted against the page scroll too."""
        _open(page, fixture, "docs-tables")
        page.set_viewport_size({"width": TABLE_WIDTH, "height": 900})
        page.wait_for_timeout(80)
        room = page.evaluate(
            "() => document.documentElement.scrollHeight - "
            "document.documentElement.clientHeight"
        )
        assert room > 900, (
            f"[{fixture.theme}] the table page is only {room}px taller than "
            f"the viewport, so scrolling it moves nothing worth measuring"
        )

    def test_the_pages_carry_the_theme_they_were_built_under(self, page, fixture):
        """A sweep that served one theme three times would prove nothing."""
        _open(page, fixture, "docs")
        page.wait_for_load_state("networkidle")
        signature = page.evaluate(
            """() => {
                const s = getComputedStyle(document.body);
                return [s.fontFamily, s.backgroundColor, s.color].join('|');
            }"""
        )
        assert signature, "no computed body style at all"
        _SIGNATURES[fixture.theme] = signature

    def test_the_fixture_declares_exactly_one_external_link(self, page, fixture):
        _open(page, fixture, "docs")
        external = page.evaluate(
            """(origin) => Array.from(document.querySelectorAll('main a[href]'))
                .map(a => a.href)
                .filter(h => h.startsWith('http') && !h.startsWith(origin))""",
            fixture.assembly.origin,
        )
        assert external == [ALLOWED_EXTERNAL], (
            f"[{fixture.theme}] the fixture's external links are {external}; "
            f"the navigation allowlist covers exactly {ALLOWED_EXTERNAL}"
        )


#: Recorded by ``test_the_pages_carry_the_theme_they_were_built_under`` as the
#: theme sweep runs, and checked once at the end of the session.
_SIGNATURES: dict[str, str] = {}


def test_the_three_themes_really_render_differently():
    """Three themes must produce three renderings, or the sweep is decoration.

    Reads what the per-theme tests recorded; skips when the session was
    filtered down to fewer themes than the sweep declares.
    """
    if len(_SIGNATURES) < len(THEMES):
        pytest.skip(
            f"only {sorted(_SIGNATURES)} of {THEMES} ran in this session"
        )
    assert len(set(_SIGNATURES.values())) == len(THEMES), (
        f"themes that render identically: {_SIGNATURES}"
    )
