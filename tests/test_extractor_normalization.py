"""Phase 7.1 -- extractor prose normalization.

Language extractors join soft-wrapped lines within paragraphs at extraction
time so a first sentence that spans several physical lines (Go/JSDoc/KDoc
comments wrap at ~75 cols) is emitted as one complete unit, while embedded
code blocks are left verbatim.
"""

import os

from selfdoc_core.extractors.base import _format_docstring
from selfdoc_core.extractors.go import GoExtractor
from selfdoc_core.extractors.python import PythonExtractor
from selfdoc_core.prose import first_sentence


# Canonical Go fixture: the real wrapped package comment of saferm's config-ish
# metadata package (internal/meta), whose wrapped first sentence produced a
# broken llms.txt bullet. Text copied here so the test does not depend on the
# other repo at runtime. An indented preformatted example block is appended to
# exercise the code-block-verbatim rule.
_SAFERM_META_GO = """\
// Package meta collects rich metadata about each deletion: environment
// variables, git repository context, parent process information, and
// arbitrary user-supplied key-value pairs.
//
// Example usage:
//
//\tm := meta.Collect()
//\tfmt.Println(m.GitBranch)
package meta

func Collect() {}
"""

_EXPECTED_META_SENTENCE = (
    "Package meta collects rich metadata about each deletion: environment "
    "variables, git repository context, parent process information, and "
    "arbitrary user-supplied key-value pairs."
)


class TestGoNormalization:
    def test_wrapped_first_sentence_joined(self, tmp_path):
        go_file = tmp_path / "meta.go"
        go_file.write_text(_SAFERM_META_GO)
        extractor = GoExtractor()
        doc = extractor.module_docstring(str(go_file))
        # The wrapped first sentence is now one line -> first_sentence works.
        assert first_sentence(doc) == _EXPECTED_META_SENTENCE

    def test_embedded_code_block_left_verbatim(self, tmp_path):
        go_file = tmp_path / "meta.go"
        go_file.write_text(_SAFERM_META_GO)
        extractor = GoExtractor()
        doc = extractor.module_docstring(str(go_file))
        # The indented preformatted example lines are preserved verbatim
        # (indentation is the Go code-block signal).
        assert "\tm := meta.Collect()" in doc
        assert "\tfmt.Println(m.GitBranch)" in doc
        # And they are NOT collapsed into the prose paragraph.
        assert "m := meta.Collect() fmt.Println" not in doc


_PY_MODULE = '''\
"""Loads and validates the tool configuration from disk, applying
defaults and reporting any errors clearly to the caller.

Example:

    cfg = load()
    print(cfg.value)
"""

def load():
    pass
'''

_EXPECTED_PY_SENTENCE = (
    "Loads and validates the tool configuration from disk, applying "
    "defaults and reporting any errors clearly to the caller."
)


class TestPythonNormalization:
    def test_wrapped_first_sentence_joined(self, tmp_path):
        py_file = tmp_path / "config.py"
        py_file.write_text(_PY_MODULE)
        extractor = PythonExtractor()
        doc = extractor.module_docstring(str(py_file))
        assert first_sentence(doc) == _EXPECTED_PY_SENTENCE

    def test_embedded_code_block_left_verbatim(self, tmp_path):
        py_file = tmp_path / "config.py"
        py_file.write_text(_PY_MODULE)
        extractor = PythonExtractor()
        doc = extractor.module_docstring(str(py_file))
        assert "    cfg = load()" in doc
        assert "    print(cfg.value)" in doc


class TestFormatDocstringNormalization:
    def test_wrapped_prose_joined_but_code_block_preserved(self):
        raw = (
            "Manages configuration loading for the whole\n"
            "application, resolving defaults and env overrides.\n"
            "\n"
            "    run()\n"
            "    done()\n"
        )
        out = _format_docstring(raw, 2)
        assert (
            "Manages configuration loading for the whole application, "
            "resolving defaults and env overrides." in out
        )
        assert "    run()\n    done()" in out

    def test_blank_line_paragraph_breaks_preserved(self):
        raw = "First paragraph\nwrapped line.\n\nSecond paragraph\nwrapped."
        out = _format_docstring(raw, 2)
        assert "First paragraph wrapped line." in out
        assert "Second paragraph wrapped." in out

    def test_a_heading_is_not_joined_into_the_line_below_it(self):
        """A heading ends the paragraph above and opens nothing.

        Joined to the sentence under it, the sentence becomes part of the
        heading -- and Go's doc convention writes exactly that shape when
        a section has no blank line after its title.
        """
        out = _format_docstring("# Usage\nCall it.\n", 2)
        assert "### Usage" in out
        assert "### Usage Call it." not in out

    def test_headings_are_renested_under_the_emitting_heading(self):
        """A doc comment writes as if it owned the document; on a reference
        page it is a subsection, and the page already has its one H1."""
        raw = "Intro.\n\n# Usage\n\nHow.\n\n## Detail\n\nMore.\n"
        out = _format_docstring(raw, 3)
        assert "#### Usage" in out
        assert "##### Detail" in out
        assert "\n# " not in out
        assert not out.startswith("# ")

    def test_a_heading_inside_a_fence_is_content(self):
        raw = "Intro.\n\n```\n# not a heading\n```\n\n# Usage\n\nHow.\n"
        out = _format_docstring(raw, 2)
        assert "# not a heading" in out
        assert "### Usage" in out

    def test_a_doc_already_nested_deeply_enough_is_left_alone(self):
        raw = "Intro.\n\n#### Deep\n\nText.\n"
        out = _format_docstring(raw, 2)
        assert "#### Deep" in out
        assert "##### Deep" not in out
