"""Tests for selfdoc.check -- directive validation and coverage analysis."""

import json
import os

import pytest

from selfdoc.check import CheckResult, LintResult, check_docs, print_results


@pytest.fixture()
def python_project(tmp_path):
    """Create a minimal Python project with selfdoc config and source files."""
    # selfdoc.json
    config = {
        "language": "python",
        "source": ["mylib/"],
        "docs": "docs/",
        "output": "docs/_build/",
    }
    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    # Source: mylib/__init__.py with public symbols
    lib_dir = os.path.join(tmp_path, "mylib")
    os.makedirs(lib_dir)
    with open(os.path.join(lib_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(
            '"""My library."""\n'
            "\n"
            "def greet(name):\n"
            '    """Say hello."""\n'
            "    return f'Hello, {name}'\n"
            "\n"
            "def farewell(name):\n"
            '    """Say goodbye."""\n'
            "    return f'Goodbye, {name}'\n"
            "\n"
            "class Widget:\n"
            '    """A widget."""\n'
            "    pass\n"
            "\n"
            "def _private():\n"
            "    pass\n"
        )

    # Source: mylib/utils.py with more public symbols
    with open(os.path.join(lib_dir, "utils.py"), "w", encoding="utf-8") as f:
        f.write(
            '"""Utility functions."""\n'
            "\n"
            "def helper():\n"
            '    """Help."""\n'
            "    pass\n"
        )

    # docs/ directory
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)

    return tmp_path


# -- All directives resolve OK --


def test_all_directives_ok(python_project):
    """When all directives resolve successfully, all results are OK."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "# API\n"
            "\n"
            ":::module mylib\n"
            ":::\n"
        )

    result = check_docs(str(python_project))

    assert len(result.directive_results) == 1
    dr = result.directive_results[0]
    assert dr.file == "api.md"
    assert dr.line == 3
    assert dr.status == "OK"
    assert dr.error == ""
    assert "module" in dr.directive


def test_multiple_directives_all_ok(python_project):
    """Multiple directives in the same file all resolve OK."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "# API\n"
            "\n"
            ":::module mylib\n"
            ":::\n"
            "\n"
            ":::module mylib.utils\n"
            ":::\n"
        )

    result = check_docs(str(python_project))

    assert len(result.directive_results) == 2
    assert all(dr.status == "OK" for dr in result.directive_results)


# -- Failed directive --


def test_failed_directive_reported(python_project):
    """A directive that cannot resolve is reported as FAILED with an error."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "# API\n"
            "\n"
            ":::module mylib\n"
            ":::\n"
            "\n"
            ":::module nonexistent.module\n"
            ":::\n"
        )

    result = check_docs(str(python_project))

    assert len(result.directive_results) == 2

    ok_results = [dr for dr in result.directive_results if dr.status == "OK"]
    failed_results = [
        dr for dr in result.directive_results if dr.status == "FAILED"
    ]

    assert len(ok_results) == 1
    assert len(failed_results) == 1

    failed = failed_results[0]
    assert failed.file == "api.md"
    assert failed.line == 6
    assert "nonexistent" in failed.error
    assert "not found" in failed.error


def test_failed_test_directive(python_project):
    """A :::test directive pointing to a missing file is FAILED."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "tests.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Tests\n"
            "\n"
            ":::test missing.py TestX\n"
            ":::\n"
        )

    result = check_docs(str(python_project))

    assert len(result.directive_results) == 1
    dr = result.directive_results[0]
    assert dr.status == "FAILED"
    assert "not found" in dr.error


# -- Coverage stats --


def test_coverage_full(python_project):
    """Coverage is 100% when all source modules are referenced."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "# API\n"
            "\n"
            ":::module mylib\n"
            ":::\n"
            "\n"
            ":::module mylib.utils\n"
            ":::\n"
        )

    result = check_docs(str(python_project))

    assert result.coverage is not None
    # mylib/__init__.py has: greet, farewell, Widget (3 public)
    # mylib/utils.py has: helper (1 public)
    assert result.coverage.total_public == 4
    assert result.coverage.referenced == 4
    assert len(result.coverage.undocumented_symbols) == 0


def test_coverage_partial(python_project):
    """Coverage reflects only the modules referenced by :::module directives."""
    docs_dir = os.path.join(python_project, "docs")
    # Only document mylib (not mylib.utils)
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "# API\n"
            "\n"
            ":::module mylib\n"
            ":::\n"
        )

    result = check_docs(str(python_project))

    assert result.coverage is not None
    # 3 from mylib/__init__.py documented, 1 from utils.py not
    assert result.coverage.total_public == 4
    assert result.coverage.referenced == 3
    assert len(result.coverage.undocumented_symbols) == 1
    # The undocumented symbol should be from utils.py
    assert any("utils.py" in s for s in result.coverage.undocumented_symbols)


def test_coverage_none_documented(python_project):
    """Coverage is 0 when no :::module directives reference source files."""
    docs_dir = os.path.join(python_project, "docs")
    # A doc with no module directives
    with open(os.path.join(docs_dir, "guide.md"), "w", encoding="utf-8") as f:
        f.write("# Guide\n\nJust a guide, no directives.\n")

    result = check_docs(str(python_project))

    assert result.coverage is not None
    assert result.coverage.total_public == 4
    assert result.coverage.referenced == 0


# -- print_results output --


def test_print_results_ok(python_project, capsys):
    """print_results shows OK status for resolved directives."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write("# API\n\n:::module mylib\n:::\n")

    result = check_docs(str(python_project))
    print_results(result)
    captured = capsys.readouterr()

    assert "OK" in captured.out
    assert "api.md:3" in captured.out
    assert "module" in captured.out


def test_print_results_failed(python_project, capsys):
    """print_results shows FAILED status with error message."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write("# API\n\n:::module missing.mod\n:::\n")

    result = check_docs(str(python_project))
    print_results(result)
    captured = capsys.readouterr()

    assert "FAILED" in captured.out
    assert "not found" in captured.out


def test_print_results_coverage(python_project, capsys):
    """print_results shows coverage summary line."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write("# API\n\n:::module mylib\n:::\n")

    result = check_docs(str(python_project))
    print_results(result)
    captured = capsys.readouterr()

    assert "Coverage:" in captured.out
    assert "public symbols documented" in captured.out


def test_print_results_no_directives(capsys):
    """print_results handles empty results gracefully."""
    result = CheckResult()
    print_results(result)
    captured = capsys.readouterr()
    assert "No directives found" in captured.out


# -- Edge cases --


def test_no_docs_dir_raises(tmp_path):
    """check_docs raises when docs/ directory is missing."""
    config = {
        "language": "python",
        "source": ["src/"],
        "docs": "docs/",
        "output": "docs/_build/",
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)

    with pytest.raises(RuntimeError, match="not found"):
        check_docs(str(tmp_path))


def test_no_config_raises(tmp_path):
    """check_docs raises when selfdoc.json is missing."""
    with pytest.raises(RuntimeError, match="No selfdoc.json found"):
        check_docs(str(tmp_path))


def test_directives_across_multiple_files(python_project):
    """Directives in multiple doc files are all checked."""
    docs_dir = os.path.join(python_project, "docs")

    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write("# API\n\n:::module mylib\n:::\n")

    with open(os.path.join(docs_dir, "utils.md"), "w", encoding="utf-8") as f:
        f.write("# Utils\n\n:::module mylib.utils\n:::\n")

    result = check_docs(str(python_project))

    assert len(result.directive_results) == 2
    files_checked = {dr.file for dr in result.directive_results}
    assert "api.md" in files_checked
    assert "utils.md" in files_checked
    assert all(dr.status == "OK" for dr in result.directive_results)


# -- Lint framework --


def test_check_result_has_lints_field():
    """CheckResult has a lints field that defaults to an empty list."""
    result = CheckResult()
    assert hasattr(result, "lints")
    assert result.lints == []
    assert isinstance(result.lints, list)


def test_lint_result_construction():
    """LintResult can be constructed with all fields."""
    lint = LintResult(
        file="index.md",
        line=5,
        code="SEO001",
        message="Missing title tag",
        severity="warning",
    )
    assert lint.file == "index.md"
    assert lint.line == 5
    assert lint.code == "SEO001"
    assert lint.message == "Missing title tag"
    assert lint.severity == "warning"


def test_lint_result_line_none():
    """LintResult accepts None for line number."""
    lint = LintResult(
        file="page.md",
        line=None,
        code="SEO002",
        message="No meta description",
        severity="error",
    )
    assert lint.line is None
    assert lint.severity == "error"


def test_check_docs_returns_lints_list(python_project):
    """check_docs() returns a CheckResult with a lints list (even if empty)."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write("# API\n\n:::module mylib\n:::\n")

    result = check_docs(str(python_project))

    assert isinstance(result.lints, list)


def test_print_results_no_lints(python_project, capsys):
    """print_results shows 'No lints.' when there are no lint diagnostics."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write("# API\n\n:::module mylib\n:::\n")

    result = check_docs(str(python_project))
    print_results(result)
    captured = capsys.readouterr()

    assert "No lints." in captured.out


def test_print_results_with_lints(capsys):
    """print_results formats lint diagnostics correctly."""
    result = CheckResult(
        lints=[
            LintResult(
                file="index.md",
                line=3,
                code="SEO001",
                message="Missing title",
                severity="warning",
            ),
            LintResult(
                file="guide.md",
                line=None,
                code="SEO002",
                message="No description",
                severity="error",
            ),
        ],
    )
    # Need at least one directive result to avoid the "No directives" path
    from selfdoc.check import DirectiveResult

    result.directive_results = [
        DirectiveResult(
            file="index.md", line=1, directive=":::module foo", status="OK"
        )
    ]

    print_results(result)
    captured = capsys.readouterr()

    assert "warning: [SEO001] index.md:3 - Missing title" in captured.out
    assert "error: [SEO002] guide.md - No description" in captured.out
    assert "No lints." not in captured.out
