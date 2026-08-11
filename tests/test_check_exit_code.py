"""Exit-code parity across every check entry point.

``selfdoc check`` and ``selfblog check`` (unified) must reach the same
verdict for the same project state.  They did not: the unified path
compared ``documented < total_public`` directly, hardcoding a 100%
coverage requirement, while ``selfdoc check`` honored the configured
``coverage_threshold``.  A project with a lowered threshold therefore
passed one entry point and failed the other.
"""

import json
import os
import subprocess
import sys

import pytest


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


_LONG_DESC = (
    "A documentation page describing the library, its public functions and "
    "the way each one is meant to be used in practice"
)


@pytest.fixture()
def lowered_threshold_projects(tmp_path):
    """A constituent project at 50% coverage plus a docs-site unifying it.

    Both configs lower ``coverage_threshold`` to 0.4, so 50% documented
    coverage is a PASS by the configured policy.  Nothing else in either
    project emits an error-severity lint, which makes the coverage rule
    the only thing either entry point can disagree about.
    """
    root = tmp_path / "monorepo"
    lib = root / "lib"
    site = root / "docs-site"

    # -- constituent project: two public symbols, one documented ------------
    _write_json(_ensure(lib, "selfdoc.json"), {
        "source": [{"path": "mylib/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com/lib",
        "coverage_threshold": 0.4,
    })
    _write_text(str(lib / "mylib" / "alpha.py"),
                '"""Alpha module."""\n\n\ndef alpha():\n    """Do alpha."""\n    return 1\n')
    _write_text(str(lib / "mylib" / "beta.py"),
                '"""Beta module."""\n\n\ndef beta():\n    """Do beta."""\n    return 2\n')
    _write_text(
        str(lib / "docs" / "index.md"),
        "---\n"
        "title: Lib\n"
        f"description: {_LONG_DESC}\n"
        "---\n"
        "\n"
        "# Lib\n"
        "\n"
        ':-: ref path="mylib/alpha.py"\n',
    )

    # -- docs-site project: unifies the constituent -------------------------
    _write_json(_ensure(site, "selfdoc.json"), {
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "coverage_threshold": 0.4,
        "unified": {"projects": [{"path": "../lib"}]},
    })
    _write_text(
        str(site / "docs" / "index.md"),
        "---\n"
        "title: Docs\n"
        f"description: {_LONG_DESC}\n"
        "---\n"
        "\n"
        "# Docs\n",
    )

    return lib, site


def _ensure(directory, name):
    os.makedirs(directory, exist_ok=True)
    return os.path.join(str(directory), name)


def _run(module, cwd):
    return subprocess.run(
        [sys.executable, "-m", module, "check", "--no-auto-commit"],
        cwd=str(cwd), capture_output=True, text=True, timeout=180,
    )


def test_lowered_coverage_threshold_verdict_is_identical(
    lowered_threshold_projects,
):
    """Both entry points honor the configured coverage threshold.

    Red before the exit-code collapse: ``selfdoc check`` exits 0 (50%
    documented clears the configured 40% threshold) while ``selfblog
    check`` exits 1 (it demanded 100%).
    """
    lib, site = lowered_threshold_projects

    standalone = _run("selfdoc", lib)
    unified = _run("selfblog", site)

    assert standalone.returncode == 0, (
        "selfdoc check should pass at 50% documented coverage with a "
        f"configured threshold of 0.4:\n{standalone.stdout}\n{standalone.stderr}"
    )
    assert unified.returncode == standalone.returncode, (
        "selfblog check reached a different verdict than selfdoc check for "
        "the same project state -- the unified path is ignoring the "
        f"configured coverage_threshold:\n{unified.stdout}\n{unified.stderr}"
    )
