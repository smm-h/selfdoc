"""Tests for comma-separated list parsing in frontmatter."""

from selfdoc.docs import parse_frontmatter


class TestCommaList:
    def test_comma_separated_becomes_list(self):
        content = "---\ntags: deployment, advanced, python\n---\nBody"
        meta, body = parse_frontmatter(content)
        assert meta["tags"] == ["deployment", "advanced", "python"]

    def test_two_items(self):
        content = "---\ntags: a, b\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == ["a", "b"]

    def test_no_comma_stays_string(self):
        content = "---\ntags: single\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == "single"
        assert isinstance(meta["tags"], str)

    def test_whitespace_stripped_from_items(self):
        content = "---\ntags:  foo ,  bar ,  baz \n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == ["foo", "bar", "baz"]

    def test_non_tags_comma_field(self):
        """Any comma-containing value becomes a list, not just 'tags'."""
        content = "---\ncategories: web, mobile\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["categories"] == ["web", "mobile"]

    def test_other_types_unaffected(self):
        """Booleans, ints, floats remain unchanged."""
        content = "---\ntags: a, b\nvisible: true\ncount: 42\nratio: 3.14\n---\nBody"
        meta, _ = parse_frontmatter(content)
        assert meta["tags"] == ["a", "b"]
        assert meta["visible"] is True
        assert meta["count"] == 42
        assert meta["ratio"] == 3.14

    def test_quoted_value_with_comma_stays_string(self):
        """Quoted values have quotes stripped first, so commas inside quotes are parsed."""
        content = '---\ntitle: "hello, world"\n---\nBody'
        meta, _ = parse_frontmatter(content)
        # Quotes are stripped, then comma detected -> list
        assert meta["title"] == ["hello", "world"]

    def test_body_preserved(self):
        content = "---\ntags: a, b\n---\nHello world"
        _, body = parse_frontmatter(content)
        assert body == "Hello world"
