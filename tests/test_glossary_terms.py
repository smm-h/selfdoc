"""Tests for the definition/glossary machinery.

A term exists only because an author declared it: definition-list syntax,
the ``list-glossary`` directive, or a hand-written ``<dfn>`` in the
markdown.  Nothing is inferred from prose.  Every definition site carries
an id, the glossary's Source link carries that fragment, and the
definition site links back to its glossary entry.
"""

import json
import os
import re

import pytest

from selfdoc.build import build
from selfdoc.html import generate_html, md_to_html
from conftest import default_config, DEFAULT_PREFIX, TEST_AUTHOR


@pytest.fixture()
def project_dir(tmp_path):
    """A minimal selfdoc project in a temp directory."""
    config = default_config(docs="docs/", output="docs/_build/")
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test Project\n\nWelcome.\n")
    return tmp_path


def _read(project_dir, *parts):
    path = os.path.join(project_dir, "docs", "_build", DEFAULT_PREFIX, *parts)
    with open(path, encoding="utf-8") as f:
        return f.read()


# --- No term is ever inferred from prose ---


@pytest.mark.parametrize("md", [
    "## Overview\n\nselfdoc is a static site generator.\n",
    "## Function\n\n`parse_directives` is a function.\n",
    "### Directives\n\nA directive refers to a block.\n",
    "## Marketing\n\nNone of this means the tool is slow.\n",
    "## Thing\n\nThe export represents the whole build.\n",
])
def test_definitional_prose_declares_nothing(md):
    """"X is a ..." after a heading is prose, not a declaration."""
    assert "<dfn" not in md_to_html(md)


def test_prose_only_site_has_no_glossary_page(project_dir):
    """A project that declares no term gets no glossary page and no nav link."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Test Project\n\n"
            "## Overview\n\n"
            "Testproject is a documentation generator.\n"
        )

    build(str(project_dir))

    out = os.path.join(project_dir, "docs", "_build", DEFAULT_PREFIX)
    assert not os.path.exists(os.path.join(out, "glossary", "index.html"))
    assert ">Glossary<" not in _read(project_dir, "index.html")


def test_prose_only_page_has_no_defined_term_jsonld(project_dir):
    """No declaration means no DefinedTermSet JSON-LD either."""
    html_files = generate_html(
        {"index.md": (
            "# Test Page\n\n"
            "## Overview\n\n"
            "Selfdoc is a static site generator.\n"
        )},
        project_name="Test",
        author=TEST_AUTHOR,
    )
    assert "DefinedTermSet" not in html_files["index.html"]


# --- Declaration forms ---


def test_definition_list_declares_a_term(project_dir):
    """``Term\\n: Definition`` is a declaration."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "terms.md"), "w", encoding="utf-8") as f:
        f.write("# Terms\n\nAPI\n: Application Programming Interface\n")

    build(str(project_dir))

    assert "API" in _read(project_dir, "glossary", "index.html")


def test_inline_dfn_declares_a_term(project_dir):
    """A hand-written ``<dfn>`` in a paragraph is a declaration."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "terms.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Terms\n\n"
            "A <dfn>widget</dfn> is a reusable interface element.\n"
        )

    build(str(project_dir))

    assert "widget" in _read(project_dir, "glossary", "index.html")


def test_glossary_directive_declares_terms(project_dir):
    """The ``list-glossary`` directive is a declaration."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "terms.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Terms\n\n"
            ":<: list-glossary\n"
            ":=:\n"
            "::: **Widget**: A reusable interface element\n"
            ":>:\n"
        )

    build(str(project_dir))

    assert "Widget" in _read(project_dir, "glossary", "index.html")


# --- The anchor contract ---


def test_definition_site_dfn_carries_an_id(project_dir):
    """Every declared definition site gets an id on its ``<dfn>``."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "terms.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Terms\n\n"
            "API\n: Application Programming Interface\n\n"
            "A <dfn>widget</dfn> is a reusable interface element.\n"
        )

    build(str(project_dir))
    content = _read(project_dir, "terms", "index.html")

    assert 'id="term-api"' in content
    assert 'id="term-widget"' in content


def test_glossary_source_link_fragment_exists_on_target_page(project_dir):
    """The glossary Source link's fragment is a real id on the source page.

    The live defect: the glossary linked ``#slugify(term)``, an id no page
    ever emitted, so the link scrolled nowhere.
    """
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "terms.md"), "w", encoding="utf-8") as f:
        f.write("# Terms\n\nAPI\n: Application Programming Interface\n")

    build(str(project_dir))

    glossary = _read(project_dir, "glossary", "index.html")
    hrefs = re.findall(r'<a href="([^"]*)">Source</a>', glossary)
    assert hrefs, "no Source link in the glossary"
    href = hrefs[0]
    assert "#" in href, f"Source link carries no fragment: {href}"
    fragment = href.split("#", 1)[1]

    target = _read(project_dir, "terms", "index.html")
    assert f'id="{fragment}"' in target, (
        f"fragment #{fragment} is not an id on the target page"
    )


def test_cross_page_term_link_fragment_exists_on_target_page(project_dir):
    """A cross-page term link's fragment is a real id on the defining page."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "terms.md"), "w", encoding="utf-8") as f:
        f.write("# Terms\n\nWidget\n: A reusable interface element\n")
    with open(os.path.join(docs_dir, "guide.md"), "w", encoding="utf-8") as f:
        f.write("# Guide\n\nEvery Widget needs a home somewhere.\n")

    build(str(project_dir))

    guide = _read(project_dir, "guide", "index.html")
    match = re.search(r'<a href="([^"]*)" class="term-link"', guide)
    assert match, "no cross-page term link emitted"
    fragment = match.group(1).split("#", 1)[1]
    assert f'id="{fragment}"' in _read(project_dir, "terms", "index.html")


def test_term_id_does_not_collide_with_a_heading_id(project_dir):
    """A term id never silently reuses a heading's id."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "terms.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Terms\n\n"
            "## Term Api\n\n"
            "Some prose about the section.\n\n"
            "API\n: Application Programming Interface\n"
        )

    build(str(project_dir))
    content = _read(project_dir, "terms", "index.html")

    ids = re.findall(r'\sid="([^"]+)"', content)
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


# --- The reverse affordance ---


def test_definition_site_links_to_its_glossary_entry(project_dir):
    """The definition site is clickable and carries the definition tooltip."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "terms.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Terms\n\n"
            "API\n: Application Programming Interface. Widely used.\n"
        )

    build(str(project_dir))
    content = _read(project_dir, "terms", "index.html")

    match = re.search(
        r'<dfn id="term-api"[^>]*>\s*<a class="term-def-link" '
        r'href="([^"]*)"',
        content,
    )
    assert match, f"definition site is not a link: {content[:0]}"
    assert match.group(1).endswith("glossary/#term-api"), match.group(1)
    assert 'title="Application Programming Interface."' in content


def test_glossary_page_entry_id_matches_the_reverse_link(project_dir):
    """The fragment the definition site links to exists on the glossary page."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "terms.md"), "w", encoding="utf-8") as f:
        f.write("# Terms\n\nAPI\n: Application Programming Interface\n")

    build(str(project_dir))

    source = _read(project_dir, "terms", "index.html")
    match = re.search(r'class="term-def-link" href="([^"]*)"', source)
    assert match
    fragment = match.group(1).split("#", 1)[1]
    assert f'id="{fragment}"' in _read(project_dir, "glossary", "index.html")


def test_other_occurrences_on_the_defining_page_are_not_linked(project_dir):
    """Only the definition site links; other mentions on that page do not."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "terms.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Terms\n\n"
            "Widget\n: A reusable interface element\n\n"
            "Every Widget lives in a tree.\n"
        )

    build(str(project_dir))
    content = _read(project_dir, "terms", "index.html")

    assert content.count('class="term-def-link"') == 1
    assert 'class="term-link"' not in content
