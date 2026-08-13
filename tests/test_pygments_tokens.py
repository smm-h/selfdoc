"""Syntax highlighting is a token layer, not two piles of literals.

Pygments hands out a stylesheet full of raw colour literals, once per
colour scheme.  Pasting both into a page produced 254 raw colour literals
in a built site's stylesheet and, worse, two independent rule sets that
could drift apart token by token -- a class styled in the light scheme and
forgotten in the dark one renders as whatever it inherits, and nothing
says so.

:func:`~selfdoc_core.html.generate_pygments_css` resolves both styles into
one set of custom properties and one set of rules that reference them.
What is asserted here is that property: no rule carries a literal, every
variable a rule names is defined on both sides of the split, and the three
token blocks are spelled the way a scheme-switching page needs them.
"""

from __future__ import annotations

import re

import pytest

from selfdoc_core.html import (
    HAS_PYGMENTS,
    PYGMENTS_SCOPE,
    PYGMENTS_VAR_PREFIX,
    generate_pygments_css,
)

pytestmark = pytest.mark.skipif(not HAS_PYGMENTS, reason="Pygments not installed")

#: Every light/dark pair the shipped themes declare, plus the defaults.
STYLE_PAIRS = [
    ("default", "monokai"),
    ("xcode", "github-dark"),
    ("friendly", "native"),
]

_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_COLOR_FN_RE = re.compile(r"\b(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb|color)\s*\(")
_VAR_RE = re.compile(r"var\((--[\w-]+)\)")


def _blocks(css: str) -> dict[str, str]:
    """``{selector: body}`` for every top-level and nested block in *css*."""
    out: dict[str, str] = {}
    for match in _RULE_RE.finditer(css):
        selector = " ".join(match.group(1).split())
        out[selector] = match.group(2)
    return out


def _defined(body: str) -> dict[str, str]:
    defined = {}
    for part in body.split(";"):
        prop, sep, value = part.partition(":")
        if sep and prop.strip().startswith("--"):
            defined[prop.strip()] = value.strip()
    return defined


@pytest.mark.parametrize("light,dark", STYLE_PAIRS)
class TestTheHighlightSheetIsTokenized:
    def test_no_rule_carries_a_colour_literal(self, light, dark):
        """Every colour a rule paints comes from a variable."""
        css = generate_pygments_css(light, dark)
        offenders = []
        for selector, body in _blocks(css).items():
            if selector.startswith(":root") or selector.startswith("html"):
                continue
            for part in body.split(";"):
                prop, sep, value = part.partition(":")
                if not sep:
                    continue
                if _HEX_RE.search(value) or _COLOR_FN_RE.search(value):
                    offenders.append(f"{selector} {{ {prop.strip()}: {value.strip()} }}")
        assert not offenders, offenders

    def test_every_variable_a_rule_names_is_defined_on_both_sides(self, light, dark):
        """A variable defined in one scheme and not the other is a drift."""
        css = generate_pygments_css(light, dark)
        blocks = _blocks(css)
        light_defs = _defined(blocks[":root"])
        dark_defs = _defined(blocks['html[data-theme="dark"]'])
        used = set()
        for selector, body in blocks.items():
            if selector.startswith(":root") or selector.startswith("html"):
                continue
            used.update(_VAR_RE.findall(body))
        assert used, "no rule references a variable at all"
        assert not (used - set(light_defs)), sorted(used - set(light_defs))
        assert not (used - set(dark_defs)), sorted(used - set(dark_defs))
        assert set(light_defs) == set(dark_defs)

    def test_the_three_token_blocks_are_spelled_for_a_scheme_switch(
        self, light, dark
    ):
        """Default, chosen-dark, and the JavaScript-free system fallback."""
        css = generate_pygments_css(light, dark)
        blocks = _blocks(css)
        assert ":root" in blocks
        assert 'html[data-theme="dark"]' in blocks
        assert "html:not([data-theme])" in blocks
        assert "@media (prefers-color-scheme: dark)" in css

    def test_every_rule_stays_inside_the_code_block_scope(self, light, dark):
        """Pygments' unscoped ``pre`` and ``linenos`` rules never reach a page."""
        css = generate_pygments_css(light, dark)
        for selector in _blocks(css):
            if selector.startswith(":root") or selector.startswith("html"):
                continue
            if selector.startswith("@media"):
                continue
            assert selector == PYGMENTS_SCOPE or selector.startswith(
                PYGMENTS_SCOPE + " "
            ), selector

    def test_the_two_schemes_really_differ(self, light, dark):
        """A tokenization that collapsed both styles into one would pass above."""
        blocks = _blocks(generate_pygments_css(light, dark))
        assert _defined(blocks[":root"]) != _defined(
            blocks['html[data-theme="dark"]']
        )

    def test_every_variable_carries_the_prefix(self, light, dark):
        css = generate_pygments_css(light, dark)
        for name in _VAR_RE.findall(css):
            assert name.startswith(PYGMENTS_VAR_PREFIX), name
