"""Tests for 'selfdoc baseline accept' -- the STALE001/DRIFT001 escape hatch.

STALE001 fires when a page's resolved content changed versus its stored
baseline but its frontmatter description did not.  The baseline is
deliberately frozen while a page is in an error state, so re-running
gen/check can never clear the error on its own -- the only prior escape
was editing the description.  ``selfdoc baseline accept <page>`` is the
deliberate, auditable human action that clears such a dead-end when the
existing description was reviewed and is still accurate.
"""

import json
import os

import pytest

from selfdoc.check import AcceptError, accept_baselines, check_docs


def _setup_project(tmp_path, *, locales=None):
    """Create a minimal selfdoc project with one page and return its config."""
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "search_engine": "pagefind",
        "version": "1.0.0",
    }
    if locales is not None:
        config["locales"] = locales

    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(src_dir, "__init__.py"), "w") as f:
        f.write("")

    os.makedirs(os.path.join(tmp_path, "docs"), exist_ok=True)
    return config


def _write_page(tmp_path, description, body, name="page.md"):
    content = f"---\ndescription: {description}\n---\n# Page\n\n{body}\n"
    with open(os.path.join(tmp_path, "docs", name), "w") as f:
        f.write(content)


def _stale_codes(result):
    return [lint for lint in result.lints if lint.code == "STALE001"]


# -- Reproduction: the sticky-freeze dead-end --


def test_stale_freeze_deadend_is_sticky(tmp_path):
    """Reproduce the dead-end: STALE001 persists across gen/check runs.

    Proves current behavior -- content changed but description unchanged
    triggers STALE001, and the frozen baseline means a subsequent check
    (which is what `gen` does too, via update_hashes) STILL reports the
    error.  Only rewriting the description would clear it.  This is the
    dead-end that `baseline accept` exists to break.
    """
    _setup_project(tmp_path)

    # First check: establish the baseline (new page -> no staleness).
    _write_page(tmp_path, "Original description", "Original content here.")
    result1 = check_docs(str(tmp_path))
    assert len(_stale_codes(result1)) == 0

    # Change content, keep the same description -> STALE001.
    _write_page(tmp_path, "Original description", "Completely rewritten content.")
    result2 = check_docs(str(tmp_path))
    assert len(_stale_codes(result2)) == 1

    # Run check again (same as re-running gen): the baseline stayed frozen,
    # so the error is STILL present -- the sticky dead-end.
    result3 = check_docs(str(tmp_path))
    assert len(_stale_codes(result3)) == 1, "STALE001 must persist (frozen baseline)"


# -- accept clears the dead-end --


def test_accept_clears_stale_and_check_passes(tmp_path):
    """After accept, the page's STALE001 is gone and check passes for it."""
    _setup_project(tmp_path)
    _write_page(tmp_path, "Original description", "Original content here.")
    check_docs(str(tmp_path))
    _write_page(tmp_path, "Original description", "Completely rewritten content.")
    assert len(_stale_codes(check_docs(str(tmp_path)))) == 1

    accepted = accept_baselines(["page.md"], dir_path=str(tmp_path))
    assert accepted == [("page.md", "STALE001")]

    result = check_docs(str(tmp_path))
    assert len(_stale_codes(result)) == 0, "STALE001 cleared after accept"


def test_accept_advances_baseline_to_current_hashes(tmp_path):
    """Accept records the current content + description hashes as baseline."""
    from selfdoc.staleness import (
        compute_content_hash,
        compute_description_hash,
        load_hashes,
    )

    _setup_project(tmp_path)
    _write_page(tmp_path, "Original description", "Original content here.")
    check_docs(str(tmp_path))
    _write_page(tmp_path, "Original description", "Brand new body text.")
    check_docs(str(tmp_path))

    accept_baselines(["page.md"], dir_path=str(tmp_path))

    stored = load_hashes(str(tmp_path))
    expected_content = compute_content_hash("# Page\n\nBrand new body text.\n")
    expected_desc = compute_description_hash("Original description")
    assert stored["page.md"]["content"] == expected_content
    assert stored["page.md"]["description"] == expected_desc


# -- hard errors --


def test_accept_non_stale_page_hard_errors(tmp_path):
    """Accepting a page that is not stale is a hard error, not a no-op."""
    _setup_project(tmp_path)
    _write_page(tmp_path, "Original description", "Original content here.")
    check_docs(str(tmp_path))  # baseline established, page is fresh

    with pytest.raises(AcceptError) as exc:
        accept_baselines(["page.md"], dir_path=str(tmp_path))
    assert "nothing to accept" in str(exc.value)


def test_accept_unknown_page_hard_errors(tmp_path):
    """Accepting a page that does not exist is a hard error."""
    _setup_project(tmp_path)
    _write_page(tmp_path, "Original description", "Original content here.")
    check_docs(str(tmp_path))

    with pytest.raises(AcceptError) as exc:
        accept_baselines(["does-not-exist.md"], dir_path=str(tmp_path))
    assert "not a documentation page" in str(exc.value)


def test_accept_page_without_baseline_hard_errors(tmp_path):
    """Accepting a page that has no baseline entry yet is a hard error."""
    _setup_project(tmp_path)
    _write_page(tmp_path, "Original description", "Original content here.")
    # Deliberately do NOT run check first -- no baseline recorded.
    with pytest.raises(AcceptError):
        accept_baselines(["page.md"], dir_path=str(tmp_path))


def test_accept_is_all_or_nothing(tmp_path):
    """When one named page is invalid, nothing is written for the valid one."""
    from selfdoc.staleness import load_hashes

    _setup_project(tmp_path)
    _write_page(tmp_path, "Original description", "Original content here.")
    check_docs(str(tmp_path))
    _write_page(tmp_path, "Original description", "Rewritten content.")
    check_docs(str(tmp_path))
    before = load_hashes(str(tmp_path))["page.md"]["content"]

    with pytest.raises(AcceptError):
        accept_baselines(["page.md", "bogus.md"], dir_path=str(tmp_path))

    # The stale page's baseline was NOT advanced.
    after = load_hashes(str(tmp_path))["page.md"]["content"]
    assert after == before


# -- multiple pages --


def test_accept_multiple_pages_in_one_call(tmp_path):
    """A single accept call can clear several stale pages at once."""
    _setup_project(tmp_path)
    _write_page(tmp_path, "Desc A original", "Body A original.", name="a.md")
    _write_page(tmp_path, "Desc B original", "Body B original.", name="b.md")
    check_docs(str(tmp_path))

    _write_page(tmp_path, "Desc A original", "Body A rewritten.", name="a.md")
    _write_page(tmp_path, "Desc B original", "Body B rewritten.", name="b.md")
    assert len(_stale_codes(check_docs(str(tmp_path)))) == 2

    accepted = accept_baselines(["a.md", "b.md"], dir_path=str(tmp_path))
    assert {p for p, _ in accepted} == {"a.md", "b.md"}

    assert len(_stale_codes(check_docs(str(tmp_path)))) == 0


# -- locale-prefixed identifiers (the real-world shape) --


def test_accept_locale_prefixed_identifier(tmp_path):
    """Pages are named with the locale prefix exactly as check reports them."""
    locales = [{"code": "en", "label": "English", "default": True}]
    _setup_project(tmp_path, locales=locales)
    _write_page(tmp_path, "Original description", "Original content here.")
    check_docs(str(tmp_path))
    _write_page(tmp_path, "Original description", "Rewritten content.")

    result = check_docs(str(tmp_path))
    stale = _stale_codes(result)
    assert len(stale) == 1
    # The check reports the locale-prefixed identifier.
    assert stale[0].file == "en/page.md"

    # Bare identifier is rejected; the locale-prefixed one is accepted.
    with pytest.raises(AcceptError):
        accept_baselines(["page.md"], dir_path=str(tmp_path))

    accepted = accept_baselines(["en/page.md"], dir_path=str(tmp_path))
    assert accepted == [("en/page.md", "STALE001")]
    assert len(_stale_codes(check_docs(str(tmp_path)))) == 0


# -- CLI command wiring --


def test_cli_baseline_accept_command(tmp_path, monkeypatch, capsys):
    """The CLI command accepts a page and reports what it cleared."""
    from selfdoc.cli import _cmd_baseline_accept

    _setup_project(tmp_path)
    _write_page(tmp_path, "Original description", "Original content here.")
    monkeypatch.chdir(tmp_path)
    check_docs(str(tmp_path))
    _write_page(tmp_path, "Original description", "Rewritten content.")
    check_docs(str(tmp_path))

    rc = _cmd_baseline_accept(None, ["page.md"], auto_commit=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "page.md" in out
    assert "STALE001" in out

    assert len(_stale_codes(check_docs(str(tmp_path)))) == 0


def test_cli_baseline_accept_unknown_page_exits(tmp_path, monkeypatch):
    """The CLI command exits non-zero on an unknown page."""
    from selfdoc.cli import _cmd_baseline_accept

    _setup_project(tmp_path)
    _write_page(tmp_path, "Original description", "Original content here.")
    monkeypatch.chdir(tmp_path)
    check_docs(str(tmp_path))

    with pytest.raises(SystemExit) as exc:
        _cmd_baseline_accept(None, ["nope.md"], auto_commit=False)
    assert exc.value.code == 1
