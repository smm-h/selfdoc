"""The built tinymoon-theme site, measured by tinymoon's own checker.

The tinymoon theme composes the framework's shipped stylesheets, so a page
selfdoc builds under that theme is a page tinymoon painted.  The framework
publishes a conformance checker for exactly that situation: it reads the
built HTML, CSS and JS and reports every place a consumer left the design
language -- a raw colour literal outside the token layer, a non-zero
border radius, a banned native control, a ``title=`` attribute, an
off-origin resource load.

This is a **required** check, not a report.  ``selfdoc build`` writes a
whole site here, that site is handed to :func:`tinymoon.checker.scan_dir`,
and a violation fails the suite.  The fixture is deliberately wide: every
page class the emitters have a distinct shape for is present, because a
shape nobody builds is a shape the checker never sees.

The one carve-out below is written down rather than suppressed -- see
:data:`KNOWN_REMNANTS`.
"""

from __future__ import annotations

import json
import os
import re

import pytest

from tinymoon.checker import scan_dir

from conftest import default_config


#: Violations that are a question for the framework rather than a defect
#: here.  An entry is ``(rule, source-line substring) -> the analysis``:
#: both have to hold, so the carve-out covers one element on one kind of
#: line and nothing else.  The suite fails on any violation NOT described
#: here, and also fails when an entry stops being produced -- a stale
#: carve-out is a carve-out nobody rechecked.
#:
#: Nothing is added here to make a build pass, and the checker's own
#: allowlist file is deliberately not used.  An allowlist entry silences
#: the rule at the scan; what is wanted is the opposite -- the rule keeps
#: firing, and the reason it fires is written where a reader will meet it.
KNOWN_REMNANTS: dict[tuple[str, str], str] = {
    ("external-url", '<link rel="canonical"'): """
    A canonical link is metadata, not a resource: no browser ever fetches
    the address it names, and the whole point of the declaration is to
    name the page's address on the *deployed* origin, which is off-origin
    from anywhere the page is served during a build or a preview.

    The checker's own rule table classifies `href` as a load on every
    element except <a> and <area>, which is right for <link rel=stylesheet>,
    rel=preload, rel=icon and rel=modulepreload -- all real fetches -- and
    wrong for the metadata rel values: canonical, alternate with an
    hreflang, prev, next, author, license, me.  The distinction the table
    needs is not the element but the `rel`.

    None of the three ways to make it stop firing is honest.  An allowlist
    entry suppresses the rule for a set of URLs that grows with every page.
    Dropping the canonical throws away the declaration that tells a crawler
    an archived version and its stable address are the same document --
    which is the whole of selfdoc's canonicalization design.  Making the
    canonical relative makes it meaningless for the case it exists for: the
    same content served from a project's own site and from the assembly.

    So it stays, and it stays visible.
    """,
}


CANONICAL_BASE = "https://docs.example.com"


PAGE_INDEX = """\
# Fixture Project

Welcome to the fixture.  It carries every shape the emitters produce.

## A section

Body text with `inline code`, **bold**, and a [link](tables/).

> A quotation.

- A list item
- Another item

!!! note
    An admonition body.

!!! warning
    A sharper admonition.

```python
def hello():
    return "world"
```

| Version | Date |
| --- | --- |
| 0.9.2 | 2026-08-05 |
| 0.9.1 | 2026-07-01 |

### A deeper heading

More prose, with a term: the fixture defines *widget* as a thing.
"""

PAGE_TABLES = """\
# Tables

| Name | Type | Default |
| --- | --- | --- |
| `alpha` | string | none |
| `beta` | int | 0 |

Some text after the table.
"""

PAGE_GUIDE = """\
# Guide

A second page so the navigation tree has a group with children.

## Step one

Do the thing.

## Step two

Do the other thing.
"""


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _git(args, cwd) -> None:
    import subprocess

    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def build_conformance_fixture(root: str) -> str:
    """Write and build the fixture project under *root*; return its output.

    Two tagged versions, so the archive, the version picker and the
    superseded-version notice are all really emitted -- three shapes the
    checker would otherwise never look at.

    Importable so ``scripts/tm_conformance_report.py`` measures exactly the
    tree the suite asserts on rather than an approximation of it.
    """
    from selfdoc_core.build import build

    project = os.path.join(str(root), "project")
    os.makedirs(project, exist_ok=True)

    config = default_config(
        name="Fixture Project",
        description="A fixture project for the conformance sweep.",
        docs="docs/",
        output="docs/_build/",
        theme="tinymoon",
        base_url=CANONICAL_BASE,
        version="1.0.0",
        source=[],
        versions=[{"version": "0.9.0"}, {"version": "1.0.0"}],
    )
    _write(os.path.join(project, "selfdoc.json"), json.dumps(config, indent=2))

    docs = os.path.join(project, "docs")
    _write(os.path.join(docs, "index.md"), PAGE_INDEX)
    _write(os.path.join(docs, "tables.md"), PAGE_TABLES)
    _write(os.path.join(docs, "guide.md"), PAGE_GUIDE)

    _git(["init", "-b", "main"], cwd=project)
    _git(["add", "."], cwd=project)
    _git(["commit", "-m", "0.9.0"], cwd=project)
    _git(["tag", "v0.9.0"], cwd=project)
    _write(os.path.join(docs, "index.md"), PAGE_INDEX + "\nRevised for 1.0.0.\n")
    _git(["add", "docs/index.md"], cwd=project)
    _git(["commit", "-m", "1.0.0"], cwd=project)
    _git(["tag", "v1.0.0"], cwd=project)

    build(project)
    return os.path.join(project, "docs", "_build")


@pytest.fixture(scope="module")
def built_site(tmp_path_factory) -> str:
    """The fixture site, built once for the module."""
    return build_conformance_fixture(str(tmp_path_factory.mktemp("tm-conformance")))


def _by_rule(violations):
    counts: dict[str, int] = {}
    for v in violations:
        counts[v.rule] = counts.get(v.rule, 0) + 1
    return counts


def _source_line(site: str, violation) -> str:
    """The line of source *violation* was reported against."""
    path = os.path.join(site, *violation.path.split("/"))
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    index = violation.line - 1
    return lines[index] if 0 <= index < len(lines) else ""


def _remnant_key(site: str, violation):
    """The :data:`KNOWN_REMNANTS` key *violation* matches, or ``None``."""
    line = _source_line(site, violation)
    for key in KNOWN_REMNANTS:
        rule, marker = key
        if violation.rule == rule and marker in line:
            return key
    return None


class TestTheBuiltSiteIsConformant:
    def test_the_checker_finds_nothing_undeclared(self, built_site):
        """Every violation is either gone or a written-down remnant."""
        violations = scan_dir(built_site)
        unexpected = [
            v for v in violations if _remnant_key(built_site, v) is None
        ]
        assert not unexpected, (
            f"{len(unexpected)} tinymoon conformance violations "
            f"({_by_rule(unexpected)}):\n"
            + "\n".join(
                f"  {v.path}:{v.line} [{v.rule}] {v.message}"
                for v in unexpected[:40]
            )
        )

    def test_every_declared_remnant_is_still_produced(self, built_site):
        """A carve-out nobody rechecks is a carve-out that outlived its reason."""
        produced = {
            key
            for key in (
                _remnant_key(built_site, v) for v in scan_dir(built_site)
            )
            if key is not None
        }
        stale = set(KNOWN_REMNANTS) - produced
        assert not stale, (
            f"KNOWN_REMNANTS names violations the build no longer produces: "
            f"{sorted(stale)} -- delete the entries"
        )

    def test_the_pagefind_widget_is_not_shipped(self, built_site):
        """Nothing loads it under this theme, so nothing carries it."""
        from selfdoc_core.html import PAGEFIND_UI_ASSETS

        widget = os.path.join(built_site, "pagefind")
        present = sorted(
            name for name in os.listdir(widget) if name in PAGEFIND_UI_ASSETS
        )
        assert present == [], present
        # The query API the palette calls, its worker and the index entry
        # are a different payload, and they stay.
        for kept in ("pagefind.js", "pagefind-worker.js", "pagefind-entry.json"):
            assert os.path.isfile(os.path.join(widget, kept)), kept

    def test_the_framework_modules_are_the_closure_and_not_the_tree(
        self, built_site,
    ):
        """Only the modules a page really imports travel with the site."""
        import tinymoon

        from selfdoc_core.themes import theme_modules

        shipped = sorted(
            name for name in os.listdir(os.path.join(built_site, "js"))
            if name.endswith(".js")
        )
        assert shipped == theme_modules("tinymoon")
        whole_tree = [
            name
            for name in os.listdir(
                os.path.join(str(tinymoon.assets_path()), "js")
            )
            if name.endswith(".js")
        ]
        assert len(shipped) < len(whole_tree) / 4, (
            f"{len(shipped)} of {len(whole_tree)} framework modules shipped "
            f"-- the closure is supposed to be a small part of the tree"
        )

    def test_every_shipped_module_can_resolve_its_own_imports(
        self, built_site,
    ):
        """A module whose dependency did not travel is a page that breaks."""
        js_dir = os.path.join(built_site, "js")
        shipped = {
            name for name in os.listdir(js_dir) if name.endswith(".js")
        }
        for name in sorted(shipped):
            with open(os.path.join(js_dir, name), encoding="utf-8") as handle:
                source = handle.read()
            for specifier in re.findall(
                r"""(?:from|import)\s*\(?\s*["'](\./[\w.\-/]+\.js)["']""",
                source,
            ):
                assert specifier[2:] in shipped, (
                    f"{name} imports {specifier}, which the site does not carry"
                )
