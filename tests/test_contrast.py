"""WCAG AA contrast ratio tests for all selfdoc themes.

Implements the WCAG 2.1 relative luminance and contrast ratio formulas,
then asserts that every foreground/background color pair in both themes
meets the 4.5:1 AA threshold for normal text.
"""

import re
from pathlib import Path

import pytest

THEMES_DIR = Path(__file__).resolve().parent.parent / "selfdoc_core" / "themes"


# ---------------------------------------------------------------------------
# WCAG contrast ratio computation
# ---------------------------------------------------------------------------

def _linearize(c: int) -> float:
    """Convert an 8-bit sRGB channel value to linear light."""
    s = c / 255.0
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """Return WCAG relative luminance for a hex color (e.g. '#abcdef')."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """Return WCAG contrast ratio between two hex colors."""
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


# ---------------------------------------------------------------------------
# CSS parsing helpers
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"--([a-z][-a-z0-9]*)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;")


def _parse_vars(block: str) -> dict[str, str]:
    """Extract CSS custom property definitions from a block of text."""
    return {m.group(1): m.group(2) for m in _VAR_RE.finditer(block)}


def _extract_root_vars(css: str) -> dict[str, str]:
    """Extract variables from the first :root { ... } block."""
    m = re.search(r":root\s*\{([^}]+)\}", css)
    assert m, "No :root block found"
    return _parse_vars(m.group(1))


def _extract_dark_media_vars(css: str) -> dict[str, str]:
    """Extract variables from @media (prefers-color-scheme: dark) { :root... }."""
    # Find the media block, then the :root:not(...) block inside
    pattern = r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{[^}]*:root:not\(\[data-theme=\"light\"\]\)\s*\{([^}]+)\}"
    m = re.search(pattern, css)
    assert m, "No dark mode media block found"
    return _parse_vars(m.group(1))


def _extract_hc_light_vars(css: str) -> dict[str, str]:
    """Extract variables from the light high-contrast block."""
    pattern = r"@media\s*\(prefers-contrast:\s*more\)\s*\{\s*:root\s*\{([^}]+)\}"
    m = re.search(pattern, css)
    assert m, "No light high-contrast block found"
    return _parse_vars(m.group(1))


def _extract_hc_dark_vars(css: str) -> dict[str, str]:
    """Extract variables from the dark high-contrast block."""
    pattern = (
        r"@media\s*\(prefers-contrast:\s*more\)\s*and\s*"
        r"\(prefers-color-scheme:\s*dark\)\s*\{[^}]*"
        r":root:not\(\[data-theme=\"light\"\]\)\s*\{([^}]+)\}"
    )
    m = re.search(pattern, css)
    assert m, "No dark high-contrast block found"
    return _parse_vars(m.group(1))


# ---------------------------------------------------------------------------
# Shared assertion logic
# ---------------------------------------------------------------------------

AA_THRESHOLD = 4.5


def _assert_pairs_pass(
    vars_: dict[str, str], pairs: list[tuple[str, str]], label: str
) -> None:
    """Assert every (fg_var, bg_var) pair passes AA in the given variable set."""
    for fg_var, bg_var in pairs:
        fg = vars_.get(fg_var)
        bg = vars_.get(bg_var)
        if fg is None or bg is None:
            continue
        ratio = contrast_ratio(fg, bg)
        assert ratio >= AA_THRESHOLD, (
            f"{label}: --{fg_var} ({fg}) on --{bg_var} ({bg}) "
            f"= {ratio:.2f}:1 < {AA_THRESHOLD}:1"
        )


# Color pairs that must pass AA.  (foreground_var, background_var)
TEXT_PAIRS = [
    ("text", "bg"),
    ("text-secondary", "bg"),
    ("heading", "bg"),
    ("link", "bg"),
    ("link-hover", "bg"),
    ("sidebar-text", "sidebar-bg"),
    ("sidebar-active", "sidebar-bg"),
    ("badge-text", "badge-bg"),
    ("topbar-text", "topbar-bg"),
]


# ---------------------------------------------------------------------------
# Clean theme tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def clean_css() -> str:
    return (THEMES_DIR / "clean.css").read_text()


class TestCleanTheme:
    def test_light_contrast(self, clean_css: str) -> None:
        vars_ = _extract_root_vars(clean_css)
        _assert_pairs_pass(vars_, TEXT_PAIRS, "clean-light")

    def test_dark_contrast(self, clean_css: str) -> None:
        root = _extract_root_vars(clean_css)
        dark = _extract_dark_media_vars(clean_css)
        merged = {**root, **dark}
        _assert_pairs_pass(merged, TEXT_PAIRS, "clean-dark")

    def test_hc_light_has_overrides(self, clean_css: str) -> None:
        hc = _extract_hc_light_vars(clean_css)
        for var in ("link", "link-hover", "text-secondary", "sidebar-text", "sidebar-active"):
            assert var in hc, f"clean high-contrast light missing --{var}"

    def test_hc_dark_has_overrides(self, clean_css: str) -> None:
        hc = _extract_hc_dark_vars(clean_css)
        for var in ("link", "link-hover", "text-secondary", "sidebar-text", "sidebar-active"):
            assert var in hc, f"clean high-contrast dark missing --{var}"

    def test_hc_light_contrast(self, clean_css: str) -> None:
        root = _extract_root_vars(clean_css)
        hc = _extract_hc_light_vars(clean_css)
        merged = {**root, **hc}
        _assert_pairs_pass(merged, TEXT_PAIRS, "clean-hc-light")

    def test_hc_dark_contrast(self, clean_css: str) -> None:
        root = _extract_root_vars(clean_css)
        dark = _extract_dark_media_vars(clean_css)
        hc = _extract_hc_dark_vars(clean_css)
        merged = {**root, **dark, **hc}
        _assert_pairs_pass(merged, TEXT_PAIRS, "clean-hc-dark")


# ---------------------------------------------------------------------------
# Minimal theme tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def minimal_css() -> str:
    return (THEMES_DIR / "minimal.css").read_text()


class TestMinimalTheme:
    def test_light_contrast(self, minimal_css: str) -> None:
        vars_ = _extract_root_vars(minimal_css)
        _assert_pairs_pass(vars_, TEXT_PAIRS, "minimal-light")

    def test_dark_contrast(self, minimal_css: str) -> None:
        root = _extract_root_vars(minimal_css)
        dark = _extract_dark_media_vars(minimal_css)
        merged = {**root, **dark}
        _assert_pairs_pass(merged, TEXT_PAIRS, "minimal-dark")

    def test_hc_light_has_overrides(self, minimal_css: str) -> None:
        hc = _extract_hc_light_vars(minimal_css)
        for var in ("link", "link-hover", "text-secondary", "sidebar-text", "sidebar-active"):
            assert var in hc, f"minimal high-contrast light missing --{var}"

    def test_hc_dark_has_overrides(self, minimal_css: str) -> None:
        hc = _extract_hc_dark_vars(minimal_css)
        for var in ("link", "link-hover", "text-secondary", "sidebar-text", "sidebar-active"):
            assert var in hc, f"minimal high-contrast dark missing --{var}"

    def test_hc_light_contrast(self, minimal_css: str) -> None:
        root = _extract_root_vars(minimal_css)
        hc = _extract_hc_light_vars(minimal_css)
        merged = {**root, **hc}
        _assert_pairs_pass(merged, TEXT_PAIRS, "minimal-hc-light")

    def test_hc_dark_contrast(self, minimal_css: str) -> None:
        root = _extract_root_vars(minimal_css)
        dark = _extract_dark_media_vars(minimal_css)
        hc = _extract_hc_dark_vars(minimal_css)
        merged = {**root, **dark, **hc}
        _assert_pairs_pass(merged, TEXT_PAIRS, "minimal-hc-dark")


# ---------------------------------------------------------------------------
# tinymoon theme tests
# ---------------------------------------------------------------------------

# tinymoon rests in dark and reassigns for light, the opposite of the two
# themes above, so its blocks are read the other way round: :root is the
# dark set, and the media query names light.


def _extract_light_media_vars(css: str) -> dict[str, str]:
    """Variables from @media (prefers-color-scheme: light) { :root... }."""
    pattern = (
        r'@media\s*\(prefers-color-scheme:\s*light\)\s*\{[^}]*'
        r':root:not\(\[data-theme="dark"\]\)\s*\{([^}]+)\}'
    )
    m = re.search(pattern, css)
    assert m, "No light mode media block found"
    return _parse_vars(m.group(1))


def _extract_hc_light_pairing_vars(css: str) -> dict[str, str]:
    """Variables from the (prefers-contrast: more) and (light) block."""
    pattern = (
        r"@media\s*\(prefers-contrast:\s*more\)\s*and\s*"
        r"\(prefers-color-scheme:\s*light\)\s*\{[^}]*"
        r':root:not\(\[data-theme="dark"\]\)\s*\{([^}]+)\}'
    )
    m = re.search(pattern, css)
    assert m, "No light high-contrast block found"
    return _parse_vars(m.group(1))


@pytest.fixture(scope="module")
def tinymoon_css() -> str:
    return (THEMES_DIR / "tinymoon.css").read_text()


class TestTinymoonTheme:
    def test_dark_contrast(self, tinymoon_css: str) -> None:
        """:root is the dark set here, not the light one."""
        vars_ = _extract_root_vars(tinymoon_css)
        _assert_pairs_pass(vars_, TEXT_PAIRS, "tinymoon-dark")

    def test_light_contrast(self, tinymoon_css: str) -> None:
        root = _extract_root_vars(tinymoon_css)
        light = _extract_light_media_vars(tinymoon_css)
        merged = {**root, **light}
        _assert_pairs_pass(merged, TEXT_PAIRS, "tinymoon-light")

    def test_the_explicit_light_block_matches_the_media_block(
        self, tinymoon_css: str,
    ) -> None:
        """Two spellings of one reassignment: they must agree.

        The media block covers the system state and the attribute block
        the explicit one.  A value that drifts between them means the
        page changes colour when the reader picks the scheme their
        system already reported.
        """
        media = _extract_light_media_vars(tinymoon_css)
        m = re.search(r'\[data-theme="light"\]\s*\{([^}]+)\}', tinymoon_css)
        assert m, "No explicit [data-theme=\"light\"] block"
        explicit = _parse_vars(m.group(1))
        assert media == explicit

    def test_the_explicit_dark_block_matches_the_resting_state(
        self, tinymoon_css: str,
    ) -> None:
        """[data-theme="dark"] restates :root; it must restate it exactly."""
        root = _extract_root_vars(tinymoon_css)
        m = re.search(r'\[data-theme="dark"\]\s*\{([^}]+)\}', tinymoon_css)
        assert m, 'No explicit [data-theme="dark"] block'
        explicit = _parse_vars(m.group(1))
        # :root carries a few variables the override has no reason to
        # restate (the font stack, the durations); every colour it does
        # restate has to match.
        for name, value in explicit.items():
            assert root.get(name) == value, (
                f'[data-theme="dark"] --{name} is {value}, :root has '
                f"{root.get(name)}"
            )

    def test_hc_dark_has_overrides(self, tinymoon_css: str) -> None:
        hc = _extract_hc_light_vars(tinymoon_css)
        for var in ("link", "link-hover", "text-secondary", "sidebar-text",
                    "sidebar-active"):
            assert var in hc, f"tinymoon high-contrast dark missing --{var}"

    def test_hc_light_has_overrides(self, tinymoon_css: str) -> None:
        hc = _extract_hc_light_pairing_vars(tinymoon_css)
        for var in ("link", "link-hover", "text-secondary", "sidebar-text",
                    "sidebar-active"):
            assert var in hc, f"tinymoon high-contrast light missing --{var}"

    def test_hc_dark_contrast(self, tinymoon_css: str) -> None:
        root = _extract_root_vars(tinymoon_css)
        hc = _extract_hc_light_vars(tinymoon_css)
        merged = {**root, **hc}
        _assert_pairs_pass(merged, TEXT_PAIRS, "tinymoon-hc-dark")

    def test_hc_light_contrast(self, tinymoon_css: str) -> None:
        root = _extract_root_vars(tinymoon_css)
        light = _extract_light_media_vars(tinymoon_css)
        hc = _extract_hc_light_pairing_vars(tinymoon_css)
        merged = {**root, **light, **hc}
        _assert_pairs_pass(merged, TEXT_PAIRS, "tinymoon-hc-light")


# ---------------------------------------------------------------------------
# Unit tests for the contrast ratio formula itself
# ---------------------------------------------------------------------------

class TestContrastFormula:
    def test_black_on_white(self) -> None:
        assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.1)

    def test_white_on_white(self) -> None:
        assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)

    def test_symmetric(self) -> None:
        assert contrast_ratio("#ff0000", "#0000ff") == contrast_ratio(
            "#0000ff", "#ff0000"
        )

    def test_known_value(self) -> None:
        # #767676 on white is the famous ~4.54:1 threshold gray
        ratio = contrast_ratio("#767676", "#ffffff")
        assert 4.5 <= ratio <= 4.6
