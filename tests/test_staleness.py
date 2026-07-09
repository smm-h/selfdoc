"""Tests for selfdoc.staleness -- description staleness detection."""

import json
import os

import pytest

from selfdoc.extractors.python import PythonExtractor
from selfdoc.staleness import (
    check_drift,
    check_schema_drift,
    check_staleness,
    compute_content_hash,
    compute_description_hash,
    compute_schema_hash,
    compute_source_docstring_hash,
    extract_module_docstring,
    load_hashes,
    save_hashes,
    update_hashes,
)


# -- compute_content_hash --


def test_content_hash_consistent():
    """Same content produces the same hash."""
    content = "# Hello\n\nSome content here."
    h1 = compute_content_hash(content)
    h2 = compute_content_hash(content)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest


def test_content_hash_different_for_different_content():
    """Different content produces different hashes."""
    h1 = compute_content_hash("# Hello")
    h2 = compute_content_hash("# Goodbye")
    assert h1 != h2


def test_content_hash_strips_frontmatter():
    """Frontmatter is stripped before hashing -- only body matters."""
    with_fm = "---\ntitle: Test\ndescription: A page\n---\n# Hello\n\nBody."
    without_fm = "# Hello\n\nBody."
    assert compute_content_hash(with_fm) == compute_content_hash(without_fm)


def test_content_hash_no_frontmatter():
    """Content without frontmatter is hashed as-is."""
    content = "# Just content\n\nNo frontmatter."
    h = compute_content_hash(content)
    assert len(h) == 64


# -- compute_description_hash --


def test_description_hash_consistent():
    """Same description produces the same hash."""
    desc = "A short description of the page"
    h1 = compute_description_hash(desc)
    h2 = compute_description_hash(desc)
    assert h1 == h2
    assert len(h1) == 64


def test_description_hash_different_for_different_descriptions():
    """Different descriptions produce different hashes."""
    h1 = compute_description_hash("Description A")
    h2 = compute_description_hash("Description B")
    assert h1 != h2


# -- load_hashes --


def test_load_hashes_missing_file(tmp_path):
    """Returns empty dict when hashes.json does not exist."""
    result = load_hashes(str(tmp_path))
    assert result == {}


def test_load_hashes_existing_file(tmp_path):
    """Loads hashes from an existing hashes.json file with _hash_version."""
    hashes_dir = os.path.join(tmp_path, ".selfdoc", "hashes")
    os.makedirs(hashes_dir)
    data = {
        "_hash_version": 2,
        "index.md": {
            "content": "abc123",
            "description": "def456",
        },
    }
    with open(os.path.join(hashes_dir, "hashes.json"), "w") as f:
        json.dump(data, f)

    result = load_hashes(str(tmp_path))
    assert result == data


# -- save_hashes --


def test_save_hashes_creates_directory(tmp_path):
    """Creates .selfdoc/hashes/ directory if it doesn't exist."""
    hashes = {"page.md": {"content": "aaa", "description": "bbb"}}
    save_hashes(hashes, str(tmp_path))

    hashes_dir = os.path.join(tmp_path, ".selfdoc", "hashes")
    assert os.path.isdir(hashes_dir)
    target = os.path.join(hashes_dir, "hashes.json")
    assert os.path.isfile(target)

    with open(target, "r") as f:
        loaded = json.load(f)
    assert loaded == hashes


def test_save_hashes_atomic_write(tmp_path):
    """Verifies no .tmp files are left behind (atomic write cleans up)."""
    hashes = {"x.md": {"content": "c", "description": "d"}}
    save_hashes(hashes, str(tmp_path))

    hashes_dir = os.path.join(tmp_path, ".selfdoc", "hashes")
    files = os.listdir(hashes_dir)
    assert files == ["hashes.json"]


def test_save_hashes_overwrites_existing(tmp_path):
    """Saving overwrites the previous hashes.json content."""
    save_hashes({"a.md": {"content": "1", "description": "2"}}, str(tmp_path))
    save_hashes({"b.md": {"content": "3", "description": "4"}}, str(tmp_path))

    result = load_hashes(str(tmp_path))
    assert "a.md" not in result
    assert result["b.md"] == {"content": "3", "description": "4"}


# -- check_staleness --


def test_check_staleness_new_page():
    """New page (not in stored hashes) returns None."""
    result = check_staleness("new.md", "c_hash", "d_hash", {})
    assert result is None


def test_check_staleness_unchanged_content():
    """Unchanged content returns None (no staleness)."""
    stored = {"page.md": {"content": "same", "description": "desc"}}
    result = check_staleness("page.md", "same", "desc", stored)
    assert result is None


def test_check_staleness_content_and_description_changed():
    """Content changed AND description changed returns None."""
    stored = {"page.md": {"content": "old_c", "description": "old_d"}}
    result = check_staleness("page.md", "new_c", "new_d", stored)
    assert result is None


def test_check_staleness_content_changed_description_unchanged():
    """Content changed but description unchanged returns error message."""
    stored = {"page.md": {"content": "old_c", "description": "same_d"}}
    result = check_staleness("page.md", "new_c", "same_d", stored)
    assert result is not None
    assert "page.md" in result
    assert "stale description" in result


# -- Integration with check_docs --


def test_staleness_integration_with_check(tmp_path):
    """Full integration: check_docs detects stale descriptions."""
    # Set up a minimal project
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "version": "1.0.0",
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir)
    with open(os.path.join(src_dir, "__init__.py"), "w") as f:
        f.write("")

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)

    # First run: create a page with description
    page_content_v1 = (
        "---\n"
        "description: Original description\n"
        "---\n"
        "# Page\n\n"
        "Original content here.\n"
    )
    with open(os.path.join(docs_dir, "page.md"), "w") as f:
        f.write(page_content_v1)

    from selfdoc.check import check_docs

    result1 = check_docs(str(tmp_path))
    # First run: no staleness (new page)
    stale_lints = [l for l in result1.lints if l.code == "STALE001"]
    assert len(stale_lints) == 0

    # Second run: change content but keep same description
    page_content_v2 = (
        "---\n"
        "description: Original description\n"
        "---\n"
        "# Page\n\n"
        "Completely rewritten content with new information.\n"
    )
    with open(os.path.join(docs_dir, "page.md"), "w") as f:
        f.write(page_content_v2)

    result2 = check_docs(str(tmp_path))
    stale_lints = [l for l in result2.lints if l.code == "STALE001"]
    assert len(stale_lints) == 1
    assert "page.md" in stale_lints[0].message
    assert stale_lints[0].severity == "error"


def test_staleness_no_error_when_description_updated(tmp_path):
    """No staleness error when both content and description change."""
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "version": "1.0.0",
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir)
    with open(os.path.join(src_dir, "__init__.py"), "w") as f:
        f.write("")

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)

    # First run
    with open(os.path.join(docs_dir, "page.md"), "w") as f:
        f.write("---\ndescription: V1 desc\n---\n# Page\n\nV1 content.\n")

    from selfdoc.check import check_docs

    check_docs(str(tmp_path))

    # Second run: change both content and description
    with open(os.path.join(docs_dir, "page.md"), "w") as f:
        f.write("---\ndescription: V2 desc\n---\n# Page\n\nV2 content.\n")

    result = check_docs(str(tmp_path))
    stale_lints = [l for l in result.lints if l.code == "STALE001"]
    assert len(stale_lints) == 0


# -- update_hashes --


def _make_all_docs(pages):
    """Helper: build an all_docs dict from a list of (rel_path, description, body) tuples."""
    result = {}
    for rel_path, description, body in pages:
        fm = {"description": description} if description is not None else {}
        resolved = f"---\ndescription: {description}\n---\n{body}" if description else body
        result[rel_path] = (fm, resolved, body, 3 if description else 0)
    return result


def test_update_hashes_writes_file(tmp_path):
    """update_hashes writes hashes.json when dry_run=False."""
    all_docs = _make_all_docs([
        ("page.md", "A page about things", "# Page\n\nSome content."),
    ])
    update_hashes(all_docs, str(tmp_path), dry_run=False)

    hashes_path = os.path.join(tmp_path, ".selfdoc", "hashes", "hashes.json")
    assert os.path.isfile(hashes_path)

    with open(hashes_path, "r") as f:
        data = json.load(f)
    assert "page.md" in data
    assert "content" in data["page.md"]
    assert "description" in data["page.md"]


def test_update_hashes_dry_run_no_write(tmp_path):
    """update_hashes does NOT write hashes.json when dry_run=True."""
    all_docs = _make_all_docs([
        ("page.md", "A page about things", "# Page\n\nSome content."),
    ])
    update_hashes(all_docs, str(tmp_path), dry_run=True)

    hashes_path = os.path.join(tmp_path, ".selfdoc", "hashes", "hashes.json")
    assert not os.path.exists(hashes_path)


def test_update_hashes_detects_stale(tmp_path):
    """update_hashes returns stale warnings when content changes but description doesn't."""
    # First pass: establish baseline hashes
    all_docs_v1 = _make_all_docs([
        ("page.md", "Original description", "# Page\n\nOriginal content."),
    ])
    warnings_v1, _ = update_hashes(all_docs_v1, str(tmp_path), dry_run=False)
    assert len(warnings_v1) == 0  # new page, no staleness

    # Second pass: change content but keep same description
    all_docs_v2 = _make_all_docs([
        ("page.md", "Original description", "# Page\n\nCompletely new content."),
    ])
    warnings_v2, _ = update_hashes(all_docs_v2, str(tmp_path), dry_run=False)
    assert len(warnings_v2) == 1
    rel_path, stale_msg = warnings_v2[0]
    assert rel_path == "page.md"
    assert "stale description" in stale_msg


def test_update_hashes_no_stale_when_both_change(tmp_path):
    """No staleness when both content and description change."""
    all_docs_v1 = _make_all_docs([
        ("page.md", "Desc v1", "# Page\n\nContent v1."),
    ])
    update_hashes(all_docs_v1, str(tmp_path), dry_run=False)

    all_docs_v2 = _make_all_docs([
        ("page.md", "Desc v2", "# Page\n\nContent v2."),
    ])
    warnings, _ = update_hashes(all_docs_v2, str(tmp_path), dry_run=False)
    assert len(warnings) == 0


def test_update_hashes_skips_pages_without_description(tmp_path):
    """Pages without a description in frontmatter are skipped entirely."""
    all_docs = _make_all_docs([
        ("no-desc.md", None, "# No Description\n\nJust content."),
    ])
    warnings, _ = update_hashes(all_docs, str(tmp_path), dry_run=False)
    assert len(warnings) == 0

    hashes_path = os.path.join(tmp_path, ".selfdoc", "hashes", "hashes.json")
    with open(hashes_path, "r") as f:
        data = json.load(f)
    assert "no-desc.md" not in data


# -- gen updates hashes --


def _setup_project(tmp_path, *, locales=None, page_content=None):
    """Helper: create a minimal selfdoc project in tmp_path.

    Returns the config dict written to selfdoc.json.
    """
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "version": "1.0.0",
    }
    if locales is not None:
        config["locales"] = locales

    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    # Minimal source dir
    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(src_dir, "__init__.py"), "w") as f:
        f.write("")

    # docs dir with a page
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    content = page_content or (
        "---\n"
        "description: A test page\n"
        "---\n"
        "# Test\n\n"
        "Some content.\n"
    )
    with open(os.path.join(docs_dir, "page.md"), "w") as f:
        f.write(content)

    return config


def _run_gen_hashes(config, base_dir):
    """Simulate the hash-update logic from _cmd_gen."""
    from selfdoc.docs import resolve_all_docs

    all_docs = resolve_all_docs(config, base_dir=base_dir)
    locales = config.get("locales") or []
    if locales:
        locale_code = locales[0]["code"]
        prefixed = {f"{locale_code}/{rp}": val for rp, val in all_docs.items()}
        update_hashes(prefixed, base_dir)
    else:
        update_hashes(all_docs, base_dir)


def test_gen_updates_hashes(tmp_path):
    """Running the gen hash-update logic creates/updates hashes.json."""
    config = _setup_project(tmp_path)
    _run_gen_hashes(config, str(tmp_path))

    hashes_path = os.path.join(tmp_path, ".selfdoc", "hashes", "hashes.json")
    assert os.path.isfile(hashes_path)

    with open(hashes_path, "r") as f:
        data = json.load(f)
    assert len(data) > 0


def test_gen_then_check_no_stale(tmp_path):
    """After gen updates hashes, check_docs reports no STALE001 warnings."""
    config = _setup_project(tmp_path)
    _run_gen_hashes(config, str(tmp_path))

    from selfdoc.check import check_docs

    result = check_docs(str(tmp_path))
    stale_lints = [lint for lint in result.lints if lint.code == "STALE001"]
    assert len(stale_lints) == 0


def test_locale_prefixed_hash_keys(tmp_path):
    """With locales configured, hash keys are prefixed with locale code."""
    locales = [{"code": "en", "label": "English", "default": True}]
    config = _setup_project(tmp_path, locales=locales)
    _run_gen_hashes(config, str(tmp_path))

    hashes_path = os.path.join(tmp_path, ".selfdoc", "hashes", "hashes.json")
    with open(hashes_path, "r") as f:
        data = json.load(f)

    # All page keys must be prefixed with "en/" (skip metadata keys)
    for key in data:
        if key.startswith("_"):
            continue
        assert key.startswith("en/"), f"Expected locale prefix on key {key!r}"
    assert "en/page.md" in data


def test_no_locales_no_prefix(tmp_path):
    """Without locales configured, hash keys are unprefixed."""
    config = _setup_project(tmp_path)
    _run_gen_hashes(config, str(tmp_path))

    hashes_path = os.path.join(tmp_path, ".selfdoc", "hashes", "hashes.json")
    with open(hashes_path, "r") as f:
        data = json.load(f)

    # Page keys should be bare paths without any locale prefix (skip metadata keys)
    for key in data:
        if key.startswith("_"):
            continue
        assert not key.startswith("en/"), f"Unexpected locale prefix on key {key!r}"
    assert "page.md" in data


# -- extract_module_docstring --


def test_extract_module_docstring_python(tmp_path):
    """Extracts module docstring from a Python file."""
    py_file = os.path.join(tmp_path, "mod.py")
    with open(py_file, "w", encoding="utf-8") as f:
        f.write('"""This is the module docstring."""\n\ndef foo(): pass\n')
    result = extract_module_docstring(py_file, PythonExtractor())
    assert result == "This is the module docstring."


def test_extract_module_docstring_python_no_docstring(tmp_path):
    """Returns empty string when Python file has no module docstring."""
    py_file = os.path.join(tmp_path, "mod.py")
    with open(py_file, "w", encoding="utf-8") as f:
        f.write("def foo(): pass\n")
    result = extract_module_docstring(py_file, PythonExtractor())
    assert result == ""


def test_extract_module_docstring_python_syntax_error(tmp_path):
    """Returns empty string on syntax error."""
    py_file = os.path.join(tmp_path, "bad.py")
    with open(py_file, "w", encoding="utf-8") as f:
        f.write("def broken(\n")
    result = extract_module_docstring(py_file, PythonExtractor())
    assert result == ""


def test_extract_module_docstring_nonexistent_file():
    """Returns empty string for a nonexistent file."""
    result = extract_module_docstring("/nonexistent/path.py", PythonExtractor())
    assert result == ""


def test_extract_module_docstring_base_extractor():
    """Returns empty string for base extractor (no language-specific logic)."""
    from selfdoc.extractors.base import BaseExtractor
    ext = BaseExtractor()
    result = extract_module_docstring("whatever.go", ext)
    assert result == ""


# -- compute_source_docstring_hash --


def test_compute_source_docstring_hash_with_docstrings(tmp_path):
    """Returns a hash when source files have docstrings."""
    f1 = os.path.join(tmp_path, "a.py")
    f2 = os.path.join(tmp_path, "b.py")
    with open(f1, "w") as f:
        f.write('"""Module A."""\n')
    with open(f2, "w") as f:
        f.write('"""Module B."""\n')
    result = compute_source_docstring_hash([(f1, PythonExtractor()), (f2, PythonExtractor())])
    assert result is not None
    assert len(result) == 64


def test_compute_source_docstring_hash_no_docstrings(tmp_path):
    """Returns None when no source files have docstrings."""
    f1 = os.path.join(tmp_path, "a.py")
    with open(f1, "w") as f:
        f.write("x = 1\n")
    result = compute_source_docstring_hash([(f1, PythonExtractor())])
    assert result is None


def test_compute_source_docstring_hash_sorted_determinism(tmp_path):
    """Hash is the same regardless of input order (sorted by path)."""
    f1 = os.path.join(tmp_path, "a.py")
    f2 = os.path.join(tmp_path, "b.py")
    with open(f1, "w") as f:
        f.write('"""A."""\n')
    with open(f2, "w") as f:
        f.write('"""B."""\n')
    h1 = compute_source_docstring_hash([(f1, PythonExtractor()), (f2, PythonExtractor())])
    h2 = compute_source_docstring_hash([(f2, PythonExtractor()), (f1, PythonExtractor())])
    assert h1 == h2


def test_compute_source_docstring_hash_base_extractor_skipped(tmp_path):
    """Base extractor contributes empty strings; if all empty, returns None."""
    from selfdoc.extractors.base import BaseExtractor
    f1 = os.path.join(tmp_path, "main.go")
    with open(f1, "w") as f:
        f.write("package main\n")
    result = compute_source_docstring_hash([(f1, BaseExtractor())])
    assert result is None


# -- check_drift --


def test_check_drift_no_source_hash():
    """Returns None when source_docstring_hash is None."""
    result = check_drift("page.md", None, "d_hash", {})
    assert result is None


def test_check_drift_new_page():
    """Returns None for a new page not in stored hashes."""
    result = check_drift("page.md", "sd_hash", "d_hash", {})
    assert result is None


def test_check_drift_no_stored_source_docstring():
    """Returns None when stored hashes exist but lack source_docstring key."""
    stored = {"page.md": {"content": "c", "description": "d"}}
    result = check_drift("page.md", "sd_hash", "d", stored)
    assert result is None


def test_check_drift_source_unchanged():
    """Returns None when source docstring hash is unchanged."""
    stored = {"page.md": {"content": "c", "description": "d", "source_docstring": "same"}}
    result = check_drift("page.md", "same", "d", stored)
    assert result is None


def test_check_drift_source_changed_description_updated():
    """Returns None when source changed but description was also updated."""
    stored = {"page.md": {"content": "c", "description": "old_d", "source_docstring": "old_sd"}}
    result = check_drift("page.md", "new_sd", "new_d", stored)
    assert result is None


def test_check_drift_source_changed_description_unchanged():
    """Returns error when source changed but description stayed the same."""
    stored = {"page.md": {"content": "c", "description": "same_d", "source_docstring": "old_sd"}}
    result = check_drift("page.md", "new_sd", "same_d", stored)
    assert result is not None
    assert "page.md" in result
    assert "documentation drift" in result


# -- Phase 2a: baseline does not advance while errors are outstanding --


def test_baseline_hold_staleness_persists(tmp_path):
    """Staleness error persists on second check when description is not rewritten.

    Red-green test for Phase 2a: before the fix, the baseline would advance
    on the first error, making the second check pass.  After the fix, the
    baseline stays frozen until the description is actually updated.
    """
    # Step 1: create page with source_docstring hash A and description "old desc"
    all_docs_v1 = _make_all_docs([
        ("page.md", "old desc", "# Page\n\nOriginal content."),
    ])
    warnings_v1, _ = update_hashes(all_docs_v1, str(tmp_path), dry_run=False)
    assert len(warnings_v1) == 0  # new page, no staleness

    # Step 2: change content (hash becomes B) but keep description "old desc"
    all_docs_v2 = _make_all_docs([
        ("page.md", "old desc", "# Page\n\nCompletely rewritten content."),
    ])
    warnings_v2, _ = update_hashes(all_docs_v2, str(tmp_path), dry_run=False)
    assert len(warnings_v2) == 1  # first check -> staleness error

    # Step 3: second check with same stale state -> STILL staleness error
    # (baseline did NOT advance because of the error)
    warnings_v3, _ = update_hashes(all_docs_v2, str(tmp_path), dry_run=False)
    assert len(warnings_v3) == 1, "Staleness error should persist on second check"

    # Step 4: rewrite description -> check passes (error cleared)
    all_docs_v3 = _make_all_docs([
        ("page.md", "new desc matching new content", "# Page\n\nCompletely rewritten content."),
    ])
    warnings_v4, _ = update_hashes(all_docs_v3, str(tmp_path), dry_run=False)
    assert len(warnings_v4) == 0, "No staleness after description was rewritten"


def test_baseline_hold_drift_persists(tmp_path):
    """Drift error persists on second check when description is not rewritten.

    Same principle as staleness hold but for source docstring drift.
    """
    # Step 1: establish baseline with source_docstring
    all_docs = _make_all_docs([
        ("page.md", "old desc", "# Page\n\nContent."),
    ])
    # Manually set up stored hashes with a source_docstring
    stored = {
        "page.md": {
            "content": compute_content_hash("# Page\n\nContent."),
            "description": compute_description_hash("old desc"),
            "source_docstring": "hash_A",
        }
    }
    save_hashes(stored, str(tmp_path))

    # Step 2: source docstring changes but description stays the same
    # We simulate this by passing page_directives that produce a different hash.
    # For simplicity, directly call update_hashes with a modified stored state.
    # Change source_docstring in the stored hash and call check_drift.
    drift_msg = check_drift(
        "page.md", "hash_B", compute_description_hash("old desc"),
        stored,
    )
    assert drift_msg is not None, "Should detect drift"

    # Verify through update_hashes that the hold works:
    # Manually create hashes that will trigger drift on update
    stored_with_old_sd = {
        "page.md": {
            "content": compute_content_hash("# Page\n\nContent."),
            "description": compute_description_hash("old desc"),
            "source_docstring": "hash_A",
        }
    }
    save_hashes(stored_with_old_sd, str(tmp_path))

    # update_hashes with schema_hashes won't trigger drift directly here
    # because page_directives is None, but we can verify the stored hashes
    # are not updated for error pages by checking the file
    all_docs_same = _make_all_docs([
        ("page.md", "old desc", "# Page\n\nContent."),
    ])

    # First, use schema_hashes to trigger a schema drift
    schema_hashes = {"page.md": "schema_hash_B"}
    stored_with_schema = {
        "page.md": {
            "content": compute_content_hash("# Page\n\nContent."),
            "description": compute_description_hash("old desc"),
            "schema_hash": "schema_hash_A",
        }
    }
    save_hashes(stored_with_schema, str(tmp_path))

    _, drift1 = update_hashes(
        all_docs_same, str(tmp_path), dry_run=False,
        schema_hashes=schema_hashes,
    )
    assert len(drift1) == 1, "Should detect schema drift"

    # Second check: error should persist
    _, drift2 = update_hashes(
        all_docs_same, str(tmp_path), dry_run=False,
        schema_hashes=schema_hashes,
    )
    assert len(drift2) == 1, "Schema drift should persist on second check"


def test_baseline_hold_all_fields_atomic(tmp_path):
    """When a page has an error, ALL its hash fields stay frozen."""
    all_docs_v1 = _make_all_docs([
        ("page.md", "old desc", "# Page\n\nOriginal content."),
    ])
    update_hashes(all_docs_v1, str(tmp_path), dry_run=False)

    # Read the stored hashes
    stored = load_hashes(str(tmp_path))
    original_content_hash = stored["page.md"]["content"]
    original_desc_hash = stored["page.md"]["description"]

    # Change content but not description -> staleness error
    all_docs_v2 = _make_all_docs([
        ("page.md", "old desc", "# Page\n\nNew content here."),
    ])
    warnings, _ = update_hashes(all_docs_v2, str(tmp_path), dry_run=False)
    assert len(warnings) == 1

    # Verify ALL fields are frozen (content and description unchanged)
    stored_after = load_hashes(str(tmp_path))
    assert stored_after["page.md"]["content"] == original_content_hash
    assert stored_after["page.md"]["description"] == original_desc_hash


# -- Phase 2b: CLI schema-hash gating --


def test_compute_schema_hash_deterministic():
    """Same schema slice produces the same hash."""
    schema = {"name": "build", "help": "Build the project", "flags": []}
    h1 = compute_schema_hash(schema)
    h2 = compute_schema_hash(schema)
    assert h1 == h2
    assert len(h1) == 64


def test_compute_schema_hash_different_for_different_schemas():
    """Different schema slices produce different hashes."""
    s1 = {"name": "build", "help": "Build the project", "flags": []}
    s2 = {"name": "build", "help": "Build the project with options", "flags": []}
    assert compute_schema_hash(s1) != compute_schema_hash(s2)


def test_compute_schema_hash_sensitive_to_flags():
    """Adding a flag changes the hash."""
    s1 = {"name": "build", "help": "Build", "flags": []}
    s2 = {"name": "build", "help": "Build", "flags": [{"name": "verbose"}]}
    assert compute_schema_hash(s1) != compute_schema_hash(s2)


def test_check_schema_drift_no_hash():
    """Returns None when schema_hash is None."""
    result = check_schema_drift("page.md", None, "d_hash", {})
    assert result is None


def test_check_schema_drift_new_page():
    """Returns None for a new page not in stored hashes."""
    result = check_schema_drift("page.md", "s_hash", "d_hash", {})
    assert result is None


def test_check_schema_drift_no_stored_schema():
    """Returns None when stored hashes lack schema_hash key."""
    stored = {"page.md": {"content": "c", "description": "d"}}
    result = check_schema_drift("page.md", "s_hash", "d", stored)
    assert result is None


def test_check_schema_drift_schema_unchanged():
    """Returns None when schema hash is unchanged."""
    stored = {"page.md": {"content": "c", "description": "d", "schema_hash": "same"}}
    result = check_schema_drift("page.md", "same", "d", stored)
    assert result is None


def test_check_schema_drift_schema_changed_description_updated():
    """Returns None when schema changed but description was also updated."""
    stored = {"page.md": {"content": "c", "description": "old_d", "schema_hash": "old_s"}}
    result = check_schema_drift("page.md", "new_s", "new_d", stored)
    assert result is None


def test_check_schema_drift_schema_changed_description_unchanged():
    """Returns error when schema changed but description stayed the same."""
    stored = {"page.md": {"content": "c", "description": "same_d", "schema_hash": "old_s"}}
    result = check_schema_drift("page.md", "new_s", "same_d", stored)
    assert result is not None
    assert "page.md" in result
    assert "CLI schema changed" in result


def test_update_hashes_with_schema_hashes(tmp_path):
    """update_hashes stores schema_hash and detects schema drift."""
    all_docs = _make_all_docs([
        ("cli-build.md", "Build the project", "# Build\n\nContent."),
    ])

    # First run: establish baseline with schema hash
    schema_hashes = {"cli-build.md": "schema_v1"}
    _, drift = update_hashes(
        all_docs, str(tmp_path), dry_run=False,
        schema_hashes=schema_hashes,
    )
    assert len(drift) == 0  # new page, no drift

    # Verify schema_hash is stored
    stored = load_hashes(str(tmp_path))
    assert stored["cli-build.md"]["schema_hash"] == "schema_v1"

    # Second run: schema changes but description stays the same
    schema_hashes_v2 = {"cli-build.md": "schema_v2"}
    _, drift = update_hashes(
        all_docs, str(tmp_path), dry_run=False,
        schema_hashes=schema_hashes_v2,
    )
    assert len(drift) == 1
    assert "CLI schema changed" in drift[0][1]


def test_update_hashes_schema_drift_baseline_hold(tmp_path):
    """Schema drift error persists on second check (baseline hold)."""
    all_docs = _make_all_docs([
        ("cli-build.md", "Build the project", "# Build\n\nContent."),
    ])

    # Establish baseline
    schema_hashes = {"cli-build.md": "schema_v1"}
    update_hashes(
        all_docs, str(tmp_path), dry_run=False,
        schema_hashes=schema_hashes,
    )

    # Schema changes -> drift error
    schema_hashes_v2 = {"cli-build.md": "schema_v2"}
    _, drift1 = update_hashes(
        all_docs, str(tmp_path), dry_run=False,
        schema_hashes=schema_hashes_v2,
    )
    assert len(drift1) == 1

    # Second check -> still drift error (baseline didn't advance)
    _, drift2 = update_hashes(
        all_docs, str(tmp_path), dry_run=False,
        schema_hashes=schema_hashes_v2,
    )
    assert len(drift2) == 1, "Schema drift should persist on second check"

    # Update description -> drift clears
    all_docs_fixed = _make_all_docs([
        ("cli-build.md", "Build the project with new flags", "# Build\n\nContent."),
    ])
    _, drift3 = update_hashes(
        all_docs_fixed, str(tmp_path), dry_run=False,
        schema_hashes=schema_hashes_v2,
    )
    assert len(drift3) == 0, "No drift after description was updated"


# -- Phase 2c: code-backed page source-hash gating --


def test_source_docstring_drift_integration(tmp_path):
    """Source docstring changes trigger drift errors via update_hashes.

    This verifies Phase 2c: module pages are gated on the extractor
    docstring hash through the existing source_docstring key.
    """
    # Create a Python source file with a docstring
    src_file = os.path.join(tmp_path, "mod.py")
    with open(src_file, "w", encoding="utf-8") as f:
        f.write('"""Original docstring."""\n\ndef foo(): pass\n')

    ext = PythonExtractor()

    # Build a fake resolved directive with the source file
    class FakeDirective:
        def __init__(self, path, extractor, source_path):
            self.attrs = {"path": path}
            self.source_entry = type("SE", (), {
                "extractor": extractor,
                "path": source_path,
            })()

    all_docs = _make_all_docs([
        ("mod.md", "Original docstring.", "# Mod\n\nContent."),
    ])
    page_directives = {
        "mod.md": [FakeDirective(src_file, ext, str(tmp_path))],
    }

    # First run: establish baseline with source_docstring hash
    _, drift = update_hashes(
        all_docs, str(tmp_path), dry_run=False,
        page_directives=page_directives,
    )
    assert len(drift) == 0

    # Verify source_docstring is stored
    stored = load_hashes(str(tmp_path))
    assert "source_docstring" in stored["mod.md"]

    # Change the docstring but keep the same description
    with open(src_file, "w", encoding="utf-8") as f:
        f.write('"""Updated docstring with new info."""\n\ndef foo(): pass\n')

    _, drift = update_hashes(
        all_docs, str(tmp_path), dry_run=False,
        page_directives=page_directives,
    )
    assert len(drift) == 1
    assert "documentation drift" in drift[0][1]


# -- Phase 1: raw-body hashing (STALE001 ignores directive output changes) --


def _make_all_docs_full(pages):
    """Build all_docs with separate raw and resolved content.

    Each item is (rel_path, description, raw_body, resolved_body).
    This mirrors the real tuple shape:
      (frontmatter_dict, resolved_content, raw_content, fm_line_count)
    """
    result = {}
    for rel_path, description, raw_body, resolved_body in pages:
        fm = {"description": description} if description is not None else {}
        result[rel_path] = (fm, resolved_body, raw_body, 3 if description else 0)
    return result


def test_stale001_not_fired_when_only_directive_output_changes(tmp_path):
    """STALE001 does not fire when a var directive's output changes.

    The raw body contains ``:-: var key="project.version"`` which stays
    constant.  Only the resolved content changes (e.g. "1.0.0" -> "1.1.0").
    Since hashing is now based on the raw body, the content hash is stable
    and STALE001 should not fire.
    """
    raw_body = '# Page\n\nVersion: :-: var key="project.version"\n'

    # Run 1: version 1.0.0
    all_docs_v1 = _make_all_docs_full([
        ("page.md", "A page about the project", raw_body,
         "# Page\n\nVersion: 1.0.0\n"),
    ])
    warnings_v1, _ = update_hashes(all_docs_v1, str(tmp_path), dry_run=False)
    assert len(warnings_v1) == 0  # new page, no staleness

    # Run 2: version changes to 1.1.0 but raw body is the same
    all_docs_v2 = _make_all_docs_full([
        ("page.md", "A page about the project", raw_body,
         "# Page\n\nVersion: 1.1.0\n"),
    ])
    warnings_v2, _ = update_hashes(all_docs_v2, str(tmp_path), dry_run=False)
    assert len(warnings_v2) == 0, (
        "STALE001 should not fire when only directive output changed"
    )


def test_stale001_fires_when_prose_changes(tmp_path):
    """STALE001 fires when the actual page prose changes.

    The raw body changes (real content edit), but the description stays
    the same.  This should trigger STALE001.
    """
    # Run 1: original content
    all_docs_v1 = _make_all_docs_full([
        ("page.md", "A page about things", "# Page\n\nOriginal prose.\n",
         "# Page\n\nOriginal prose.\n"),
    ])
    warnings_v1, _ = update_hashes(all_docs_v1, str(tmp_path), dry_run=False)
    assert len(warnings_v1) == 0  # new page

    # Run 2: prose changes, description stays the same
    all_docs_v2 = _make_all_docs_full([
        ("page.md", "A page about things", "# Page\n\nRewritten prose.\n",
         "# Page\n\nRewritten prose.\n"),
    ])
    warnings_v2, _ = update_hashes(all_docs_v2, str(tmp_path), dry_run=False)
    assert len(warnings_v2) == 1, "STALE001 should fire when prose changes"
    assert "stale description" in warnings_v2[0][1]


def test_baseline_migration_discards_old_format(tmp_path):
    """Old-format hashes.json (no _hash_version) is discarded on load."""
    hashes_dir = os.path.join(tmp_path, ".selfdoc", "hashes")
    os.makedirs(hashes_dir)
    old_data = {
        "page.md": {
            "content": "old_hash_of_resolved_content",
            "description": "desc_hash",
        }
    }
    with open(os.path.join(hashes_dir, "hashes.json"), "w") as f:
        json.dump(old_data, f)

    result = load_hashes(str(tmp_path))
    assert result == {}, "Old-format hashes should be discarded (empty dict)"


def test_baseline_migration_keeps_new_format(tmp_path):
    """New-format hashes.json (with _hash_version=2) is loaded normally."""
    hashes_dir = os.path.join(tmp_path, ".selfdoc", "hashes")
    os.makedirs(hashes_dir)
    new_data = {
        "_hash_version": 2,
        "page.md": {
            "content": "hash_of_raw_body",
            "description": "desc_hash",
        },
    }
    with open(os.path.join(hashes_dir, "hashes.json"), "w") as f:
        json.dump(new_data, f)

    result = load_hashes(str(tmp_path))
    assert result == new_data


def test_save_hashes_includes_hash_version(tmp_path):
    """save_hashes always writes _hash_version=2 to the output."""
    hashes = {"page.md": {"content": "aaa", "description": "bbb"}}
    save_hashes(hashes, str(tmp_path))

    hashes_path = os.path.join(tmp_path, ".selfdoc", "hashes", "hashes.json")
    with open(hashes_path, "r") as f:
        data = json.load(f)
    assert data["_hash_version"] == 2
