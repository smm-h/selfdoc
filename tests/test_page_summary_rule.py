"""Which pages print their frontmatter description above the H1.

The description block is presentation of the same string the ``description``
meta tag carries.  On a reference page that is a useful summary of what the
page covers.  On the home page and on a post it is the page's own opening
line said twice inside one viewport, because both of those open with a lead
paragraph an author wrote.

The rule is read off the page's identity, never off its prose: a home page
is ``index.md``, a post declares ``type: post``, and everything else keeps
the block.  Nothing compares the description against the first paragraph --
a rendering that changes with the wording is a rendering nobody can predict.
"""

import json
import os

import pytest

from conftest import DEFAULT_PREFIX, default_config
from selfdoc.build import build

SUMMARY_BLOCK = '<div class="page-summary">'


@pytest.fixture()
def project_dir(tmp_path):
    config = default_config(docs="docs/", output="docs/_build/")
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    return tmp_path


def _write(project_dir, name, text):
    path = os.path.join(project_dir, "docs", name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _built(project_dir, *parts):
    path = os.path.join(
        project_dir, "docs", "_build", DEFAULT_PREFIX, *parts,
    )
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_a_reference_page_keeps_its_summary(project_dir):
    _write(project_dir, "index.md", "# Home\n\nWelcome.\n")
    _write(
        project_dir, "reference.md",
        "---\ndescription: Every flag the command takes.\n---\n"
        "# Reference\n\nThe flags follow.\n",
    )

    build(str(project_dir))

    page = _built(project_dir, "reference", "index.html")
    assert SUMMARY_BLOCK in page
    assert "Every flag the command takes." in page


def test_the_home_page_does_not_repeat_its_description(project_dir):
    """The site description is already the home page's opening line."""
    _write(
        project_dir, "index.md",
        "---\ndescription: A curated index of the tools I build.\n---\n"
        "# Home\n\nA curated index of the tools I build, each linking to its "
        "documentation.\n",
    )

    build(str(project_dir))

    page = _built(project_dir, "index.html")
    assert SUMMARY_BLOCK not in page
    # The meta tag is untouched: only the on-page block is suppressed.
    assert 'name="description" content="A curated index of the tools I build."' in page


def test_a_post_does_not_repeat_its_description(project_dir):
    _write(project_dir, "index.md", "# Home\n\nWelcome.\n")
    _write(
        project_dir, "writing.md",
        "---\ntype: post\ndescription: Why the release flow waits for CI.\n---\n"
        "# Waiting for CI\n\nWhy the release flow waits for CI, and what it "
        "costs.\n",
    )

    build(str(project_dir))

    page = _built(project_dir, "writing", "index.html")
    assert SUMMARY_BLOCK not in page
    assert 'name="description" content="Why the release flow waits for CI."' in page
