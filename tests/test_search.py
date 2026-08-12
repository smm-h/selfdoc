"""Tests for the WebSite JSON-LD a search-capable site does and does not emit."""

import json
import os
import re

import pytest

from selfdoc.build import build
from conftest import default_config, DEFAULT_PREFIX


@pytest.fixture()
def project_dir(tmp_path):
    """Create a minimal selfdoc project in a temp directory."""
    config = default_config(docs="docs/", output="docs/_build/")
    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)

    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test Project\n\nWelcome.\n")

    with open(os.path.join(docs_dir, "guide.md"), "w", encoding="utf-8") as f:
        f.write("# Guide\n\nSome content.\n")

    return tmp_path


def _website_lds(index_html):
    """Every WebSite JSON-LD block on a built homepage, parsed."""
    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        index_html,
        re.DOTALL,
    )
    return [json.loads(b) for b in ld_blocks if '"WebSite"' in b]


def test_website_jsonld_survives(project_dir):
    """The homepage still declares one WebSite node, with name and url."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, DEFAULT_PREFIX, "index.html"), "r", encoding="utf-8") as f:
        index_html = f.read()

    website_lds = _website_lds(index_html)
    assert len(website_lds) == 1, "Expected exactly one WebSite JSON-LD block"
    assert website_lds[0]["@type"] == "WebSite"
    assert website_lds[0]["url"] == "https://example.com/"
    assert website_lds[0]["name"]


def test_website_jsonld_has_no_search_action(project_dir):
    """The SearchAction is gone: it advertised a ?q= duplicate-content URL.

    The pattern told crawlers that every search term had its own address,
    while the site serves one client-side-searched page for all of them.
    """
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, DEFAULT_PREFIX, "index.html"), "r", encoding="utf-8") as f:
        index_html = f.read()

    assert "potentialAction" not in _website_lds(index_html)[0]
    assert '"SearchAction"' not in index_html
    assert "search_term_string" not in index_html


def test_non_homepage_no_website_jsonld(project_dir):
    """Non-homepage pages do NOT have WebSite JSON-LD."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, DEFAULT_PREFIX, "guide", "index.html"), "r", encoding="utf-8") as f:
        guide_html = f.read()

    assert '"WebSite"' not in guide_html
    assert '"SearchAction"' not in guide_html
