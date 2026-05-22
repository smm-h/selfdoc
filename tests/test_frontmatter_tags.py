"""Tests for bracket-delimited list parsing in frontmatter."""

from selfdoc.docs import parse_frontmatter


class TestBracketList:
    def test_bracket_list_becomes_list(self):
        content = "---\ntags: [deployment, advanced, python]\n---\nBody"
        meta, body = parse_frontmatter(content)
        assert meta["tags"] == ["deployment", "advanced", "python"]

    def test_two_items(self):
        content = "---\ntags: [a, b]\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == ["a", "b"]

    def test_no_brackets_stays_string(self):
        content = "---\ntags: single\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == "single"
        assert isinstance(meta["tags"], str)

    def test_whitespace_stripped_from_items(self):
        content = "---\ntags: [ foo ,  bar ,  baz ]\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == ["foo", "bar", "baz"]

    def test_non_tags_bracket_field(self):
        """Any bracket-delimited value becomes a list, not just 'tags'."""
        content = "---\ncategories: [web, mobile]\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["categories"] == ["web", "mobile"]

    def test_other_types_unaffected(self):
        """Booleans, ints, floats remain unchanged."""
        content = "---\ntags: [a, b]\nvisible: true\ncount: 42\nratio: 3.14\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == ["a", "b"]
        assert meta["visible"] is True
        assert meta["count"] == 42
        assert meta["ratio"] == 3.14

    def test_quoted_value_with_comma_stays_string(self):
        """Quoted values with commas stay as strings (no bracket syntax)."""
        content = '---\ntitle: "hello, world"\n---\nBody'
        meta, _ = parse_frontmatter(content)
        assert meta["title"] == "hello, world"
        assert isinstance(meta["title"], str)

    def test_unquoted_value_with_comma_stays_string(self):
        """Unquoted values with commas stay as strings (no bracket syntax)."""
        content = "---\ndescription: Build sites from Markdown, source code, and config\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["description"] == "Build sites from Markdown, source code, and config"
        assert isinstance(meta["description"], str)

    def test_body_preserved(self):
        content = "---\ntags: [a, b]\n---\nHello world"
        _, body = parse_frontmatter(content)
        assert body == "Hello world"

    def test_empty_bracket_list(self):
        """Empty brackets produce an empty list."""
        content = "---\ntags: []\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == []

    def test_single_item_bracket_list(self):
        """Single item in brackets becomes a one-element list."""
        content = "---\ntags: [python]\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == ["python"]
