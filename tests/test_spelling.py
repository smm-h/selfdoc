"""The spelling engine, its vendored word list, and its accept list.

One engine serves ``selfdoc check`` (SPELL001) and ``selfdoc spell-corpus``,
so everything asserted here holds for both.  The tests are grouped by the
three things that can independently be wrong: what the word list contains
and whether it ships legally, how the accept list is read, and what the
scanner does and does not treat as a word.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from selfdoc_core import spelling
from selfdoc_core.spelling import (
    AcceptListError,
    check_text,
    iter_unknown_words,
    load_accept_list,
    load_wordlist,
    suggestions_for,
    wordlist_copyright,
    wordlist_source,
)


@pytest.fixture(scope="module")
def vocab():
    """The vendored word list, loaded once for the module."""
    return load_wordlist()


# -- The vendored word list ---------------------------------------------------


def test_wordlist_is_mid_sized(vocab):
    """Big enough not to flag ordinary English, small enough to mean something."""
    assert 100_000 < len(vocab) < 300_000


@pytest.mark.parametrize("word", [
    "the", "documentation", "subdirectory", "configure", "release",
    "colour", "behaviour", "analyse", "analyze", "runtime", "metadata",
])
def test_ordinary_words_are_known(vocab, word):
    """Ordinary English, in US and British spelling alike, is accepted."""
    assert word in vocab


@pytest.mark.parametrize("word", [
    "teh", "recieve", "seperate", "occured", "definately", "neccessary",
    "adress", "existance", "reponse", "paramter",
])
def test_common_misspellings_are_unknown(vocab, word):
    """The list is an acceptance oracle, not a scrape: typos are absent."""
    assert word not in vocab


def test_source_record_matches_the_vendored_words():
    """SOURCE.json's digest and count describe the words.txt actually shipped."""
    record = wordlist_source()
    from importlib.resources import files

    blob = files("selfdoc_core").joinpath("wordlist", "words.txt").read_text(
        encoding="utf-8",
    )
    assert record["word_count"] == len([ln for ln in blob.split("\n") if ln])
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    assert record["words_sha256"] == digest


def test_source_record_names_its_retrieval_method():
    """The vendoring is reproducible: URL, parameters and script are recorded."""
    record = wordlist_source()
    assert record["generator_url"].endswith("app.aspell.net/create")
    assert ["max_size", "70"] in record["generator_params"]
    assert record["regenerate_with"] == "python scripts/regen_wordlist.py"
    assert record["esdb_git_revision"]


def test_upstream_copyright_ships_with_the_words():
    """Redistribution is conditioned on the notice travelling with the data."""
    notice = wordlist_copyright()
    assert "Kevin Atkinson" in notice
    assert "Permission to use, copy, modify, distribute" in notice


def test_sub_source_notice_is_included_verbatim():
    """UKACD's own terms require its notice be displayed and included verbatim."""
    notice = wordlist_copyright()
    assert "UK Advanced Cryptics Dictionary" in notice
    assert "J Ross Beresford" in notice
    assert "prominently displayed" in notice


def test_module_docstring_records_the_obligations():
    """The obligations are recorded where a maintainer will read them."""
    doc = spelling.__doc__
    assert "COPYRIGHT.txt" in doc
    assert "UK Advanced Cryptics Dictionary" in doc


# -- The accept list ----------------------------------------------------------


def test_accept_list_path_is_the_fixed_shared_location():
    """One list, outside every repo, shared by every project on the machine."""
    assert spelling.ACCEPT_LIST_PATH.name == "spelling-accept.txt"
    assert spelling.ACCEPT_LIST_PATH.parent.name == "ark"


def test_missing_accept_list_is_an_empty_list(tmp_path):
    """A fresh machine has accepted nothing yet -- absence, not an error."""
    assert load_accept_list(tmp_path / "nope.txt") == frozenset()


def test_accept_list_reads_words_and_comments(tmp_path):
    """One word per line; '#' starts a comment, whole-line or trailing."""
    path = tmp_path / "accept.txt"
    path.write_text(
        "# project names\n"
        "selfdoc\n"
        "\n"
        "rlsbl  # the release orchestrator\n",
        encoding="utf-8",
    )
    assert load_accept_list(path) == frozenset({"selfdoc", "rlsbl"})


@pytest.mark.parametrize("line", [
    "two words",
    "selfdoc-core",
    "utf8",
    "config.json",
])
def test_malformed_accept_line_is_a_hard_error(tmp_path, line):
    """A line the format cannot admit stops the run rather than being dropped."""
    path = tmp_path / "accept.txt"
    path.write_text(f"selfdoc\n{line}\n", encoding="utf-8")
    with pytest.raises(AcceptListError) as excinfo:
        load_accept_list(path)
    assert ":2:" in str(excinfo.value)


def test_accept_list_error_is_a_runtime_error(tmp_path):
    """The CLI's existing RuntimeError handler surfaces it cleanly."""
    path = tmp_path / "accept.txt"
    path.write_text("not a word\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        load_accept_list(path)


def test_accepted_term_is_accepted_in_any_standard_casing(vocab):
    """An accepted term is accepted everywhere, however the sentence cases it."""
    accepted = frozenset({"selfdoc"})
    text = "selfdoc and Selfdoc and SELFDOC.\n"
    assert check_text(text, file="p.md", vocab=vocab, accepted=accepted) == []


# -- What counts as a word ----------------------------------------------------


def _words(text, vocab, accepted=frozenset()):
    """Unknown words found in *text*, as plain strings."""
    return [m.word for m in check_text(
        text, file="p.md", vocab=vocab, accepted=accepted, suggest=False,
    )]


def test_fenced_code_blocks_are_not_scanned(vocab):
    """Structure comes from the tokenizer, so code is excluded by construction."""
    text = "```python\nteh = recieve\n```\n"
    assert _words(text, vocab) == []


def test_directive_blocks_are_not_scanned(vocab):
    """A ':::' directive block is its own token and carries no prose."""
    text = ":::note teh\nrecieve\n:::\n"
    assert _words(text, vocab) == []


def test_inline_code_spans_are_not_scanned(vocab):
    """Backtick spans are blanked before the line is scanned."""
    text = "Prose with `teh recieve` inside it.\n"
    assert _words(text, vocab) == []


def test_inline_directive_markers_are_not_scanned(vocab):
    """An inline ':-:' marker and its attributes are syntax, not prose."""
    text = 'Before :-: ref target="teh" after.\n'
    assert _words(text, vocab) == []


@pytest.mark.parametrize("text", [
    "See https://example.com/seperate for more.\n",
    "Mail <someone@example.com> about it.\n",
    "A [link](https://example.com/recieve) here.\n",
    "Write to mailto:teh@example.com now.\n",
])
def test_urls_are_not_scanned(vocab, text):
    """A URL is an address, not prose; its path segments are not words."""
    assert _words(text, vocab) == []


@pytest.mark.parametrize("chunk", [
    "max_size", "os.path", "std::vector", "v0.36.0", "utf8",
    "docs/check-guide.md", "~/Projects", "user@host",
])
def test_identifier_shaped_tokens_are_skipped(vocab, chunk):
    """A machine token is skipped whole -- its letters are not English."""
    assert _words(f"Prose about {chunk} here.\n", vocab) == []


def test_camel_case_is_treated_as_an_identifier(vocab):
    """An unbackticked symbol name is not a spelling mistake to report."""
    assert _words("The LintResult and parseFrontmatter values.\n", vocab) == []


def test_headings_are_scanned(vocab):
    """Page titles used to escape every prose rule; they no longer do."""
    assert _words("## A heading with teh typo\n", vocab) == ["teh"]


def test_table_cells_are_scanned(vocab):
    """Table cells used to escape every prose rule; they no longer do."""
    text = (
        "| Column | Notes |\n"
        "| --- | --- |\n"
        "| a cell | with adress |\n"
    )
    assert _words(text, vocab) == ["adress"]


@pytest.mark.parametrize("text,expected", [
    ("- item with occured\n", ["occured"]),
    ("1. item with occured\n", ["occured"]),
    ("> quoted with occured\n", ["occured"]),
    ("Term\n: definition with occured\n", ["occured"]),
])
def test_every_prose_token_type_is_scanned(vocab, text, expected):
    """Lists, blockquotes and definition lists carry prose and are checked."""
    assert _words(text, vocab) == expected


def test_hyphenated_compounds_are_checked_part_by_part(vocab):
    """Each part is checked honestly; only the bad part is reported."""
    found = check_text(
        "A well-knwon compound.\n", file="p.md", vocab=vocab,
        accepted=frozenset(), suggest=False,
    )
    assert [m.word for m in found] == ["knwon"]


def test_possessive_of_a_known_word_is_accepted(vocab):
    """Possessives are handled rather than flagged as unknown forms."""
    assert _words("The tokenizer's output and the parsers' outputs.\n", vocab) == []


def test_capitalized_sentence_start_is_accepted(vocab):
    """Lowercase matching covers a capitalized ordinary word."""
    assert _words("Documentation is generated.\n", vocab) == []


def test_all_caps_heading_is_accepted(vocab):
    """An all-caps heading matches the ordinary lowercase entry."""
    assert _words("# GETTING STARTED\n", vocab) == []


def test_single_letters_are_never_reported(vocab):
    """A lone letter is an enumeration marker or an initial."""
    assert _words("a b c point x of y\n", vocab) == []


# -- Location and suggestions -------------------------------------------------


def test_line_and_column_point_at_the_word(vocab):
    """A diagnostic names a position a reader can open the file at."""
    text = "First line.\n\nSecond has recieve in it.\n"
    found = check_text(text, file="p.md", vocab=vocab, accepted=frozenset())
    assert len(found) == 1
    miss = found[0]
    assert miss.line == 3
    line = text.split("\n")[miss.line - 1]
    assert line[miss.column - 1:miss.column - 1 + len(miss.word)] == "recieve"


def test_columns_survive_a_masked_code_span(vocab):
    """Masking keeps the line's length, so a later column is still true."""
    text = "Use `--flag --other` then recieve it.\n"
    found = check_text(text, file="p.md", vocab=vocab, accepted=frozenset())
    assert len(found) == 1
    miss = found[0]
    assert text.split("\n")[0][miss.column - 1:].startswith("recieve")


def test_line_offset_accounts_for_frontmatter(vocab):
    """The body is scanned, but reported lines are the file's own."""
    found = check_text(
        "Body with recieve.\n", file="p.md", vocab=vocab,
        accepted=frozenset(), line_offset=4,
    )
    assert found[0].line == 5


def test_file_is_reported_verbatim(vocab):
    """Diagnostics name the path the caller gave, unchanged."""
    found = check_text(
        "recieve\n", file="posts/2026-01-01-x.md", vocab=vocab,
        accepted=frozenset(),
    )
    assert found[0].file == "posts/2026-01-01-x.md"


def test_suggestion_is_offered_for_a_one_edit_typo(vocab):
    """Edit distance one is cheap and right often enough to be worth printing."""
    assert "occurred" in suggestions_for("occured", vocab)


def test_no_suggestion_rather_than_a_wrong_one(vocab):
    """A word with no near neighbour gets no suggestion at all."""
    assert suggestions_for("zzzqqqxxvv", vocab) == ()


def test_describe_names_word_column_and_suggestions(vocab):
    """The lint message carries everything the engine located."""
    found = check_text("recieve\n", file="p.md", vocab=vocab, accepted=frozenset())
    message = found[0].describe()
    assert "recieve" in message
    assert "col 1" in message
    assert "receive" in message


def test_iter_unknown_words_reports_zero_based_columns(vocab):
    """The line-level primitive returns raw offsets; check_text adds the 1."""
    assert iter_unknown_words("recieve", vocab) == [(0, "recieve")]


# -- The lint registration ----------------------------------------------------


def test_spell001_is_registered_as_an_error():
    """Misspellings block; the accept list is the sanctioned response."""
    from selfdoc_core.lints import LINT_REGISTRY

    assert LINT_REGISTRY["SPELL001"].severity == "error"


def test_spell001_is_in_the_check_output_schema():
    """The JSON output schema's enum admits the code the check can emit."""
    import os

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(
        os.path.join(repo_root, "schemas", "check-output.schema.json"),
        encoding="utf-8",
    ) as f:
        schema = json.load(f)
    codes = schema["properties"]["lints"]["items"]["properties"]["code"]["enum"]
    assert "SPELL001" in codes
