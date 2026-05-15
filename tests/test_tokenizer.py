"""Tests for selfdoc.tokenizer -- standalone Markdown block tokenizer."""

from selfdoc.tokenizer import (
    BlankLine,
    Blockquote,
    CodeBlock,
    DefinitionList,
    Directive,
    Heading,
    OrderedList,
    Paragraph,
    Table,
    ThematicBreak,
    UnorderedList,
    tokenize,
)


# ---------------------------------------------------------------------------
# Individual block types
# ---------------------------------------------------------------------------

class TestCodeBlock:
    def test_basic(self):
        tokens = tokenize("```python\nprint('hi')\n```")
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, CodeBlock)
        assert t.lang == "python"
        assert t.lines == ["print('hi')"]
        assert t.annotations == {}
        assert t.start == 1
        assert t.end == 3

    def test_no_language(self):
        tokens = tokenize("```\nfoo\n```")
        assert tokens[0].lang == ""

    def test_with_annotations(self):
        md = "```js\nlet x = 1; // [1]\n```\n[1]: assign x"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, CodeBlock)
        assert t.annotations == {"1": "assign x"}
        assert t.lines == ["let x = 1; // [1]"]
        assert t.start == 1
        assert t.end == 4

    def test_comment_inside_code_block_is_not_heading(self):
        """# comment inside a fenced code block is CodeBlock content, NOT a
        Heading -- this is THE critical test."""
        md = "```python\n# this is a comment\nprint('hello')\n```"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, CodeBlock)
        assert t.lines == ["# this is a comment", "print('hello')"]

    def test_consecutive_code_blocks(self):
        md = "```py\na\n```\n```js\nb\n```"
        tokens = tokenize(md)
        assert len(tokens) == 2
        assert isinstance(tokens[0], CodeBlock)
        assert isinstance(tokens[1], CodeBlock)
        assert tokens[0].lang == "py"
        assert tokens[1].lang == "js"
        assert tokens[0].end == 3
        assert tokens[1].start == 4
        assert tokens[1].end == 6


class TestHeading:
    def test_h1(self):
        tokens = tokenize("# Title")
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, Heading)
        assert t.level == 1
        assert t.text == "Title"
        assert t.start == 1
        assert t.end == 1

    def test_h3(self):
        tokens = tokenize("### Sub-sub")
        t = tokens[0]
        assert t.level == 3
        assert t.text == "Sub-sub"

    def test_h6(self):
        tokens = tokenize("###### Deep")
        t = tokens[0]
        assert t.level == 6


class TestTable:
    def test_basic(self):
        md = "| A | B |\n| --- | --- |\n| 1 | 2 |"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, Table)
        assert len(t.rows) == 3
        assert t.start == 1
        assert t.end == 3


class TestUnorderedList:
    def test_dash(self):
        md = "- alpha\n- beta"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, UnorderedList)
        assert t.items == ["alpha", "beta"]
        assert t.start == 1
        assert t.end == 2

    def test_star(self):
        md = "* one\n* two\n* three"
        tokens = tokenize(md)
        t = tokens[0]
        assert isinstance(t, UnorderedList)
        assert t.items == ["one", "two", "three"]


class TestOrderedList:
    def test_basic(self):
        md = "1. first\n2. second\n3. third"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, OrderedList)
        assert t.items == ["first", "second", "third"]
        assert t.start == 1
        assert t.end == 3


class TestBlockquote:
    def test_plain(self):
        md = "> hello\n> world"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, Blockquote)
        assert t.lines == ["hello", "world"]
        assert t.admonition_type is None
        assert t.start == 1
        assert t.end == 2

    def test_admonition(self):
        md = "> [!WARNING]\n> Be careful"
        tokens = tokenize(md)
        t = tokens[0]
        assert isinstance(t, Blockquote)
        assert t.admonition_type == "WARNING"
        assert t.lines == ["[!WARNING]", "Be careful"]

    def test_custom_admonition(self):
        md = "> [!DANGER]\n> watch out"
        tokens = tokenize(md)
        t = tokens[0]
        assert t.admonition_type == "DANGER"


class TestDefinitionList:
    def test_single(self):
        md = "Term\n: Definition"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, DefinitionList)
        assert t.entries == [("Term", ["Definition"])]
        assert t.start == 1
        assert t.end == 2

    def test_multiple_definitions_per_term(self):
        md = "Word\n: Meaning one\n: Meaning two"
        tokens = tokenize(md)
        t = tokens[0]
        assert isinstance(t, DefinitionList)
        assert t.entries == [("Word", ["Meaning one", "Meaning two"])]

    def test_multiple_terms(self):
        md = "Alpha\n: First letter\n\nBeta\n: Second letter"
        tokens = tokenize(md)
        t = tokens[0]
        assert isinstance(t, DefinitionList)
        assert len(t.entries) == 2
        assert t.entries[0] == ("Alpha", ["First letter"])
        assert t.entries[1] == ("Beta", ["Second letter"])


class TestThematicBreak:
    def test_dashes(self):
        tokens = tokenize("---")
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, ThematicBreak)
        assert t.start == 1
        assert t.end == 1

    def test_stars(self):
        tokens = tokenize("***")
        assert isinstance(tokens[0], ThematicBreak)

    def test_underscores(self):
        tokens = tokenize("___")
        assert isinstance(tokens[0], ThematicBreak)

    def test_long(self):
        tokens = tokenize("----------")
        assert isinstance(tokens[0], ThematicBreak)

    def test_not_heading(self):
        """--- is a thematic break, not a heading or paragraph."""
        tokens = tokenize("---")
        assert isinstance(tokens[0], ThematicBreak)


class TestBlankLine:
    def test_basic(self):
        tokens = tokenize("")
        assert len(tokens) == 1
        assert isinstance(tokens[0], BlankLine)
        assert tokens[0].start == 1
        assert tokens[0].end == 1

    def test_whitespace_only(self):
        tokens = tokenize("   ")
        assert isinstance(tokens[0], BlankLine)


class TestParagraph:
    def test_basic(self):
        md = "Hello world\nthis is a paragraph"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, Paragraph)
        assert t.lines == ["Hello world", "this is a paragraph"]
        assert t.start == 1
        assert t.end == 2

    def test_stops_before_definition_list(self):
        md = "Some intro text\nTerm\n: Definition"
        tokens = tokenize(md)
        # "Some intro text" is a paragraph, then "Term / : Definition" is a
        # definition list
        assert isinstance(tokens[0], Paragraph)
        assert tokens[0].lines == ["Some intro text"]
        assert isinstance(tokens[1], DefinitionList)


# ---------------------------------------------------------------------------
# Integration / mixed documents
# ---------------------------------------------------------------------------

class TestMixedDocument:
    def test_all_block_types(self):
        md = "\n".join([
            "# Welcome",
            "",
            "A paragraph of text",
            "spanning two lines.",
            "",
            "---",
            "",
            "## Code Example",
            "",
            "```python",
            "# a comment",
            "x = 1",
            "```",
            "",
            "| Col1 | Col2 |",
            "| ---- | ---- |",
            "| a    | b    |",
            "",
            "- item one",
            "- item two",
            "",
            "1. first",
            "2. second",
            "",
            "> [!NOTE]",
            "> Take note",
            "",
            ":::cli my.module",
            ":::",
            "",
            "Term",
            ": Its definition",
        ])
        tokens = tokenize(md)
        types = [type(t).__name__ for t in tokens]
        assert "Heading" in types
        assert "Paragraph" in types
        assert "ThematicBreak" in types
        assert "CodeBlock" in types
        assert "Table" in types
        assert "UnorderedList" in types
        assert "OrderedList" in types
        assert "Blockquote" in types
        assert "Directive" in types
        assert "DefinitionList" in types
        assert "BlankLine" in types

    def test_empty_document(self):
        tokens = tokenize("")
        assert len(tokens) == 1
        assert isinstance(tokens[0], BlankLine)

    def test_only_blank_lines(self):
        tokens = tokenize("\n\n\n")
        assert all(isinstance(t, BlankLine) for t in tokens)
        assert len(tokens) == 4  # 4 lines from 3 newlines


class TestDirective:
    def test_basic(self):
        md = ":::cli rlsbl.commands.release\n:::"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, Directive)
        assert t.name == "cli"
        assert t.arg == "rlsbl.commands.release"
        assert t.body == []
        assert t.start == 1
        assert t.end == 2

    def test_with_body(self):
        md = ":::module mylib.config\nsome body line\nanother line\n:::"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, Directive)
        assert t.name == "module"
        assert t.arg == "mylib.config"
        assert t.body == ["some body line", "another line"]
        assert t.start == 1
        assert t.end == 4

    def test_no_arg(self):
        md = ":::config\n:::"
        tokens = tokenize(md)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, Directive)
        assert t.name == "config"
        assert t.arg == ""
        assert t.body == []

    def test_directive_after_heading(self):
        md = "## Section\n\n:::cli my.module\n:::"
        tokens = tokenize(md)
        types = [type(t).__name__ for t in tokens]
        assert types == ["Heading", "BlankLine", "Directive"]

    def test_directive_between_paragraphs(self):
        md = "Some intro text.\n\n:::module foo\n:::\n\nMore text."
        tokens = tokenize(md)
        types = [type(t).__name__ for t in tokens]
        assert types == ["Paragraph", "BlankLine", "Directive", "BlankLine", "Paragraph"]

    def test_paragraph_stops_before_directive(self):
        """A paragraph must not absorb a directive opening line."""
        md = "Intro paragraph.\n:::cli my.module\n:::"
        tokens = tokenize(md)
        assert isinstance(tokens[0], Paragraph)
        assert tokens[0].lines == ["Intro paragraph."]
        assert isinstance(tokens[1], Directive)
        assert tokens[1].name == "cli"

    def test_directive_not_confused_with_thematic_break(self):
        """:::word is a directive, not a thematic break or paragraph."""
        md = ":::test\n:::"
        tokens = tokenize(md)
        assert len(tokens) == 1
        assert isinstance(tokens[0], Directive)


class TestLineCoverage:
    """Every line must be covered by exactly one token's (start, end) range."""

    def _check_coverage(self, content: str):
        lines = content.split("\n")
        n = len(lines)
        tokens = tokenize(content)
        covered = [False] * (n + 1)  # 1-based
        for t in tokens:
            for line_no in range(t.start, t.end + 1):
                assert not covered[line_no], (
                    f"Line {line_no} covered by multiple tokens"
                )
                covered[line_no] = True
        for line_no in range(1, n + 1):
            assert covered[line_no], (
                f"Line {line_no} not covered by any token"
            )

    def test_simple_document(self):
        self._check_coverage("# Hello\n\nWorld")

    def test_mixed_document(self):
        md = "\n".join([
            "# Title",
            "",
            "Some text.",
            "",
            "```go",
            "// comment",
            "func main() {}",
            "```",
            "[1]: annotation",
            "",
            "---",
            "",
            "| A | B |",
            "| - | - |",
            "",
            "- x",
            "- y",
            "",
            "1. a",
            "2. b",
            "",
            "> quote",
            "",
            ":::cli my.mod",
            ":::",
            "",
            "Term",
            ": def",
        ])
        self._check_coverage(md)

    def test_consecutive_code_blocks(self):
        self._check_coverage("```a\nfoo\n```\n```b\nbar\n```")

    def test_only_blanks(self):
        self._check_coverage("\n\n")

    def test_code_with_heading_inside(self):
        self._check_coverage("```\n# not a heading\n```")

    def test_all_thematic_break_variants(self):
        self._check_coverage("---\n\n***\n\n___")
