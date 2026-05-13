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
        "language": "python",
        "source": ["src/"],
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
        "language": "python",
        "source": ["src/"],
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
