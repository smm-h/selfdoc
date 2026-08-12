"""Internal ``.md`` links must resolve under the directory addressing.

A page written as ``guide.md`` is emitted as ``guide/index.html``, so the
page that writes a link sits one directory deeper than its source did.
Every link a docs page writes therefore has to be re-expressed against the
*emitted* page's directory, not against the source file's -- the whole
point of this module's fixtures.

Two shapes are covered:

* the working tree, where a ``.md`` link is the only correct form and a
  legacy ``.html`` link is a defect the resolution check reports;
* an archive build, whose source came out of an immutable git tag and can
  therefore carry links written before the addressing changed.
"""

import json
import os
import re
import subprocess

import pytest

from selfdoc.build import build
from selfdoc_core.resolution import check_output_resolution


BASE_URL = "https://example.com"


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True)


# Every internal link shape a page can write: a sibling, a sibling with an
# anchor, a same-page anchor, the root index, a subdirectory page, a page
# one level up, and a page two levels up.
LINKED_PAGES = {
    "index.md": (
        "# Fixture\n\n"
        "Root page linking [the guide](guide.md), "
        "[a section of it](guide.md#section-two) and "
        "[the API](reference/api.md).\n"
    ),
    "guide.md": (
        "---\ntitle: Guide\n---\n\n"
        "# Guide\n\n"
        "A sibling: [checks](checks.md). "
        "With an anchor: [detail](checks.md#detail). "
        "Itself: [below](#section-two). "
        "Home: [index](index.md). "
        "Down: [notes](reference/deep/notes.md).\n\n"
        "## Section two\n\nSecond section.\n"
    ),
    "checks.md": (
        "---\ntitle: Checks\n---\n\n"
        "# Checks\n\nBack to [the guide](guide.md).\n\n"
        "## Detail\n\nThe detail.\n"
    ),
    "reference/api.md": (
        "---\ntitle: API\n---\n\n"
        "# API\n\n"
        "Up: [guide](../guide.md). Down: [notes](deep/notes.md).\n"
    ),
    "reference/deep/notes.md": (
        "---\ntitle: Notes\n---\n\n"
        "# Notes\n\n"
        "Up: [api](../api.md). Root: [index](../../index.md).\n"
    ),
}


def _write_project(root, pages, *, tag=None):
    """A single-version project holding *pages*, built at the origin root."""
    root.mkdir(parents=True, exist_ok=True)
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "search_engine": "pagefind",
        "base_url": BASE_URL,
        "author": {"name": "Test Author", "url": "https://author.example"},
        "version": "0.2.0",
        "versions": [{"version": "0.2.0"}],
        "locales": [{"code": "en", "label": "EN", "default": True}],
    }
    (root / "selfdoc.json").write_text(json.dumps(config, indent=2))
    src = root / "src"
    src.mkdir(exist_ok=True)
    (src / "__init__.py").write_text('"""Fixture package."""\n')
    docs = root / "docs"
    for rel, text in pages.items():
        path = docs / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    if tag:
        _git(["init"], cwd=root)
        _git(["add", "."], cwd=root)
        _git(["commit", "-m", "initial"], cwd=root)
        _git(["tag", tag], cwd=root)
    return root


def _hrefs(output_dir, page):
    with open(os.path.join(output_dir, page), encoding="utf-8") as f:
        html = f.read()
    body = html.split('<article', 1)[-1].split("</article>", 1)[0]
    return re.findall(r'href="([^"]*)"', body)


def _build(root):
    build(str(root))
    return os.path.join(str(root), "docs", "_build")


# -- The working tree: `.md` links, resolved against the emitted page ----


def test_every_md_link_resolves(tmp_path):
    """The whole-tree check has nothing to say about a page full of links."""
    project = _write_project(tmp_path / "links", LINKED_PAGES)
    output_dir = _build(project)
    assert check_output_resolution(output_dir, base_url=BASE_URL) == []


def test_a_sibling_link_hops_out_of_the_pages_own_directory(tmp_path):
    """`checks.md` written on `guide.md` is `../checks/`, not `checks/`.

    ``guide.md`` is emitted at ``guide/index.html``, so the bare
    ``checks/`` the old rewriter produced resolved to ``guide/checks/``
    and named nothing.
    """
    project = _write_project(tmp_path / "sibling", LINKED_PAGES)
    output_dir = _build(project)
    hrefs = _hrefs(output_dir, "guide/index.html")
    assert "../checks/" in hrefs
    assert "checks/" not in hrefs


def test_a_sibling_anchor_link_is_rewritten_too(tmp_path):
    """`checks.md#detail` is an address like any other, fragment kept."""
    project = _write_project(tmp_path / "anchor", LINKED_PAGES)
    output_dir = _build(project)
    hrefs = _hrefs(output_dir, "guide/index.html")
    assert "../checks/#detail" in hrefs
    assert not any(h.endswith(".md#detail") for h in hrefs)


def test_a_same_page_anchor_is_left_alone(tmp_path):
    project = _write_project(tmp_path / "self", LINKED_PAGES)
    output_dir = _build(project)
    assert "#section-two" in _hrefs(output_dir, "guide/index.html")


def test_the_root_index_is_reached_from_a_page_one_level_down(tmp_path):
    project = _write_project(tmp_path / "home", LINKED_PAGES)
    output_dir = _build(project)
    assert "../index.html" in _hrefs(output_dir, "guide/index.html")


def test_the_root_page_links_its_children_without_a_hop(tmp_path):
    """`index.md` is emitted at the mount root, so its links climb nothing."""
    project = _write_project(tmp_path / "root", LINKED_PAGES)
    output_dir = _build(project)
    hrefs = _hrefs(output_dir, "index.html")
    assert "guide/" in hrefs
    assert "guide/#section-two" in hrefs
    assert "reference/api/" in hrefs


def test_a_subdirectory_page_links_up_and_down(tmp_path):
    project = _write_project(tmp_path / "sub", LINKED_PAGES)
    output_dir = _build(project)
    hrefs = _hrefs(output_dir, "reference/api/index.html")
    assert "../../guide/" in hrefs
    assert "../deep/notes/" in hrefs

    # `notes.md` is emitted at reference/deep/notes/, so its source-level
    # sibling-of-the-parent hop gains one level on the way out.
    deep = _hrefs(output_dir, "reference/deep/notes/index.html")
    assert "../../api/" in deep
    assert "../../../index.html" in deep


def test_a_markdown_link_inside_a_code_block_is_not_rewritten(tmp_path):
    """A code sample shows source, so its text is not an address to fix."""
    pages = dict(LINKED_PAGES)
    pages["checks.md"] += "\n```\n[example](thing.md)\n```\n"
    project = _write_project(tmp_path / "code", pages)
    output_dir = _build(project)
    with open(
        os.path.join(output_dir, "checks", "index.html"), encoding="utf-8",
    ) as f:
        html = f.read()
    assert "[example](thing.md)" in html


# -- Archives: legacy `.html` links out of an immutable tag --------------


LEGACY_PAGES = {
    "index.md": "# Fixture\n\nRoot page linking [the guide](guide.html).\n",
    "guide.md": (
        "---\ntitle: Guide\n---\n\n"
        "# Guide\n\n"
        "A sibling: [checks](checks.html). "
        "With an anchor: [detail](checks.html#detail). "
        "Home: [index](index.html). "
        "Down: [notes](reference/deep/notes.html).\n"
    ),
    "checks.md": (
        "---\ntitle: Checks\n---\n\n"
        "# Checks\n\nBack to [the guide](guide.html).\n\n"
        "## Detail\n\nThe detail.\n"
    ),
    "reference/deep/notes.md": (
        "---\ntitle: Notes\n---\n\n"
        "# Notes\n\nUp: [index](../../index.html).\n"
    ),
}


def _multiversion_project(root, archived_pages, current_pages):
    """A project whose 0.1.0 tag holds *archived_pages* and whose tree holds
    *current_pages*, so one build renders both an archive and a current
    version."""
    root.mkdir(parents=True, exist_ok=True)
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "search_engine": "pagefind",
        "base_url": BASE_URL,
        "author": {"name": "Test Author", "url": "https://author.example"},
        "version": "0.2.0",
        "versions": [{"version": "0.1.0"}, {"version": "0.2.0"}],
        "locales": [{"code": "en", "label": "EN", "default": True}],
    }
    (root / "selfdoc.json").write_text(json.dumps(config, indent=2))
    src = root / "src"
    src.mkdir(exist_ok=True)
    (src / "__init__.py").write_text('"""Fixture package."""\n')

    docs = root / "docs"

    def _lay(pages):
        if docs.exists():
            for dirpath, _dirs, files in os.walk(docs):
                for name in files:
                    if name.endswith(".md"):
                        os.remove(os.path.join(dirpath, name))
        for rel, text in pages.items():
            path = docs / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    _lay(archived_pages)
    _git(["init"], cwd=root)
    _git(["add", "."], cwd=root)
    _git(["commit", "-m", "0.1.0"], cwd=root)
    _git(["tag", "v0.1.0"], cwd=root)

    _lay(current_pages)
    _git(["add", "-A"], cwd=root)
    _git(["commit", "-m", "0.2.0"], cwd=root)
    _git(["tag", "v0.2.0"], cwd=root)
    return root


def test_an_archive_renders_legacy_html_links_that_resolve(tmp_path):
    """A tag is immutable, so its pre-scheme links are mapped at render time."""
    project = _multiversion_project(
        tmp_path / "archive", LEGACY_PAGES, LINKED_PAGES,
    )
    output_dir = _build(project)
    assert os.path.isfile(
        os.path.join(output_dir, "v", "0.1.0", "guide", "index.html")
    )
    assert check_output_resolution(output_dir, base_url=BASE_URL) == []

    hrefs = _hrefs(output_dir, "v/0.1.0/guide/index.html")
    assert "../checks/" in hrefs
    assert "../checks/#detail" in hrefs
    assert "../index.html" in hrefs
    assert "../reference/deep/notes/" in hrefs


def test_the_working_tree_gets_no_legacy_tolerance(tmp_path):
    """The same link form in the working tree is still a broken reference."""
    project = _write_project(tmp_path / "strict", LEGACY_PAGES)
    output_dir = _build(project)
    lints = check_output_resolution(output_dir, base_url=BASE_URL)
    assert lints, "a legacy .html link in the working tree must be reported"
    assert {lint.code for lint in lints} == {"LINK001"}
    assert any("checks.html" in lint.message for lint in lints)
