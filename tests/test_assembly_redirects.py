"""Tests for generate_redirects_file in selfblog.assembly."""

from selfblog.assembly import generate_redirects_file
from selfblog.cli import app


def test_redirects_basic_format():
    result = generate_redirects_file("selfdoc", "https://docs.smmh.dev")
    assert result == "/* https://docs.smmh.dev/selfdoc/:splat 301\n"


def test_redirects_trailing_slash_stripped():
    with_slash = generate_redirects_file("selfdoc", "https://docs.smmh.dev/")
    without_slash = generate_redirects_file("selfdoc", "https://docs.smmh.dev")
    assert with_slash == without_slash


def test_redirects_various_slugs():
    for slug in ("selfdoc", "my-project", "a"):
        result = generate_redirects_file(slug, "https://docs.smmh.dev")
        assert f"/{slug}/:splat" in result


def test_redirects_various_bases():
    for base in ("https://docs.smmh.dev", "http://localhost:8080", "https://example.com/docs"):
        result = generate_redirects_file("proj", base)
        assert result.startswith("/* ")
        assert base.rstrip("/") in result


def test_redirects_ends_with_newline():
    result = generate_redirects_file("proj", "https://docs.smmh.dev")
    assert result.endswith("\n")
    assert not result.endswith("\n\n")


def test_redirects_single_line():
    result = generate_redirects_file("proj", "https://docs.smmh.dev")
    lines = result.splitlines()
    assert len(lines) == 1


def test_redirects_has_splat():
    result = generate_redirects_file("proj", "https://docs.smmh.dev")
    assert ":splat" in result


def test_redirects_has_301():
    result = generate_redirects_file("proj", "https://docs.smmh.dev")
    assert "301" in result


def test_redirects_wildcard_pattern():
    result = generate_redirects_file("proj", "https://docs.smmh.dev")
    assert result.startswith("/*")


# -- CLI surface -------------------------------------------------------------


def test_cli_redirects_accepts_kebab_docs_base(capsys):
    """The flag is spelled --docs-base, like every sibling assembly flag."""
    result = app.test(
        ["assembly", "redirects", "--slug", "proj",
         "--docs-base", "https://docs.smmh.dev"],
    )
    assert result.exit_code == 0
    assert "/* https://docs.smmh.dev/proj/:splat 301" in result.stdout


def test_cli_redirects_rejects_underscore_docs_base():
    """--docs_base is not a flag: strictcli flags are kebab-case."""
    result = app.test(
        ["assembly", "redirects", "--slug", "proj",
         "--docs_base", "https://docs.smmh.dev"],
    )
    assert result.exit_code != 0


def test_cli_redirects_missing_docs_base_names_the_real_flag():
    result = app.test(["assembly", "redirects", "--slug", "proj"])
    assert result.exit_code != 0
    assert "--docs-base" in result.stderr
