"""Every theme styles the same class surface.

A theme is not a palette, it is a restatement of selfdoc's whole rendered
surface.  A page's markup does not change with the theme, so a class the
other themes style and this one does not is not a stylistic choice -- it
is an element that renders unstyled, and nothing about the page says so.
This asserts the surfaces match, and forces any deliberate difference to
be written down here rather than discovered on a page.

The unit is the *class name*, not the selector string.  Two themes can
reach ``.admonition.note`` by different routes -- one restating it per
colour scheme, another deriving the tint with ``color-mix`` from a token
that already flips -- and both have styled it.  Comparing selector text
would call the second one a gap.
"""

import re
from pathlib import Path

import pytest

from selfdoc_core.themes import list_themes

THEMES_DIR = Path(__file__).resolve().parent.parent / "selfdoc_core" / "themes"

#: The theme every other theme's surface is measured against.  It is the
#: default, and its surface is a superset of the others'.
REFERENCE = "minimal"

#: Classes a named theme deliberately does not carry, with the reason.
#: Empty for every theme: a gap here is a bug until someone writes down
#: why it is not.  An entry is a claim that the element is styled by
#: something else, or cannot exist under this theme -- not that it was
#: forgotten.
DELIBERATE_OMISSIONS: dict[str, dict[str, str]] = {
    "clean": {},
    "minimal": {},
    "tinymoon": {},
}

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CLASS_RE = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")


def _selectors(css: str) -> list[str]:
    """Every selector text in *css*, comments and at-rule preludes removed."""
    css = _COMMENT_RE.sub("", css)
    out = []
    for match in re.finditer(r"([^{}]+)\{", css):
        sel = match.group(1).strip()
        if not sel or sel.startswith("@"):
            continue
        out.append(re.sub(r"\s+", " ", sel))
    return out


def _classes(css: str) -> set[str]:
    """Every class name the stylesheet targets."""
    names: set[str] = set()
    for sel in _selectors(css):
        names.update(_CLASS_RE.findall(sel))
    return names


def _elements(css: str) -> set[str]:
    """Every bare element name the stylesheet targets at the top of a
    selector -- ``table``, ``thead``, ``kbd`` and the rest of the surface
    that carries no class."""
    names: set[str] = set()
    for sel in _selectors(css):
        for part in sel.split(","):
            part = part.strip()
            match = re.match(r"^([a-z][a-z0-9]*)\b", part)
            if match:
                names.add(match.group(1))
    return names


def _read(theme: str) -> str:
    return (THEMES_DIR / f"{theme}.css").read_text()


@pytest.fixture(scope="module")
def reference_css() -> str:
    return _read(REFERENCE)


OTHER_THEMES = [t for t in list_themes() if t != REFERENCE]


class TestClassSurfaceParity:
    def test_the_reference_theme_is_shipped(self) -> None:
        assert REFERENCE in list_themes()

    def test_there_is_more_than_one_theme_to_compare(self) -> None:
        assert OTHER_THEMES, "nothing to compare the reference against"

    @pytest.mark.parametrize("theme", OTHER_THEMES)
    def test_the_theme_styles_every_class_the_reference_does(
        self, theme: str, reference_css: str,
    ) -> None:
        expected = _classes(reference_css)
        actual = _classes(_read(theme))
        omitted = set(DELIBERATE_OMISSIONS.get(theme, {}))
        missing = sorted(expected - actual - omitted)
        assert not missing, (
            f"theme {theme!r} styles none of these classes, which "
            f"{REFERENCE!r} does: {', '.join(missing)}. Style them, or "
            f"record them in DELIBERATE_OMISSIONS with the reason."
        )

    @pytest.mark.parametrize("theme", OTHER_THEMES)
    def test_the_theme_styles_every_element_the_reference_does(
        self, theme: str, reference_css: str,
    ) -> None:
        expected = _elements(reference_css)
        actual = _elements(_read(theme))
        missing = sorted(expected - actual)
        assert not missing, (
            f"theme {theme!r} styles none of these elements, which "
            f"{REFERENCE!r} does: {', '.join(missing)}"
        )

    @pytest.mark.parametrize("theme", OTHER_THEMES)
    def test_a_recorded_omission_is_really_absent(self, theme: str) -> None:
        """An omission that is no longer one is a stale exemption."""
        actual = _classes(_read(theme))
        for name, reason in DELIBERATE_OMISSIONS.get(theme, {}).items():
            assert reason, f"{theme}: omission of .{name} carries no reason"
            assert name not in actual, (
                f"theme {theme!r} does style .{name}; remove it from "
                f"DELIBERATE_OMISSIONS"
            )


class TestEveryThemeCarriesTheStructuralMarkers:
    """The bits of a theme the build reads rather than the browser."""

    @pytest.mark.parametrize("theme", list_themes())
    def test_the_critical_marker_is_present(self, theme: str) -> None:
        """Without it the whole stylesheet is inlined into every page."""
        assert "/* --- NON-CRITICAL --- */" in _read(theme)

    @pytest.mark.parametrize("theme", list_themes())
    def test_the_theme_defines_the_contract_variables(self, theme: str) -> None:
        css = _read(theme)
        root = re.search(r":root\s*\{([^}]+)\}", css)
        assert root, f"{theme}: no :root block"
        body = root.group(1)
        for var in (
            "--bg", "--text", "--text-secondary", "--heading", "--link",
            "--link-hover", "--sidebar-bg", "--sidebar-text",
            "--sidebar-active", "--sidebar-hover-bg", "--code-bg",
            "--code-border", "--border", "--topbar-bg", "--topbar-text",
            "--badge-bg", "--badge-text", "--admonition-tip",
            "--admonition-important", "--admonition-warning",
            "--admonition-caution", "--font-body", "--font-mono",
            "--mark-bg",
        ):
            assert f"{var}:" in body, f"{theme}: :root does not define {var}"

    @pytest.mark.parametrize("theme", list_themes())
    def test_the_light_dark_mechanism_is_intact(self, theme: str) -> None:
        """One scheme rests in :root, the other is reassigned two ways.

        Which scheme rests is the theme's own decision -- the shipped
        themes disagree about it -- but the mechanism underneath is
        fixed, because the toggle has three states and all three have to
        resolve.  The reassigned scheme needs a media block for the
        *system* state, scoped away from the opposite explicit choice,
        and a plain ``[data-theme]`` block for its own explicit one.
        """
        css = _read(theme)
        media = re.findall(
            r"@media\s*\(prefers-color-scheme:\s*(light|dark)\)\s*\{\s*"
            r':root:not\(\[data-theme="(light|dark)"\]\)\s*\{',
            css,
        )
        assert len(media) == 1, (
            f"{theme}: expected exactly one variable-reassigning "
            f"prefers-color-scheme block, found {len(media)}"
        )
        reassigned, excluded = media[0]
        assert excluded != reassigned, (
            f"{theme}: the media block for {reassigned} excludes "
            f"data-theme={excluded!r}, which is the same scheme -- forcing "
            f"the resting scheme on the opposite system would not work"
        )
        assert re.search(rf'\[data-theme="{reassigned}"\]\s*\{{', css), (
            f"{theme}: no explicit [data-theme=\"{reassigned}\"] block, so "
            f"choosing {reassigned} on a {excluded} system does nothing"
        )

    @pytest.mark.parametrize("theme", list_themes())
    def test_the_theme_honours_the_hidden_attribute(self, theme: str) -> None:
        """An element JS marks ``hidden`` must stop being painted.

        The UA's own ``[hidden] { display: none }`` sits at specificity
        (0,1,0), which any single class carrying a ``display`` ties with
        and beats on source order -- and every theme styles
        ``.version-notice`` with ``display: flex``.  Without a rule of its
        own, the Dismiss button on an archive page stored the dismissal
        and left the notice on screen.
        """
        css = (THEMES_DIR / f"{theme}.css").read_text(encoding="utf-8")
        assert re.search(r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important", css), (
            f"{theme}: no `[hidden] {{ display: none !important }}` rule, so "
            f"an element JS hides stays painted wherever a class sets display"
        )

    @pytest.mark.parametrize("theme", list_themes())
    def test_the_theme_has_a_metadata_file(self, theme: str) -> None:
        assert (THEMES_DIR / f"{theme}.json").is_file(), (
            f"{theme}: no companion .json; it would silently inherit the "
            f"default metadata, including a Google Fonts URL"
        )
