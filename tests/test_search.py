"""Tests for search URL parameter handling and SearchAction JSON-LD."""

import json
import os
import re

import pytest

from selfdoc.build import build
from selfdoc.html import _generate_search_js


@pytest.fixture()
def project_dir(tmp_path):
    """Create a minimal selfdoc project in a temp directory."""
    config = {
        "language": "python",
        "source": ["src/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
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


def test_website_jsonld_has_search_action(project_dir):
    """WebSite JSON-LD on homepage includes potentialAction with SearchAction."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        index_html = f.read()

    # Extract all JSON-LD blocks
    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        index_html,
        re.DOTALL,
    )
    website_lds = [json.loads(b) for b in ld_blocks if '"WebSite"' in b]
    assert len(website_lds) == 1, "Expected exactly one WebSite JSON-LD block"

    website_ld = website_lds[0]
    assert website_ld["@type"] == "WebSite"
    assert "potentialAction" in website_ld

    action = website_ld["potentialAction"]
    assert action["@type"] == "SearchAction"
    assert "query-input" in action
    assert action["query-input"] == "required name=search_term_string"


def test_search_action_target_uses_base_url(project_dir):
    """SearchAction target URL uses the configured base_url."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        index_html = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        index_html,
        re.DOTALL,
    )
    website_lds = [json.loads(b) for b in ld_blocks if '"WebSite"' in b]
    assert len(website_lds) == 1

    action = website_lds[0]["potentialAction"]
    assert action["target"] == "https://example.com/?q={search_term_string}"


def test_search_js_has_url_parameter_handling(project_dir):
    """Generated HTML includes URLSearchParams handling for ?q= parameter."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    search_js_path = os.path.join(output_dir, "search.js")
    with open(search_js_path, "r", encoding="utf-8") as f:
        search_js = f.read()

    assert "URLSearchParams" in search_js
    assert "openSearch(urlQ)" in search_js or "openSearch(urlQ)" in search_js.replace(" ", "")


def test_non_homepage_no_website_jsonld(project_dir):
    """Non-homepage pages do NOT have WebSite JSON-LD."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "guide", "index.html"), "r", encoding="utf-8") as f:
        guide_html = f.read()

    assert '"WebSite"' not in guide_html
    assert '"SearchAction"' not in guide_html


def test_search_js_clears_url_param_on_close():
    """Search JS closeSearch function clears ?q= from the URL."""
    js = _generate_search_js()
    assert "searchParams.delete" in js or "searchParams.delete" in js.replace(" ", "")
    assert "replaceState" in js


def test_search_js_open_accepts_initial_query():
    """openSearch accepts an initial query parameter."""
    js = _generate_search_js()
    assert "openSearch(initialQuery)" in js or "function openSearch(initialQuery)" in js
