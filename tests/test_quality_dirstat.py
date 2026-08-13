"""selfdoc quality's dirstat consumption: loud on every failure.

Source LOC has no in-tree fallback -- it comes from the external ``dirstat``
binary and nothing else. A swallowed failure therefore does not degrade the
report, it falsifies it: every project silently scores 0 source LOC, which
makes every doc-to-source ratio infinite and every content grade an A. These
tests pin the opposite behaviour: a dirstat that fails, times out, or answers
in a shape this module does not understand is a hard error naming the cause.
"""

import json
import subprocess

import pytest

from selfdoc.quality import DirstatError, get_code_loc


class _FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _envelope(payload):
    return json.dumps({
        "interface_version": 1,
        "app": "dirstat",
        "app_version": "0.3.0",
        "command": "scan",
        "exit_code": 0,
        "payload": payload,
        "dry_run": False,
        "preview": [],
        "preview_error": None,
        "diagnostics": [],
    })


def _patch_run(monkeypatch, result):
    """Replace the effects.run seam with a canned answer or an exception."""
    def fake_run(argv, **kwargs):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr("selfdoc.quality.effects.run", fake_run)


def test_reads_the_payload_of_the_envelope(monkeypatch, tmp_path):
    """The scan document is the envelope's payload member."""
    _patch_run(monkeypatch, _FakeCompleted(stdout=_envelope({
        "root": str(tmp_path),
        "method": "hybrid",
        "summary": {},
        "groups": [
            {"format": "py", "text": True, "count": 3, "total_loc": 120},
            {"format": "md", "text": True, "count": 1, "total_loc": 900},
        ],
    })))
    assert get_code_loc(tmp_path) == (120, 3)


def test_a_nonzero_exit_is_a_hard_error(monkeypatch, tmp_path):
    _patch_run(monkeypatch, _FakeCompleted(
        stdout="", stderr="error: unknown flag --output\n", returncode=2,
    ))
    with pytest.raises(DirstatError) as exc:
        get_code_loc(tmp_path)
    assert "exited 2" in str(exc.value)
    assert "unknown flag" in str(exc.value)


def test_unparseable_output_is_a_hard_error(monkeypatch, tmp_path):
    _patch_run(monkeypatch, _FakeCompleted(stdout="not json at all\n"))
    with pytest.raises(DirstatError) as exc:
        get_code_loc(tmp_path)
    assert "not valid JSON" in str(exc.value)


def test_an_envelope_without_a_payload_is_a_hard_error(monkeypatch, tmp_path):
    _patch_run(monkeypatch, _FakeCompleted(stdout=_envelope(None)))
    with pytest.raises(DirstatError) as exc:
        get_code_loc(tmp_path)
    assert "payload" in str(exc.value)


def test_a_payload_without_groups_is_a_hard_error(monkeypatch, tmp_path):
    _patch_run(monkeypatch, _FakeCompleted(stdout=_envelope({"root": "/x"})))
    with pytest.raises(DirstatError) as exc:
        get_code_loc(tmp_path)
    assert "groups" in str(exc.value)


def test_a_timeout_is_a_hard_error(monkeypatch, tmp_path):
    _patch_run(monkeypatch, subprocess.TimeoutExpired(cmd=["dirstat"], timeout=60))
    with pytest.raises(DirstatError) as exc:
        get_code_loc(tmp_path)
    assert "timed out" in str(exc.value)


def test_a_failing_submodule_subtraction_is_a_hard_error(monkeypatch, tmp_path):
    """The inner scan is not a lesser scan: a broken one falsifies the total."""
    sub = tmp_path / "vendor"
    sub.mkdir()

    calls = {"n": 0}

    def fake_run(argv, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeCompleted(stdout=_envelope({
                "groups": [{"format": "py", "text": True, "count": 2, "total_loc": 200}],
            }))
        return _FakeCompleted(stdout="", stderr="boom\n", returncode=1)

    monkeypatch.setattr("selfdoc.quality.effects.run", fake_run)
    with pytest.raises(DirstatError):
        get_code_loc(tmp_path, ["vendor"])


def test_a_submodule_subtraction_reduces_the_totals(monkeypatch, tmp_path):
    sub = tmp_path / "vendor"
    sub.mkdir()

    calls = {"n": 0}

    def fake_run(argv, **kwargs):
        calls["n"] += 1
        loc = 200 if calls["n"] == 1 else 50
        count = 4 if calls["n"] == 1 else 1
        return _FakeCompleted(stdout=_envelope({
            "groups": [{"format": "py", "text": True, "count": count, "total_loc": loc}],
        }))

    monkeypatch.setattr("selfdoc.quality.effects.run", fake_run)
    assert get_code_loc(tmp_path, ["vendor"]) == (150, 3)
