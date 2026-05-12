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
                severity="warning",
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
    desc = "Complete API reference for the mylib library covering all public functions, classes, and utilities with detailed usage examples included"
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ntitle: API\ndescription: {desc}\n---\n"
            "# API\n\n:::module mylib\n:::\n"
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
            file="index.md", line=1, directive=":::module foo", status="OK"
        )
    ]

    print_results(result)
    captured = capsys.readouterr()

    assert "warning: [SEO001] index.md:3 - Missing title" in captured.out
    assert "error: [SEO002] guide.md - No description" in captured.out
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
    """SEO001: file with two H1 headings triggers a warning."""
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
    assert seo001[0].severity == "warning"
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
    """SEO006: file without description in frontmatter triggers a warning."""
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
    assert seo006[0].severity == "warning"
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
                file="index.md", line=1, directive=":::module foo", status="OK"
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
                file="index.md", line=1, directive=":::module foo", status="OK"
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
                file="index.md", line=1, directive=":::module foo", status="OK"
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
        f.write("# API\n\n:::module mylib\n:::\n")

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
    """SEO013: page with no H1 heading triggers warning."""
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
    assert seo013[0].severity == "warning"
    assert "No H1" in seo013[0].message


def test_seo013_with_h1_no_warning(lint_project):
    """SEO013: page with an H1 heading does not trigger warning."""
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
