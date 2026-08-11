"""Tests for search filter syntax and chip UI (Phase 4)."""

import json
import os
import re

import pytest

from selfdoc.build import build
from selfdoc.html import _generate_search_js, _render_search_dialog
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
        f.write("# Guide\n\nSome content about features.\n")

    return tmp_path


def test_search_dialog_has_default_version_attr(project_dir):
    """Built HTML search dialog has data-default-version attribute."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    index_path = os.path.join(output_dir, DEFAULT_PREFIX, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'data-default-version="1.0.0"' in html


def test_render_search_dialog_version_attr():
    """_render_search_dialog includes data-default-version when version given."""
    html = _render_search_dialog(asset_prefix="", current_version="2.5.0")
    assert 'data-default-version="2.5.0"' in html


def test_render_search_dialog_no_version_attr():
    """_render_search_dialog omits data-default-version when version empty."""
    html = _render_search_dialog(asset_prefix="")
    assert 'data-default-version' not in html


def test_search_index_entries_have_metadata(project_dir):
    """search-index.json entries contain all metadata fields from Phase 0.7."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    index_path = os.path.join(output_dir, "search-index.json")
    with open(index_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    assert len(entries) > 0
    required_keys = {"title", "path", "body", "version", "locale", "group", "type", "target", "project", "tags"}
    for entry in entries:
        assert required_keys.issubset(set(entry.keys())), (
            f"Entry missing keys: {required_keys - set(entry.keys())}"
        )


def test_search_js_contains_filter_functions(project_dir):
    """Generated search.js contains parseSearchQuery and applyFilters."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    search_js_path = os.path.join(output_dir, "search.js")
    with open(search_js_path, "r", encoding="utf-8") as f:
        js = f.read()

    assert "parseSearchQuery" in js
    assert "applyFilters" in js
    assert "_FILTER_KEYS" in js


def test_search_js_contains_chip_rendering():
    """Generated search JS includes chip container and renderChips function."""
    js = _generate_search_js()
    assert "search-chips" in js
    assert "renderChips" in js
    assert "chip-remove" in js
    assert "search-chip" in js


def test_search_js_contains_filter_integration():
    """Generated search JS calls parseSearchQuery and applyFilters."""
    js = _generate_search_js()
    assert "runFilteredSearch" in js
    assert "parseSearchQuery" in js
    assert "applyFilters" in js


def test_search_filter_js_loaded_in_search_js():
    """search-filter.js is included before search-dialog.js in composed JS."""
    js = _generate_search_js()
    filter_pos = js.find("function parseSearchQuery")
    dialog_pos = js.find("search-dialog")
    assert filter_pos != -1, "parseSearchQuery not found in search JS"
    assert dialog_pos != -1, "search-dialog marker not found in search JS"
    assert filter_pos < dialog_pos, "filter JS must come before dialog JS"


def test_search_filter_js_default_version_injection():
    """Filter JS reads data-default-version for auto-injecting version filter."""
    js = _generate_search_js()
    assert "data-default-version" in js


def test_search_dialog_version_escapes_html():
    """Version string with special chars is HTML-escaped."""
    html = _render_search_dialog(asset_prefix="", current_version='1.0.0"<script>')
    assert '1.0.0"<script>' not in html
    assert "&quot;" in html or "&lt;" in html
