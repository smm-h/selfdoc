"""SPELL001 in ``selfdoc check``, and the corpus sweep over sibling projects.

The engine itself is covered by tests/test_spelling.py.  What is asserted
here is the wiring: that the check reaches documentation pages AND posts,
that an error-severity finding fails the run, that the accept list is
consulted, and that the corpus command runs the same engine over siblings
without writing to them.
"""

from __future__ import annotations

import json
import os

import pytest

from selfdoc.check import check_docs, check_result_exit_code
from selfdoc.spell_corpus import run_spell_corpus, scan_project
from selfdoc_core import spelling
from selfdoc_core.fleet import discover_fleet

from conftest import default_config


@pytest.fixture(autouse=True)
def empty_accept_list(monkeypatch, tmp_path):
    """Never read the real machine's accept list from a test.

    The list lives outside every repository, so a suite that read it would
    pass or fail depending on which terms this machine happens to have
    accepted.  Every test here points the engine at a path that does not
    exist, which is the documented "empty list" case.
    """
    monkeypatch.setattr(
        spelling, "ACCEPT_LIST_PATH", tmp_path / "no-accept-list.txt",
    )


def _project(tmp_path, pages, name="project"):
    """A minimal selfdoc project whose docs tree holds *pages*."""
    project_dir = tmp_path / name
    project_dir.mkdir(parents=True, exist_ok=True)
    with open(project_dir / "selfdoc.json", "w", encoding="utf-8") as f:
        json.dump(default_config(docs="docs/", output="docs/_build/"), f)

    src_dir = project_dir / "src"
    src_dir.mkdir(exist_ok=True)
    with open(src_dir / "__init__.py", "w", encoding="utf-8") as f:
        f.write('"""Example package."""\n')

    docs_dir = project_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    for rel, content in pages.items():
        full = docs_dir / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
    return project_dir


_CLEAN_PAGE = (
    "---\ntitle: Home\ndescription: "
    "A page of ordinary prose that says something concrete about the "
    "project and its documentation for the reader.\n---\n\n"
    "# Home\n\nThis page is spelled correctly.\n"
)


def test_a_misspelling_on_a_docs_page_is_reported(tmp_path):
    """The check reaches documentation pages."""
    project = _project(tmp_path, {"index.md": _CLEAN_PAGE.replace(
        "spelled correctly", "spelled correclty",
    )})
    result = check_docs(str(project))
    spell = [lint for lint in result.lints if lint.code == "SPELL001"]
    assert len(spell) == 1
    assert "correclty" in spell[0].message
    assert spell[0].file == "index.md"


def test_the_reported_line_is_the_file_line(tmp_path):
    """Frontmatter is stripped before scanning; reported lines are not."""
    project = _project(tmp_path, {"index.md": _CLEAN_PAGE.replace(
        "spelled correctly", "spelled correclty",
    )})
    result = check_docs(str(project))
    spell = [lint for lint in result.lints if lint.code == "SPELL001"][0]
    with open(project / "docs" / "index.md", encoding="utf-8") as f:
        lines = f.read().split("\n")
    assert "correclty" in lines[spell.line - 1]


def test_a_misspelling_fails_the_check(tmp_path):
    """SPELL001 is error severity, so a run carrying one does not pass."""
    project = _project(tmp_path, {"index.md": _CLEAN_PAGE.replace(
        "spelled correctly", "spelled correclty",
    )})
    result = check_docs(str(project))
    assert check_result_exit_code(result) == 1


def test_clean_prose_produces_no_spelling_lint(tmp_path):
    """A correctly spelled page is silent."""
    project = _project(tmp_path, {"index.md": _CLEAN_PAGE})
    result = check_docs(str(project))
    assert [lint for lint in result.lints if lint.code == "SPELL001"] == []


def test_code_blocks_on_a_page_are_not_flagged(tmp_path):
    """A documented command is not prose and must not fail a project's check."""
    page = _CLEAN_PAGE + "\n```bash\nteh recieve --seperate\n```\n"
    project = _project(tmp_path, {"index.md": page})
    result = check_docs(str(project))
    assert [lint for lint in result.lints if lint.code == "SPELL001"] == []


def test_the_accept_list_silences_a_genuine_term(tmp_path, monkeypatch):
    """A term on the shared list is accepted everywhere, permanently."""
    accept = tmp_path / "accept.txt"
    accept.write_text("# genuine terms\nrlsbl\n", encoding="utf-8")
    monkeypatch.setattr(spelling, "ACCEPT_LIST_PATH", accept)

    page = _CLEAN_PAGE.replace("spelled correctly", "released with rlsbl")
    project = _project(tmp_path, {"index.md": page})
    result = check_docs(str(project))
    assert [lint for lint in result.lints if lint.code == "SPELL001"] == []


def test_a_malformed_accept_list_stops_the_check(tmp_path, monkeypatch):
    """The run stops on the bad list rather than judging pages against it."""
    accept = tmp_path / "accept.txt"
    accept.write_text("two words\n", encoding="utf-8")
    monkeypatch.setattr(spelling, "ACCEPT_LIST_PATH", accept)

    project = _project(tmp_path, {"index.md": _CLEAN_PAGE})
    with pytest.raises(RuntimeError):
        check_docs(str(project))


def test_posts_are_spell_checked_too(tmp_path):
    """A post is a page on the site and is held to the same standard."""
    project = _project(tmp_path, {"index.md": _CLEAN_PAGE})
    posts_dir = project / ".selfdoc" / "posts"
    posts_dir.mkdir(parents=True)
    with open(posts_dir / "2026-01-01-hello.md", "w", encoding="utf-8") as f:
        f.write(
            "---\ntitle: Hello\ndate: 2026-01-01\ndirectives: false\n"
            "description: An announcement post with enough description text "
            "to satisfy the length rules that every page is held to.\n---\n\n"
            "The post body has a recieve typo in it.\n"
        )

    result = check_docs(str(project))
    spell = [lint for lint in result.lints if lint.code == "SPELL001"]
    assert len(spell) == 1
    assert "recieve" in spell[0].message
    assert spell[0].file.endswith("2026-01-01-hello.md")


# -- Content a directive rendered ---------------------------------------------


CV_DOCUMENT = """
format_version = 1

[identity]
name = "Ada Lovelace"
headline = "Analyst"
location = "London, England"
email = "ada@example.org"
summary = "I write notes about engines."

[[skills]]
category = "Languages"
items = ["French"]

[[projects]]
name = "Note G"
notes = ["The first published algorithm"]

[[interests]]
title = "Poetical science"
body = "Imagination is the discovering faculty."

[[education]]
degree = "Private tuition in mathematics"
years = "1833 - 1840"
institute = "University of London"
location = "London, England"

[[experience]]
role = "Translator"
period = "1842"
company = "Scientific Memoirs"
location = "London, England"

[[languages]]
name = "English"
level = "Native"

[contact]
body = "Write to ada@example.org."
"""

_CV_PAGE = (
    "---\ntitle: CV\ntype: cv\ndescription: "
    "The curriculum vitae of Ada Lovelace, analyst, with her skills, "
    "projects, interests, education, work and languages.\n---\n\n"
    ':-: cv path="docs/cv.toml"\n'
)


def _cv_project(tmp_path, document):
    project = _project(tmp_path, {"cv.md": _CV_PAGE})
    with open(project / "docs" / "cv.toml", "w", encoding="utf-8") as f:
        f.write(document)
    return project


def test_a_misspelling_in_the_cv_document_is_reported(tmp_path):
    """CV prose lives in TOML, and TOML is where the typo has to be named.

    The page carries a directive marker where the reader sees a whole CV,
    so nothing on the page was ever scanned and the document behind it was
    never reached at all.
    """
    document = CV_DOCUMENT.replace(
        "Imagination is the discovering faculty.",
        "Imagination is the discovring faculty.",
    )
    project = _cv_project(tmp_path, document)
    result = check_docs(str(project))
    spell = [lint for lint in result.lints if lint.code == "SPELL001"]
    assert len(spell) == 1
    assert "discovring" in spell[0].message


def test_the_cv_misspelling_is_located_in_the_source_document(tmp_path):
    """The diagnostic names cv.toml and the line the word is written on."""
    document = CV_DOCUMENT.replace(
        "Imagination is the discovering faculty.",
        "Imagination is the discovring faculty.",
    )
    project = _cv_project(tmp_path, document)
    result = check_docs(str(project))
    spell = [lint for lint in result.lints if lint.code == "SPELL001"][0]
    assert spell.file == "docs/cv.toml"
    with open(project / "docs" / "cv.toml", encoding="utf-8") as f:
        lines = f.read().split("\n")
    assert "discovring" in lines[spell.line - 1]
    assert "cv.md" in spell.message


def test_a_misspelling_in_the_cv_document_fails_the_check(tmp_path):
    document = CV_DOCUMENT.replace("Analyst", "Analsyt")
    project = _cv_project(tmp_path, document)
    result = check_docs(str(project))
    assert check_result_exit_code(result) == 1


def test_a_clean_cv_document_produces_no_spelling_lint(tmp_path):
    project = _cv_project(tmp_path, CV_DOCUMENT)
    result = check_docs(str(project))
    assert [lint for lint in result.lints if lint.code == "SPELL001"] == []


def test_a_document_is_reported_once_however_it_was_found(tmp_path):
    """The docs walk and the directive's own `path` name the same file."""
    document = CV_DOCUMENT.replace("Analyst", "Analsyt")
    project = _cv_project(tmp_path, document)
    result = check_docs(str(project))
    spell = [lint for lint in result.lints if lint.code == "SPELL001"]
    assert len(spell) == 1


def test_a_copy_of_the_document_in_the_build_output_is_not_reported(tmp_path):
    """A generated copy is overwritten by the next build; it is not a source."""
    document = CV_DOCUMENT.replace("Analyst", "Analsyt")
    project = _cv_project(tmp_path, document)
    build_dir = project / "docs" / "_build"
    build_dir.mkdir(parents=True, exist_ok=True)
    with open(build_dir / "cv.toml", "w", encoding="utf-8") as f:
        f.write(document)

    result = check_docs(str(project))
    spell = [lint for lint in result.lints if lint.code == "SPELL001"]
    assert [lint.file for lint in spell] == ["docs/cv.toml"]


def test_a_symbol_name_a_directive_extracted_is_not_a_misspelling(tmp_path):
    """A `ref` renders identifiers out of source; those are not prose.

    The file to fix would be code, and the word is a name rather than
    something anyone spelled wrong, so it is not this check's finding.
    """
    page = (
        "---\ntitle: API\ndescription: "
        "The API reference for this project's one example package, listing "
        "every public symbol it exports for callers to use.\n---\n\n"
        "# API\n\n"
        ':-: ref path="src"\n'
    )
    project = _project(tmp_path, {"api.md": page})
    with open(project / "docs" / "notes.toml", "w", encoding="utf-8") as f:
        f.write('# an authored document that holds none of those names\n')
    result = check_docs(str(project))
    assert [lint for lint in result.lints if lint.code == "SPELL001"] == []


def test_the_pages_own_prose_is_not_reported_twice(tmp_path):
    """A word the raw scan already found is not re-reported from the render."""
    page = _CV_PAGE.replace(
        ':-: cv path="docs/cv.toml"',
        'The page says recieve.\n\n:-: cv path="docs/cv.toml"',
    )
    project = _project(tmp_path, {"cv.md": page})
    with open(project / "docs" / "cv.toml", "w", encoding="utf-8") as f:
        f.write(CV_DOCUMENT)
    result = check_docs(str(project))
    spell = [lint for lint in result.lints if lint.code == "SPELL001"]
    assert len(spell) == 1
    assert spell[0].file == "cv.md"


# -- The corpus sweep ---------------------------------------------------------


def test_scan_project_reports_per_project_findings(tmp_path):
    """One project's sweep names its pages and its unknown words."""
    _project(tmp_path, {"index.md": _CLEAN_PAGE.replace(
        "spelled correctly", "spelled correclty",
    )}, name="alpha")

    found = discover_fleet(str(tmp_path))
    report = scan_project(found[0], spelling.load_wordlist(), frozenset())
    assert report.pages == 1
    assert [word for word, _count in report.unique_words] == ["correclty"]


def test_scan_project_reports_an_unreadable_project_without_raising(tmp_path):
    """A neighbour that cannot be read is reported, never fatal."""
    broken = tmp_path / "broken"
    broken.mkdir()
    with open(broken / "selfdoc.json", "w", encoding="utf-8") as f:
        f.write("{ not json")

    found = discover_fleet(str(tmp_path))
    report = scan_project(found[0], spelling.load_wordlist(), frozenset())
    assert report.error
    assert report.misspellings == []


def test_corpus_run_exits_nonzero_when_a_word_is_flagged(tmp_path, capsys):
    """A misspelling anywhere in the corpus is a finding, not a note."""
    _project(tmp_path, {"index.md": _CLEAN_PAGE.replace(
        "spelled correctly", "spelled correclty",
    )}, name="alpha")

    assert run_spell_corpus(str(tmp_path)) == 1
    assert "correclty" in capsys.readouterr().out


def test_corpus_run_exits_zero_on_a_clean_sweep(tmp_path, capsys):
    """Nothing flagged is a pass."""
    _project(tmp_path, {"index.md": _CLEAN_PAGE}, name="alpha")
    assert run_spell_corpus(str(tmp_path)) == 0
    assert "total flagged: 0" in capsys.readouterr().out


def test_corpus_json_output_is_machine_readable(tmp_path, capsys):
    """The json format carries every located word for a tool to consume."""
    _project(tmp_path, {"index.md": _CLEAN_PAGE.replace(
        "spelled correctly", "spelled correclty",
    )}, name="alpha")

    run_spell_corpus(str(tmp_path), format="json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 1
    entry = payload["projects"][0]["misspellings"][0]
    assert entry["word"] == "correclty"
    assert entry["file"] == "index.md"
    assert entry["line"] >= 1 and entry["column"] >= 1


def test_corpus_run_writes_nothing_into_the_projects(tmp_path):
    """The sweep is read-only over every project it visits."""
    project = _project(tmp_path, {"index.md": _CLEAN_PAGE}, name="alpha")
    before = {
        os.path.relpath(os.path.join(root, name), project)
        for root, _dirs, files in os.walk(project)
        for name in files
    }

    run_spell_corpus(str(tmp_path))

    after = {
        os.path.relpath(os.path.join(root, name), project)
        for root, _dirs, files in os.walk(project)
        for name in files
    }
    assert after == before
