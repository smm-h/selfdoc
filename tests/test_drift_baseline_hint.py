"""Tests for the DRIFT001 baseline-accept remediation hint.

A drift error tells the operator that source docstrings (or a CLI schema
slice) moved while the page description did not -- but it never said what
to do when the description is genuinely still accurate. Without a stated
escape hatch the only discoverable way out is to invent a description
edit. Every DRIFT001 message now names ``selfdoc baseline accept``.
"""

import json

from selfdoc_core.staleness import check_drift, check_schema_drift


class TestDriftMessageHint:
    def test_source_drift_message_carries_hint(self):
        stored = {"page.md": {"source_docstring": "old", "description": "d"}}
        msg = check_drift("page.md", "new", "d", stored)
        assert msg is not None
        assert (
            "after reviewing the page against the changed docstrings, run "
            "`selfdoc baseline accept page.md`"
        ) in msg
        assert "new baseline" in msg

    def test_schema_drift_message_carries_hint(self):
        stored = {"cli-run.md": {"schema_hash": "old", "description": "d"}}
        msg = check_schema_drift("cli-run.md", "new", "d", stored)
        assert msg is not None
        assert (
            "after reviewing the page against the changed CLI schema, run "
            "`selfdoc baseline accept cli-run.md`"
        ) in msg

    def test_original_diagnosis_is_preserved(self):
        stored = {"page.md": {"source_docstring": "old", "description": "d"}}
        msg = check_drift("page.md", "new", "d", stored)
        assert "possible documentation drift" in msg

    def test_no_hint_when_there_is_no_drift(self):
        stored = {"page.md": {"source_docstring": "same", "description": "d"}}
        assert check_drift("page.md", "same", "d", stored) is None


def test_emitted_drift001_lint_carries_the_hint(tmp_path):
    """The hint must survive all the way to the DRIFT001 lint the user sees."""
    from selfdoc.check import check_docs

    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "docs").mkdir(parents=True)
    (proj / "pyproject.toml").write_text(
        '[project]\nname = "mylib"\nversion = "1.0.0"\n', encoding="utf-8",
    )
    (proj / "src" / "__init__.py").write_text(
        '"""Original module docstring."""\n', encoding="utf-8",
    )
    (proj / "selfdoc.json").write_text(json.dumps({
        "source": [{"path": "src/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "versions": [{"version": "1.0.0", "indexed": True}],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }), encoding="utf-8")
    (proj / "docs" / "index.md").write_text(
        '---\ndescription: "A handwritten description of the module."\n---\n'
        '# Index\n\n:-: ref path="src" lang="python"\n',
        encoding="utf-8",
    )

    # First pass records the baseline.
    check_docs(str(proj))

    # Change the source docstring only -- the description stays put.
    (proj / "src" / "__init__.py").write_text(
        '"""A completely different module docstring."""\n', encoding="utf-8",
    )

    result = check_docs(str(proj))
    drift = [lint for lint in result.lints if lint.code == "DRIFT001"]
    assert drift, "expected a DRIFT001 lint"
    for lint in drift:
        assert "after reviewing the page against the changed" in lint.message
        assert f"`selfdoc baseline accept {lint.file}`" in lint.message
