"""The real Pagefind indexer, run over a real build.

The attribute assertions elsewhere say what the HTML carries; this says
what Pagefind makes of it -- the filter groups a reader can actually pick
from, read back out of the index the build wrote.
"""

import glob
import gzip
import json
import os
import shutil
import subprocess
import sys

import pytest

from selfdoc.build import build


def _pagefind_available():
    """Whether the indexer this build shells out to is on this machine."""
    for cmd in (
        [sys.executable, "-m", "pagefind", "--version"],
        ["pagefind", "--version"],
    ):
        try:
            if subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


pytestmark = pytest.mark.skipif(
    not _pagefind_available(), reason="pagefind is not installed",
)


def _fragments(output_dir):
    """Every indexed page, as Pagefind recorded it."""
    fragments = []
    pattern = os.path.join(output_dir, "pagefind", "fragment", "*.pf_fragment")
    for path in sorted(glob.glob(pattern)):
        with gzip.open(path, "rb") as f:
            raw = f.read().decode("utf-8")
        # Each fragment is a short binary prefix followed by its JSON object.
        fragments.append(json.loads(raw[raw.index("{"):]))
    return fragments


@pytest.fixture()
def indexed_site(make_project):
    """A built project whose pages carry every facet, plus its index."""
    project = make_project(deploy={"provider": "github-pages"})
    docs_dir = project / "docs"
    (docs_dir / "index.md").write_text(
        "---\ntitle: Home\ntags: [intro, overview]\n---\n\n"
        "# Home\n\nWelcome to the documentation site.\n",
    )
    guides = docs_dir / "guides"
    guides.mkdir()
    (guides / "deploying.md").write_text(
        "---\ntitle: Deploying\ntype: guide\ntags: [deploy]\n---\n\n"
        "# Deploying\n\nPublish the built site to a static host.\n",
    )
    build(str(project))
    output_dir = str(project / "docs" / "_build")
    return output_dir, _fragments(output_dir)


class TestIndexerOutput:
    def test_the_build_wrote_an_index(self, indexed_site):
        output_dir, _ = indexed_site
        entry = os.path.join(output_dir, "pagefind", "pagefind-entry.json")
        assert os.path.isfile(entry), "the build did not index its own output"

    def test_the_build_wrote_the_ui_bundle(self, indexed_site):
        """The pages reference these; nothing fetches them from a CDN."""
        output_dir, _ = indexed_site
        for asset in ("pagefind-ui.js", "pagefind-ui.css"):
            assert os.path.isfile(os.path.join(output_dir, "pagefind", asset))

    def test_no_builtin_index_or_bundle(self, indexed_site):
        output_dir, _ = indexed_site
        assert not os.path.exists(os.path.join(output_dir, "search-index.json"))
        assert not os.path.exists(os.path.join(output_dir, "search.js"))

    def test_every_page_is_indexed(self, indexed_site):
        _, fragments = indexed_site
        assert len(fragments) >= 2

    def test_page_body_is_indexed(self, indexed_site):
        _, fragments = indexed_site
        content = " ".join(f["content"] for f in fragments)
        assert "Publish the built site" in content


class TestFilterGroups:
    """The facets the emitted attributes produce, as Pagefind reports them."""

    def test_single_valued_facets_reach_the_index(self, indexed_site):
        _, fragments = indexed_site
        guide = next(
            f for f in fragments if "deploying" in f["url"]
        )
        filters = guide["filters"]
        assert filters["version"] == ["1.0.0"]
        assert filters["type"] == ["guide"]
        assert filters["group"] == ["Guides"]
        assert filters["target"] == ["github-pages"]
        assert filters["project"]

    def test_tags_index_as_several_values(self, indexed_site):
        _, fragments = indexed_site
        home = next(f for f in fragments if f["url"].rstrip("/") == "")
        assert sorted(home["filters"]["tags"]) == ["intro", "overview"]

    def test_result_metadata_reaches_the_index(self, indexed_site):
        _, fragments = indexed_site
        guide = next(f for f in fragments if "deploying" in f["url"])
        assert guide["meta"]["type"] == "guide"
        assert guide["meta"]["project"]

    def test_facet_values_are_not_indexed_as_body_text(self, indexed_site):
        """The facet elements hold no text, so they add none to the page."""
        _, fragments = indexed_site
        guide = next(f for f in fragments if "deploying" in f["url"])
        assert "github-pages" not in guide["content"]


def test_no_pagefind_binary_is_a_hard_error(make_project, monkeypatch):
    """A build with no indexer fails; it never writes an unsearchable site."""
    project = make_project()

    def refuse(cmd, *args, **kwargs):
        raise FileNotFoundError(cmd)

    monkeypatch.setattr(subprocess, "run", refuse)
    with pytest.raises(RuntimeError, match="not installed"):
        build(str(project))


def test_indexer_is_the_python_module_or_the_binary():
    """Both installation shapes are usable; at least one is present here."""
    assert (
        shutil.which("pagefind") is not None
        or subprocess.run(
            [sys.executable, "-m", "pagefind", "--version"],
            capture_output=True, timeout=30,
        ).returncode == 0
    )
