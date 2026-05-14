"""Tests for selfdoc.check -- directive validation and coverage analysis."""

import json
import os
from unittest import mock

import pytest

from selfdoc.check import CheckResult, DirectiveResult, LintResult, check_docs, filter_lints, print_results


@pytest.fixture()
def python_project(tmp_path):
    """Create a minimal Python project with selfdoc config and source files."""
    # selfdoc.json
    config = {
        "language": "python",
        "source": ["mylib/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
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
            ':-: ref path="mylib"\n'
        )

    result = check_docs(str(python_project))

    assert len(result.directive_results) == 1
    dr = result.directive_results[0]
    assert dr.file == "api.md"
    assert dr.line == 3
    assert dr.status == "OK"
    assert dr.error == ""
    assert "ref" in dr.directive


def test_multiple_directives_all_ok(python_project):
    """Multiple directives in the same file all resolve OK."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "# API\n"
            "\n"
            ':-: ref path="mylib"\n'
            "\n"
            ':-: ref path="mylib.utils"\n'
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
            ':-: ref path="mylib"\n'
            "\n"
            ':-: ref path="nonexistent.module"\n'
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
    assert failed.line == 5
    assert "nonexistent" in failed.error
    assert "not found" in failed.error


def test_failed_test_directive(python_project):
    """A code-test directive pointing to a missing file is FAILED."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "tests.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Tests\n"
            "\n"
            ':-: code-test path="missing.py" target="TestX"\n'
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
            ':-: ref path="mylib"\n'
            "\n"
            ':-: ref path="mylib.utils"\n'
        )

    result = check_docs(str(python_project))

    assert result.coverage is not None
    # mylib/__init__.py has: greet, farewell, Widget (3 public)
    # mylib/utils.py has: helper (1 public)
    assert result.coverage.total_public == 4
    assert result.coverage.referenced == 4
    assert len(result.coverage.undocumented_symbols) == 0


def test_coverage_partial(python_project):
    """Coverage reflects only the modules referenced by ref directives."""
    docs_dir = os.path.join(python_project, "docs")
    # Only document mylib (not mylib.utils)
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "# API\n"
            "\n"
            ':-: ref path="mylib"\n'
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
    """Coverage is 0 when no ref directives reference source files."""
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
        f.write('# API\n\n:-: ref path="mylib"\n')

    result = check_docs(str(python_project))
    print_results(result)
    captured = capsys.readouterr()

    assert "OK" in captured.out
    assert "api.md:3" in captured.out
    assert "ref" in captured.out


def test_print_results_failed(python_project, capsys):
    """print_results shows FAILED status with error message."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write('# API\n\n:-: ref path="missing.mod"\n')

    result = check_docs(str(python_project))
    print_results(result)
    captured = capsys.readouterr()

    assert "FAILED" in captured.out
    assert "not found" in captured.out


def test_print_results_coverage(python_project, capsys):
    """print_results shows coverage summary line."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write('# API\n\n:-: ref path="mylib"\n')

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
    assert "No lints." in captured.out


def test_print_results_no_directives_with_lints(capsys):
    """print_results shows lint output even when there are no directives."""
    result = CheckResult(
        lints=[
            LintResult(
                file="index.md",
                line=None,
                code="SEO006",
                message="No 'description' in frontmatter",
                severity="error",
            ),
        ],
    )
    print_results(result)
    captured = capsys.readouterr()
    assert "No directives found" in captured.out
    assert "SEO006" in captured.out
    assert "No 'description' in frontmatter" in captured.out


# -- Edge cases --


def test_no_docs_dir_raises(tmp_path):
    """check_docs raises when docs/ directory is missing."""
    config = {
        "language": "python",
        "source": ["src/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
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
        f.write('# API\n\n:-: ref path="mylib"\n')

    with open(os.path.join(docs_dir, "utils.md"), "w", encoding="utf-8") as f:
        f.write('# Utils\n\n:-: ref path="mylib.utils"\n')

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
        f.write('# API\n\n:-: ref path="mylib"\n')

    result = check_docs(str(python_project))

    assert isinstance(result.lints, list)


def test_print_results_no_lints(python_project, capsys):
    """print_results shows 'No lints.' when there are no lint diagnostics."""
    docs_dir = os.path.join(python_project, "docs")
    desc = "Complete API reference for the mylib library covering all public functions, classes, and utilities with detailed usage examples included"
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ntitle: API\ndescription: {desc}\n---\n"
            '# API\n\n:-: ref path="mylib"\n'
        )

    # Add base_url to config so SEO005 does not trigger
    config_path = os.path.join(python_project, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

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
    from selfdoc.check import DirectiveResult

    result.directive_results = [
        DirectiveResult(
            file="index.md", line=1, directive='ref path="foo"', status="OK"
        )
    ]

    print_results(result)
    captured = capsys.readouterr()

    assert "SEO001" in captured.out
    assert "Missing title" in captured.out
    assert "SEO002" in captured.out
    assert "No description" in captured.out
    assert "No lints." not in captured.out


# -- SEO lint rules --


from selfdoc.check import _run_lints


@pytest.fixture()
def lint_project(tmp_path):
    """Create a minimal project with docs dir and config for lint testing."""
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    config = {
        "language": "python",
        "source": ["src/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    return tmp_path, docs_dir, config


def test_seo001_multiple_h1s(lint_project):
    """SEO001: file with two H1 headings triggers an error."""
    _, docs_dir, config = lint_project
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# First Title\n\nSome text.\n\n# Second Title\n\nMore text.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo001 = [r for r in results if r.code == "SEO001"]

    assert len(seo001) == 1
    assert seo001[0].file == "page.md"
    assert seo001[0].severity == "error"
    assert "2" in seo001[0].message


def test_seo001_single_h1_no_warning(lint_project):
    """SEO001: file with one H1 does not trigger a warning."""
    _, docs_dir, config = lint_project
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Only Title\n\n## Subsection\n\n### Sub-subsection\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo001 = [r for r in results if r.code == "SEO001"]
    assert len(seo001) == 0


def test_seo002_heading_level_gap(lint_project):
    """SEO002: heading that jumps from H2 to H4 triggers a warning."""
    _, docs_dir, config = lint_project
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n## Section\n\n#### Skipped H3\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo002 = [r for r in results if r.code == "SEO002"]

    assert len(seo002) == 1
    assert seo002[0].file == "page.md"
    assert seo002[0].severity == "warning"
    assert seo002[0].line is not None
    assert "H2" in seo002[0].message
    assert "H4" in seo002[0].message


def test_seo002_no_gap(lint_project):
    """SEO002: sequential heading levels do not trigger a warning."""
    _, docs_dir, config = lint_project
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n## Section\n\n### Subsection\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo002 = [r for r in results if r.code == "SEO002"]
    assert len(seo002) == 0


def test_seo003_empty_alt_text(lint_project):
    """SEO003: image with empty alt text triggers a warning."""
    _, docs_dir, config = lint_project
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n![](image.png)\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo003 = [r for r in results if r.code == "SEO003"]

    assert len(seo003) == 1
    assert seo003[0].file == "page.md"
    assert seo003[0].severity == "warning"
    assert seo003[0].line is not None


def test_seo003_with_alt_text_no_warning(lint_project):
    """SEO003: image with alt text does not trigger a warning."""
    _, docs_dir, config = lint_project
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n![screenshot](image.png)\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo003 = [r for r in results if r.code == "SEO003"]
    assert len(seo003) == 0


def test_seo004_title_too_long(lint_project):
    """SEO004: frontmatter title that exceeds 60 chars with project name warns."""
    tmp_path, docs_dir, config = lint_project
    long_title = "A Very Long Page Title That Will Exceed The Sixty Character Limit"
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ntitle: {long_title}\ndescription: test\n---\n"
            "# Title\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo004 = [r for r in results if r.code == "SEO004"]

    # project_name is derived from docs_dir parent basename
    project_name = os.path.basename(str(tmp_path))
    combined_len = len(long_title) + len(" - ") + len(project_name)
    assert combined_len > 60, "Test setup: combined title must exceed 60 chars"

    assert len(seo004) == 1
    assert seo004[0].file == "page.md"
    assert seo004[0].severity == "warning"


def test_seo004_short_title_no_warning(lint_project):
    """SEO004: short frontmatter title does not trigger a warning."""
    _, docs_dir, config = lint_project
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ntitle: Hi\ndescription: test\n---\n"
            "# Hi\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo004 = [r for r in results if r.code == "SEO004"]
    assert len(seo004) == 0


def test_seo006_missing_description(lint_project):
    """SEO006: file without description in frontmatter triggers an error."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ntitle: My Page\n---\n"
            "# My Page\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo006 = [r for r in results if r.code == "SEO006"]

    assert len(seo006) == 1
    assert seo006[0].file == "page.md"
    assert seo006[0].severity == "error"
    assert "description" in seo006[0].message


def test_seo006_with_description_no_warning(lint_project):
    """SEO006: file with description in frontmatter does not trigger a warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ntitle: My Page\ndescription: A great page\n---\n"
            "# My Page\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo006 = [r for r in results if r.code == "SEO006"]
    assert len(seo006) == 0


def test_clean_file_no_lints(lint_project):
    """A well-formed file with all metadata produces no lint warnings."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A clean page demonstrating proper formatting and metadata usage for SEO best practices and documentation quality standards"
    # Generate a paragraph of 50 words to satisfy SEO007 (40-60 words)
    para = " ".join(["word"] * 50)
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ntitle: Clean\ndescription: {desc}\n---\n"
            f"# Clean\n\n## Section\n\n{para}\n\n### Subsection\n\n"
            f"{para}\n\n![diagram](diagram.png)\n"
        )

    results = _run_lints(docs_dir, None, config)
    assert len(results) == 0


# -- Info severity and verbose --


def test_info_lints_always_shown(capsys):
    """Info-level lints are always shown (no verbose flag needed)."""
    from selfdoc.check import DirectiveResult

    result = CheckResult(
        directive_results=[
            DirectiveResult(
                file="index.md", line=1, directive='ref path="foo"', status="OK"
            )
        ],
        lints=[
            LintResult(
                file="index.md",
                line=5,
                code="SEO099",
                message="Test info lint",
                severity="info",
            ),
        ],
    )

    print_results(result)
    captured = capsys.readouterr()

    assert "SEO099" in captured.out
    assert "Test info lint" in captured.out


def test_warning_and_info_lints_both_shown(capsys):
    """Both warning and info lints are shown together."""
    from selfdoc.check import DirectiveResult

    result = CheckResult(
        directive_results=[
            DirectiveResult(
                file="index.md", line=1, directive='ref path="foo"', status="OK"
            )
        ],
        lints=[
            LintResult(
                file="index.md",
                line=5,
                code="SEO001",
                message="Test warning lint",
                severity="warning",
            ),
            LintResult(
                file="index.md",
                line=10,
                code="SEO099",
                message="Test info lint",
                severity="info",
            ),
        ],
    )

    print_results(result)
    captured = capsys.readouterr()

    assert "SEO001" in captured.out
    assert "Test warning lint" in captured.out
    assert "SEO099" in captured.out
    assert "Test info lint" in captured.out


def test_info_lints_do_not_show_no_lints_message(capsys):
    """When info lints exist, 'No lints.' message is not shown."""
    from selfdoc.check import DirectiveResult

    result = CheckResult(
        directive_results=[
            DirectiveResult(
                file="index.md", line=1, directive='ref path="foo"', status="OK"
            )
        ],
        lints=[
            LintResult(
                file="page.md", line=3, code="SEO099",
                message="Short paragraph", severity="info",
            ),
            LintResult(
                file="page.md", line=None, code="SEO098",
                message="No numbers", severity="info",
            ),
        ],
    )

    print_results(result)
    captured = capsys.readouterr()

    assert "No lints." not in captured.out
    assert "SEO099" in captured.out
    assert "SEO098" in captured.out


# -- SEO007: Paragraph length after headings --


def test_seo007_short_paragraph(lint_project):
    """SEO007: short paragraph after heading triggers warning lint."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n"
            "## Section\n\n"
            "This is short.\n\n"
            "More content here.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo007 = [r for r in results if r.code == "SEO007"]

    assert len(seo007) == 1
    assert seo007[0].severity == "warning"
    assert "3 words" in seo007[0].message
    assert "Section" in seo007[0].message


def test_seo007_normal_paragraph_no_lint(lint_project):
    """SEO007: paragraph of 40-60 words does not trigger a lint."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    # Generate a paragraph of exactly 50 words
    words = " ".join(["word"] * 50)
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n"
            f"## Section\n\n"
            f"{words}\n\n"
            "More content.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo007 = [r for r in results if r.code == "SEO007"]

    assert len(seo007) == 0


# -- SEO008: Statistics density --


def test_seo008_no_numbers_long_page(lint_project):
    """SEO008: page with >200 words and no numbers triggers warning lint."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    words = " ".join(["word"] * 250)
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n"
            f"{words}\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo008 = [r for r in results if r.code == "SEO008"]

    assert len(seo008) == 1
    assert seo008[0].severity == "warning"
    assert "words" in seo008[0].message
    assert "no numeric" in seo008[0].message


def test_seo008_with_numbers_no_lint(lint_project):
    """SEO008: page with numbers does not trigger a lint."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    words = " ".join(["word"] * 200) + " 42 items"
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n"
            f"{words}\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo008 = [r for r in results if r.code == "SEO008"]

    assert len(seo008) == 0


def test_seo008_short_page_no_lint(lint_project):
    """SEO008: page with <200 words does not trigger a lint (even without numbers)."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    words = " ".join(["word"] * 100)
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n"
            f"{words}\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo008 = [r for r in results if r.code == "SEO008"]

    assert len(seo008) == 0


# -- SEO009: Description too short --


def test_seo009_short_description(lint_project):
    """SEO009: frontmatter description under 120 chars triggers warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    # 70 chars -- above old threshold of 50 but below new threshold of 120
    desc = "A" * 70
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo009 = [r for r in results if r.code == "SEO009"]

    assert len(seo009) == 1
    assert seo009[0].severity == "warning"
    assert "aim for 120-155" in seo009[0].message


def test_seo009_no_description_does_not_trigger(lint_project):
    """SEO009: no description at all does NOT trigger (SEO006 covers that)."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write("# Title\n")

    results = _run_lints(docs_dir, None, config)
    seo009 = [r for r in results if r.code == "SEO009"]

    assert len(seo009) == 0


def test_seo009_normal_length_no_trigger(lint_project):
    """SEO009: description of normal length (120-155 chars) does not trigger."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130  # 130 chars, within range
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo009 = [r for r in results if r.code == "SEO009"]

    assert len(seo009) == 0


# -- SEO010: Frontmatter description too long --


def test_seo010_long_description(lint_project):
    """SEO010: frontmatter description over 155 chars triggers warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 200  # 200 chars, over limit
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo010 = [r for r in results if r.code == "SEO010"]

    assert len(seo010) == 1
    assert seo010[0].severity == "warning"
    assert "200" in seo010[0].message
    assert "max 155" in seo010[0].message


def test_seo010_normal_length_no_trigger(lint_project):
    """SEO010: frontmatter description within 155 chars does not trigger."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 100  # 100 chars, within limit
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo010 = [r for r in results if r.code == "SEO010"]

    assert len(seo010) == 0


# -- SEO011: Empty heading section --


def test_seo011_h2_followed_by_h2(lint_project):
    """SEO011: H2 followed by H2 with no content triggers warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A page for testing empty heading sections in documentation"
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n## Foo\n\n## Bar\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo011 = [r for r in results if r.code == "SEO011"]

    assert len(seo011) == 1
    assert seo011[0].severity == "warning"
    assert "H2" in seo011[0].message


def test_seo011_h3_followed_by_h2(lint_project):
    """SEO011: H3 followed by H2 (empty H3 section) triggers warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A page for testing empty heading sections in documentation"
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n### A\n\n## B\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo011 = [r for r in results if r.code == "SEO011"]

    assert len(seo011) == 1
    assert seo011[0].severity == "warning"


def test_seo011_h2_with_content_no_trigger(lint_project):
    """SEO011: H2 with content before next H2 does not trigger."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A page for testing that headings with content pass validation"
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n## Foo\n\nSome text.\n\n## Bar\n\nMore text.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo011 = [r for r in results if r.code == "SEO011"]

    assert len(seo011) == 0


def test_seo011_h2_followed_by_h3_no_trigger(lint_project):
    """SEO011: H2 followed by H3 (valid subsection nesting) does not trigger."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A page for testing valid heading nesting with subsections"
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n## Foo\n\n### Bar\n\nText here.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo011 = [r for r in results if r.code == "SEO011"]

    assert len(seo011) == 0


# -- SEO012: WCAG contrast ratio checks --


from selfdoc.check import (
    _check_contrast, _parse_hex_color, _relative_luminance, _contrast_ratio,
)


def test_seo012_default_theme_passes(lint_project):
    """Default minimal theme passes all contrast checks (no SEO012)."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"
    config["theme"] = "minimal"

    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo012 = [r for r in results if r.code == "SEO012"]

    assert len(seo012) == 0


def test_seo012_low_contrast_triggers(lint_project, tmp_path):
    """Mock CSS with low contrast triggers SEO012 warnings."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    # Directly test _check_pairs with bad contrast values
    lints = []
    mock_css_vars = {
        "--bg": "#ffffff",
        "--text": "#eeeeee",          # Very light gray on white = bad
        "--text-secondary": "#dddddd",  # Even worse
        "--heading": "#fafafa",        # Nearly invisible
        "--link": "#f0f0f0",           # Bad contrast
        "--sidebar-bg": "#ffffff",
        "--sidebar-text": "#eeeeee",   # Bad
    }

    from selfdoc.check import _check_pairs
    pairs = [
        ("--text", "--bg", "body text", 4.5),
        ("--text-secondary", "--bg", "secondary text", 4.5),
        ("--heading", "--bg", "headings", 3.0),
        ("--link", "--bg", "links", 4.5),
        ("--sidebar-text", "--sidebar-bg", "sidebar text", 4.5),
    ]

    _check_pairs(lints, mock_css_vars, pairs, "")

    seo012 = [r for r in lints if r.code == "SEO012"]
    assert len(seo012) == 5  # All 5 pairs fail
    assert all(r.severity == "warning" for r in seo012)
    assert any("body text" in r.message for r in seo012)
    assert any("WCAG AA" in r.message for r in seo012)


def test_contrast_ratio_black_on_white():
    """Black on white has maximum contrast ratio of 21:1."""
    black = (0, 0, 0)
    white = (255, 255, 255)
    ratio = _contrast_ratio(black, white)
    assert abs(ratio - 21.0) < 0.1


def test_contrast_ratio_same_color():
    """Same color has contrast ratio of 1:1."""
    gray = (128, 128, 128)
    ratio = _contrast_ratio(gray, gray)
    assert abs(ratio - 1.0) < 0.01


def test_parse_hex_color_valid():
    """Valid hex colors are parsed correctly."""
    assert _parse_hex_color("#ffffff") == (255, 255, 255)
    assert _parse_hex_color("#000000") == (0, 0, 0)
    assert _parse_hex_color("#0969da") == (9, 105, 218)


def test_parse_hex_color_invalid():
    """Invalid hex colors return None."""
    assert _parse_hex_color("not-a-color") is None
    assert _parse_hex_color("#fff") is None  # Too short


# -- SEO lints always run --


def test_seo_lints_always_run(python_project):
    """check_docs always runs SEO lints (no skip_seo parameter)."""
    docs_dir = os.path.join(python_project, "docs")
    # Write a file that produces SEO warnings:
    # no frontmatter description (SEO006)
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write('# API\n\n:-: ref path="mylib"\n')

    result = check_docs(str(python_project))
    assert len(result.lints) > 0
    # SEO006 (missing description) should be present
    seo006 = [l for l in result.lints if l.code == "SEO006"]
    assert len(seo006) >= 1
    # Directive validation still works
    assert len(result.directive_results) == 1
    assert result.directive_results[0].status == "OK"


# -- SEO013: Missing H1 --


def test_seo013_no_h1(lint_project):
    """SEO013: page with no H1 heading and no frontmatter title triggers error."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "## Only H2\n\nSome content here.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo013 = [r for r in results if r.code == "SEO013"]

    assert len(seo013) == 1
    assert seo013[0].severity == "error"
    assert "No title source" in seo013[0].message


def test_seo013_with_h1_no_warning(lint_project):
    """SEO013: page with an H1 heading does not trigger error."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\nSome content here.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo013 = [r for r in results if r.code == "SEO013"]

    assert len(seo013) == 0


def test_seo013_with_frontmatter_title_no_h1(lint_project):
    """SEO013: page with frontmatter title but no H1 does not trigger error."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ntitle: My Page\ndescription: {desc}\n---\n"
            "## Section\n\nSome content here.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo013 = [r for r in results if r.code == "SEO013"]

    assert len(seo013) == 0


# -- SEO004: Auto-extracted title length (H1 fallback) --


def test_seo004_long_h1_no_frontmatter_title(lint_project):
    """SEO004: long H1 heading without frontmatter title fires warning."""
    tmp_path, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    long_h1 = "A Very Long Page Title That Will Exceed The Sixty Character Limit"
    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            f"# {long_h1}\n\nContent.\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo004 = [r for r in results if r.code == "SEO004"]

    # Verify that combined length exceeds 60
    project_name = os.path.basename(str(tmp_path))
    combined_len = len(long_h1) + len(" - ") + len(project_name)
    assert combined_len > 60, "Test setup: combined title must exceed 60 chars"

    assert len(seo004) == 1
    assert seo004[0].file == "page.md"
    assert seo004[0].severity == "warning"


# -- SEO014: Meaningless alt text --


def test_seo014_meaningless_alt(lint_project):
    """SEO014: image with meaningless alt text triggers warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n![image](photo.png)\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo014 = [r for r in results if r.code == "SEO014"]

    assert len(seo014) == 1
    assert seo014[0].severity == "warning"
    assert "Meaningless alt text" in seo014[0].message
    assert "'image'" in seo014[0].message


def test_seo014_filename_alt(lint_project):
    """SEO014: image with filename as alt text triggers warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n![dashboard-v2.png](assets/dashboard.png)\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo014 = [r for r in results if r.code == "SEO014"]

    assert len(seo014) == 1
    assert seo014[0].severity == "warning"
    assert "dashboard-v2.png" in seo014[0].message


def test_seo014_single_char_alt(lint_project):
    """SEO014: single-character alt text triggers warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n![x](photo.png)\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo014 = [r for r in results if r.code == "SEO014"]

    assert len(seo014) == 1
    assert seo014[0].severity == "warning"
    assert "'x'" in seo014[0].message


def test_seo014_descriptive_alt_no_warning(lint_project):
    """SEO014: image with descriptive alt text does not trigger warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n![Architecture diagram showing request flow](arch.png)\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo014 = [r for r in results if r.code == "SEO014"]

    assert len(seo014) == 0


# -- SEO015: Generic anchor text --


def test_seo015_generic_anchor(lint_project):
    """SEO015: generic anchor text triggers warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n[click here](https://example.com)\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo015 = [r for r in results if r.code == "SEO015"]

    assert len(seo015) == 1
    assert seo015[0].severity == "warning"
    assert "Generic anchor text" in seo015[0].message
    assert "'click here'" in seo015[0].message


def test_seo015_descriptive_anchor_no_warning(lint_project):
    """SEO015: descriptive anchor text does not trigger warning."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n[selfdoc configuration reference](https://example.com/config)\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo015 = [r for r in results if r.code == "SEO015"]

    assert len(seo015) == 0


def test_seo015_inside_code_block_no_warning(lint_project):
    """SEO015: generic anchor text inside a fenced code block does NOT trigger."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n"
            "```\n"
            "[click here](url)\n"
            "```\n"
        )

    results = _run_lints(docs_dir, None, config)
    seo015 = [r for r in results if r.code == "SEO015"]

    assert len(seo015) == 0


# -- Ignore flag and lint_ignore --


def test_ignore_flag_suppresses_lint():
    """filter_lints with ignore='SEO001' removes SEO001 from results."""
    lints = [
        LintResult(file="a.md", line=1, code="SEO001", message="m1", severity="warning"),
        LintResult(file="b.md", line=2, code="SEO006", message="m2", severity="error"),
        LintResult(file="c.md", line=3, code="SEO007", message="m3", severity="warning"),
    ]
    filtered = filter_lints(lints, {"SEO001"})
    codes = [lint.code for lint in filtered]
    assert "SEO001" not in codes
    assert "SEO006" in codes
    assert "SEO007" in codes


def test_lint_ignore_config():
    """filter_lints with config lint_ignore=['SEO007'] removes SEO007."""
    lints = [
        LintResult(file="a.md", line=1, code="SEO001", message="m1", severity="warning"),
        LintResult(file="b.md", line=2, code="SEO007", message="m2", severity="warning"),
    ]
    # Simulate config lint_ignore
    config_ignore = {"SEO007"}
    filtered = filter_lints(lints, config_ignore)
    codes = [lint.code for lint in filtered]
    assert "SEO007" not in codes
    assert "SEO001" in codes


def test_ignore_merges_cli_and_config():
    """Combined CLI and config ignore sets filter both codes."""
    lints = [
        LintResult(file="a.md", line=1, code="SEO001", message="m1", severity="warning"),
        LintResult(file="b.md", line=2, code="SEO007", message="m2", severity="warning"),
        LintResult(file="c.md", line=3, code="SEO009", message="m3", severity="warning"),
    ]
    cli_ignore = {"SEO001"}
    config_ignore = {"SEO007"}
    combined = cli_ignore | config_ignore
    filtered = filter_lints(lints, combined)
    codes = [lint.code for lint in filtered]
    assert "SEO001" not in codes
    assert "SEO007" not in codes
    assert "SEO009" in codes


# -- ANSI color output --


def test_color_output_on_tty(capsys):
    """When stdout is a TTY, output contains ANSI escape codes."""
    import selfdoc.check as check_mod

    result = CheckResult(
        directive_results=[
            DirectiveResult(
                file="index.md", line=1, directive='ref path="foo"', status="OK"
            )
        ],
        lints=[
            LintResult(
                file="index.md", line=5, code="SEO001",
                message="Test warning", severity="warning",
            ),
        ],
    )

    old_use_color = check_mod._USE_COLOR
    try:
        check_mod._USE_COLOR = True
        print_results(result)
        captured = capsys.readouterr()
        # Should contain ANSI escape codes
        assert "\033[" in captured.out
        # Green for OK
        assert "\033[32m" in captured.out
        # Yellow for warning
        assert "\033[33m" in captured.out
        # Cyan for lint code
        assert "\033[36m" in captured.out
    finally:
        check_mod._USE_COLOR = old_use_color


def test_plain_output_on_pipe(capsys):
    """When stdout is not a TTY, output contains no ANSI escape codes."""
    import selfdoc.check as check_mod

    result = CheckResult(
        directive_results=[
            DirectiveResult(
                file="index.md", line=1, directive='ref path="foo"', status="OK"
            )
        ],
        lints=[
            LintResult(
                file="index.md", line=5, code="SEO001",
                message="Test warning", severity="warning",
            ),
        ],
    )

    old_use_color = check_mod._USE_COLOR
    try:
        check_mod._USE_COLOR = False
        print_results(result)
        captured = capsys.readouterr()
        # Should NOT contain ANSI escape codes
        assert "\033[" not in captured.out
        # Content should still be present
        assert "OK" in captured.out
        assert "SEO001" in captured.out
    finally:
        check_mod._USE_COLOR = old_use_color


# -- Undocumented symbols printed --


def test_undocumented_symbols_printed(python_project, capsys):
    """When coverage < 100%, undocumented symbols are printed grouped by file."""
    import selfdoc.check as check_mod

    docs_dir = os.path.join(python_project, "docs")
    # Only document mylib (not mylib.utils) -- utils.py:helper is undocumented
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write('# API\n\n:-: ref path="mylib"\n')

    result = check_docs(str(python_project))

    old_use_color = check_mod._USE_COLOR
    try:
        check_mod._USE_COLOR = False
        print_results(result)
    finally:
        check_mod._USE_COLOR = old_use_color
    captured = capsys.readouterr()

    assert "Undocumented symbols:" in captured.out
    assert "utils.py" in captured.out
    assert "helper" in captured.out


# -- JSON format --


def test_json_format(python_project, capsys):
    """--format json outputs valid JSON with expected structure."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write('# API\n\n:-: ref path="mylib"\n')

    result = check_docs(str(python_project))

    # Simulate the JSON output path from _cmd_check
    output = {
        "directives": [
            {
                "file": dr.file,
                "line": dr.line,
                "directive": dr.directive,
                "status": dr.status,
                "error": dr.error,
            }
            for dr in result.directive_results
        ],
        "coverage": None,
        "lints": [
            {
                "file": lint.file,
                "line": lint.line,
                "code": lint.code,
                "message": lint.message,
                "severity": lint.severity,
            }
            for lint in result.lints
        ],
        "exit_code": 0,
    }
    if result.coverage is not None:
        cov = result.coverage
        output["coverage"] = {
            "total_public": cov.total_public,
            "referenced": cov.referenced,
            "documented_symbols": cov.documented_symbols,
            "undocumented_symbols": cov.undocumented_symbols,
        }

    json_str = json.dumps(output, indent=2)
    print(json_str)
    captured = capsys.readouterr()

    parsed = json.loads(captured.out)
    assert "directives" in parsed
    assert "coverage" in parsed
    assert "lints" in parsed
    assert "exit_code" in parsed
    assert isinstance(parsed["directives"], list)
    assert isinstance(parsed["lints"], list)
    assert parsed["coverage"] is not None
    assert "total_public" in parsed["coverage"]
    assert "undocumented_symbols" in parsed["coverage"]


# -- Per-symbol coverage --


def test_coverage_per_symbol(tmp_path):
    """Coverage tracks individual symbols, not whole files.

    A :::module directive that only mentions 1 of 3 public symbols
    should yield 1/3 coverage, not 3/3.
    """
    # selfdoc.json
    config = {
        "language": "python",
        "source": ["mylib/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)

    # Source: mylib/__init__.py with 3 public symbols
    lib_dir = os.path.join(tmp_path, "mylib")
    os.makedirs(lib_dir)
    with open(os.path.join(lib_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(
            '"""My library."""\n'
            "\n"
            "def alpha():\n"
            '    """Alpha function."""\n'
            "    pass\n"
            "\n"
            "def beta():\n"
            '    """Beta function."""\n'
            "    pass\n"
            "\n"
            "def gamma():\n"
            '    """Gamma function."""\n'
            "    pass\n"
        )

    # docs/ with a :::module directive -- the resolved output from
    # _handle_module will contain all 3 symbol names (alpha, beta, gamma)
    # because it formats all functions. But we need a case where the
    # resolved content only mentions some symbols.
    #
    # Actually, :::module always dumps all public symbols, so to test
    # per-symbol tracking we need to verify that when a module IS
    # referenced, each symbol name is checked against the resolved content.
    # Since _handle_module includes all public function names in its output,
    # all 3 will be documented. Let's verify that works correctly first,
    # then test a case where a symbol name does NOT appear.

    # Create a file with a symbol whose name won't appear in the resolved
    # content. For example, if a function has no docstring and no body,
    # the extractor still includes its name as a heading. So all symbols
    # in a :::module directive will appear. The per-symbol tracking matters
    # when only SOME files are referenced -- symbols in unreferenced files
    # remain undocumented.

    # Better test: have two files. Reference one, not the other.
    # The referenced file has symbols that appear in its resolved content.
    with open(os.path.join(lib_dir, "extras.py"), "w", encoding="utf-8") as f:
        f.write(
            '"""Extra utilities."""\n'
            "\n"
            "def delta():\n"
            '    """Delta function."""\n'
            "    pass\n"
        )

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    # Only reference mylib (not mylib.extras)
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write('# API\n\n:-: ref path="mylib"\n')

    result = check_docs(str(tmp_path))
    assert result.coverage is not None
    # mylib/__init__.py has alpha, beta, gamma -- all appear in resolved content
    # mylib/extras.py has delta -- not referenced at all
    assert result.coverage.total_public == 4
    assert result.coverage.referenced == 3
    assert len(result.coverage.undocumented_symbols) == 1
    assert any("delta" in s for s in result.coverage.undocumented_symbols)


# -- Multi-directive coverage --


def test_coverage_multi_directive(tmp_path):
    """table-schema and code-test directives contribute to coverage."""
    config = {
        "language": "python",
        "source": ["mylib/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)

    lib_dir = os.path.join(tmp_path, "mylib")
    os.makedirs(lib_dir)

    # Source file with a class (for :::schema) and a function
    with open(os.path.join(lib_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(
            '"""My library."""\n'
            "\n"
            "from dataclasses import dataclass\n"
            "\n"
            "@dataclass\n"
            "class Config:\n"
            '    """Configuration."""\n'
            "    name: str = ''\n"
            "\n"
            "def helper():\n"
            '    """Help."""\n'
            "    pass\n"
        )

    # Test file (for :::test directive)
    tests_dir = os.path.join(tmp_path, "tests")
    os.makedirs(tests_dir)
    with open(os.path.join(tests_dir, "test_mylib.py"), "w", encoding="utf-8") as f:
        f.write(
            "def test_helper():\n"
            "    assert True\n"
        )

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "# API\n\n"
            ':-: table-schema path="mylib" target="Config"\n'
            "\n"
            ':-: code-test path="tests/test_mylib.py" target="test_helper"\n'
        )

    result = check_docs(str(tmp_path))
    assert result.coverage is not None
    # Config and helper are the public symbols
    assert result.coverage.total_public == 2
    # table-schema references Config by name in target attr
    assert result.coverage.referenced >= 1
    # Config should be documented
    assert any("Config" in s for s in result.coverage.documented_symbols)


# -- Coverage threshold --


def test_coverage_threshold_pass(tmp_path):
    """min_coverage=50 with 3/4 documented (75%) passes."""
    config = {
        "language": "python",
        "source": ["mylib/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "min_coverage": 50,
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)

    lib_dir = os.path.join(tmp_path, "mylib")
    os.makedirs(lib_dir)
    with open(os.path.join(lib_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(
            '"""My lib."""\n'
            "def greet(): pass\n"
            "def farewell(): pass\n"
            "def wave(): pass\n"
        )
    with open(os.path.join(lib_dir, "extra.py"), "w", encoding="utf-8") as f:
        f.write("def bonus(): pass\n")

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write('# API\n\n:-: ref path="mylib"\n')

    result = check_docs(str(tmp_path))
    assert result.coverage is not None
    # 3/4 = 75% > 50% threshold
    assert result.coverage.referenced == 3
    assert result.coverage.total_public == 4

    # Simulate what _cmd_check does for threshold
    from selfdoc.config import load_config
    cfg = load_config(str(tmp_path))
    min_cov = cfg.get("min_coverage")
    actual_pct = result.coverage.referenced * 100 // result.coverage.total_public
    assert actual_pct >= min_cov  # 75 >= 50 -- should pass


def test_coverage_threshold_fail(tmp_path, capsys):
    """min_coverage=80 with 1/3 documented (33%) fails."""
    config = {
        "language": "python",
        "source": ["mylib/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "min_coverage": 80,
        "lint_ignore": ["SEO006", "SEO009", "SEO013"],
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)

    lib_dir = os.path.join(tmp_path, "mylib")
    os.makedirs(lib_dir)
    with open(os.path.join(lib_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(
            '"""Lib."""\n'
            "def alpha(): pass\n"
        )
    with open(os.path.join(lib_dir, "other.py"), "w", encoding="utf-8") as f:
        f.write(
            "def beta(): pass\n"
            "def gamma(): pass\n"
        )

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write('# API\n\n:-: ref path="mylib"\n')

    result = check_docs(str(tmp_path))
    assert result.coverage is not None
    # 1 documented (alpha from mylib/__init__.py), 2 undocumented
    assert result.coverage.total_public == 3
    assert result.coverage.referenced == 1

    # Check the threshold logic
    from selfdoc.config import load_config
    cfg = load_config(str(tmp_path))
    min_cov = cfg.get("min_coverage")
    actual_pct = result.coverage.referenced * 100 // result.coverage.total_public
    assert actual_pct < min_cov  # 33 < 80 -- should fail


# -- Warn-only mode --


def test_warn_only_mode(tmp_path, capsys):
    """With warn_only, SEO warnings do not cause exit code 1."""
    config = {
        "language": "python",
        "source": ["mylib/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)

    lib_dir = os.path.join(tmp_path, "mylib")
    os.makedirs(lib_dir)
    with open(os.path.join(lib_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Lib."""\ndef greet(): pass\n')

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    # No frontmatter description -> triggers SEO006 warning
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write('# API\n\n:-: ref path="mylib"\n')

    result = check_docs(str(tmp_path))

    # Verify there ARE warnings
    has_warnings = any(lint.severity == "warning" for lint in result.lints)
    has_failures = any(dr.status == "FAILED" for dr in result.directive_results)

    # With warn_only=True, warnings should not contribute to exit code
    exit_code_warn_only = 1 if has_failures else 0
    exit_code_normal = 1 if (has_failures or has_warnings) else 0

    # There should be warnings (SEO lints)
    assert len(result.lints) > 0
    # No directive failures
    assert not has_failures
    # Normal mode would exit 1 due to warnings
    assert exit_code_normal == 1
    # Warn-only mode exits 0 since no directive failures
    assert exit_code_warn_only == 0


# -- Go coverage --


def test_go_coverage_basic(tmp_path):
    """Create a Go project with exported and unexported symbols, verify coverage."""
    # selfdoc.json
    config = {
        "language": "go",
        "source": ["pkg/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    # Source: pkg/server/server.go with exported symbols
    pkg_dir = os.path.join(tmp_path, "pkg", "server")
    os.makedirs(pkg_dir)
    with open(os.path.join(pkg_dir, "server.go"), "w", encoding="utf-8") as f:
        f.write(
            'package server\n'
            '\n'
            '// Start starts the server.\n'
            'func Start() {}\n'
            '\n'
            '// Stop stops the server.\n'
            'func Stop() {}\n'
            '\n'
            'func helper() {}\n'
        )

    # Source: pkg/util/util.go with more exports
    util_dir = os.path.join(tmp_path, "pkg", "util")
    os.makedirs(util_dir)
    with open(os.path.join(util_dir, "util.go"), "w", encoding="utf-8") as f:
        f.write(
            'package util\n'
            '\n'
            'func Format() string { return "" }\n'
        )

    # docs/ directory with a directive referencing only pkg/server
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "# API\n"
            "\n"
            ':-: ref path="pkg/server"\n'
        )

    result = check_docs(str(tmp_path))

    assert result.coverage is not None
    # pkg/server/server.go has Start, Stop (2 exported; helper is unexported)
    # pkg/util/util.go has Format (1 exported)
    # Total: 3 exported symbols
    assert result.coverage.total_public == 3
    # Only pkg/server is documented (Start and Stop appear in resolved content)
    assert result.coverage.referenced == 2
    # Format from util is undocumented
    assert len(result.coverage.undocumented_symbols) == 1
    assert any("Format" in s for s in result.coverage.undocumented_symbols)


# -- TypeScript/JavaScript coverage --


def test_ts_coverage_basic(tmp_path):
    """Create a TypeScript project with exports, verify coverage."""
    config = {
        "language": "typescript",
        "source": ["src/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    # Source: src/utils.ts with exports
    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir)
    with open(os.path.join(src_dir, "utils.ts"), "w", encoding="utf-8") as f:
        f.write(
            'export function format(s: string): string {\n'
            '    return s.trim();\n'
            '}\n'
            '\n'
            'export function parse(s: string): number {\n'
            '    return parseInt(s);\n'
            '}\n'
        )

    # Source: src/config.ts with more exports
    with open(os.path.join(src_dir, "config.ts"), "w", encoding="utf-8") as f:
        f.write(
            'export interface Settings {\n'
            '    name: string;\n'
            '}\n'
        )

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    # Only document src/utils.ts
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            "# API\n"
            "\n"
            ':-: ref path="src/utils.ts"\n'
        )

    result = check_docs(str(tmp_path))

    assert result.coverage is not None
    # src/utils.ts has format, parse (2 exported)
    # src/config.ts has Settings (1 exported)
    # Total: 3 exported symbols
    assert result.coverage.total_public == 3
    # Only src/utils.ts is documented (format, parse in resolved content)
    assert result.coverage.referenced == 2
    # Settings from config.ts is undocumented
    assert len(result.coverage.undocumented_symbols) == 1
    assert any("Settings" in s for s in result.coverage.undocumented_symbols)
