"""Tests for selfdoc.staleness -- description staleness detection."""

import json
import os

import pytest

from selfdoc.staleness import (
    check_staleness,
    compute_content_hash,
    compute_description_hash,
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
    """Loads hashes from an existing hashes.json file."""
    hashes_dir = os.path.join(tmp_path, ".selfdoc", "hashes")
    os.makedirs(hashes_dir)
    data = {
        "index.md": {
            "content": "abc123",
            "description": "def456",
        }
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
    warnings_v1 = update_hashes(all_docs_v1, str(tmp_path), dry_run=False)
    assert len(warnings_v1) == 0  # new page, no staleness

    # Second pass: change content but keep same description
    all_docs_v2 = _make_all_docs([
        ("page.md", "Original description", "# Page\n\nCompletely new content."),
    ])
    warnings_v2 = update_hashes(all_docs_v2, str(tmp_path), dry_run=False)
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
    warnings = update_hashes(all_docs_v2, str(tmp_path), dry_run=False)
    assert len(warnings) == 0


def test_update_hashes_skips_pages_without_description(tmp_path):
    """Pages without a description in frontmatter are skipped entirely."""
    all_docs = _make_all_docs([
        ("no-desc.md", None, "# No Description\n\nJust content."),
    ])
    warnings = update_hashes(all_docs, str(tmp_path), dry_run=False)
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

    # All keys must be prefixed with "en/"
    for key in data:
        assert key.startswith("en/"), f"Expected locale prefix on key {key!r}"
    assert "en/page.md" in data


def test_no_locales_no_prefix(tmp_path):
    """Without locales configured, hash keys are unprefixed."""
    config = _setup_project(tmp_path)
    _run_gen_hashes(config, str(tmp_path))

    hashes_path = os.path.join(tmp_path, ".selfdoc", "hashes", "hashes.json")
    with open(hashes_path, "r") as f:
        data = json.load(f)

    # Keys should be bare paths without any "/" prefix
    for key in data:
        assert not key.startswith("en/"), f"Unexpected locale prefix on key {key!r}"
    assert "page.md" in data
