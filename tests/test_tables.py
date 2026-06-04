"""Tests for selfdoc.tables and _parse_table in selfdoc.html."""

import pytest

from selfdoc.tables import render_markdown_table
from selfdoc.html import _parse_table


# -- render_markdown_table: basic tables --------------------------------------


class TestBasicTables:
    """Basic table rendering."""

    def test_two_column_table(self):
        """Two-column table with two rows."""
        result = render_markdown_table(
            ["Name", "Value"],
            [["alpha", "1"], ["beta", "2"]],
        )
        assert result == (
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| alpha | 1 |\n"
            "| beta | 2 |"
        )

    def test_three_column_table(self):
        """Three-column table with one row."""
        result = render_markdown_table(
            ["A", "B", "C"],
            [["x", "y", "z"]],
        )
        assert result == (
            "| A | B | C |\n"
            "| --- | --- | --- |\n"
            "| x | y | z |"
        )

    def test_single_column_table(self):
        """Single-column table."""
        result = render_markdown_table(
            ["Item"],
            [["one"], ["two"]],
        )
        assert result == (
            "| Item |\n"
            "| --- |\n"
            "| one |\n"
            "| two |"
        )

    def test_single_row_table(self):
        """Table with exactly one data row."""
        result = render_markdown_table(
            ["X", "Y"],
            [["a", "b"]],
        )
        lines = result.split("\n")
        assert len(lines) == 3
        assert lines[2] == "| a | b |"

    def test_empty_rows(self):
        """No data rows: header + separator only."""
        result = render_markdown_table(["Col1", "Col2"], [])
        assert result == (
            "| Col1 | Col2 |\n"
            "| --- | --- |"
        )


# -- render_markdown_table: alignment ----------------------------------------


class TestAlignment:
    """Alignment marker generation."""

    def test_left_alignment(self):
        """Left-aligned columns use :--- separator."""
        result = render_markdown_table(
            ["A", "B"],
            [["1", "2"]],
            align=["left", "left"],
        )
        assert "| :--- | :--- |" in result

    def test_right_alignment(self):
        """Right-aligned columns use ---: separator."""
        result = render_markdown_table(
            ["A", "B"],
            [["1", "2"]],
            align=["right", "right"],
        )
        assert "| ---: | ---: |" in result

    def test_center_alignment(self):
        """Center-aligned columns use :---: separator."""
        result = render_markdown_table(
            ["A", "B"],
            [["1", "2"]],
            align=["center", "center"],
        )
        assert "| :---: | :---: |" in result

    def test_mixed_alignment(self):
        """Mix of left, center, right."""
        result = render_markdown_table(
            ["A", "B", "C"],
            [["1", "2", "3"]],
            align=["left", "center", "right"],
        )
        sep_line = result.split("\n")[1]
        assert sep_line == "| :--- | :---: | ---: |"

    def test_no_alignment(self):
        """No alignment: plain --- separators."""
        result = render_markdown_table(
            ["A", "B"],
            [["1", "2"]],
        )
        assert "| --- | --- |" in result

    def test_invalid_alignment_raises(self):
        """Invalid alignment value raises ValueError."""
        with pytest.raises(ValueError, match="invalid alignment"):
            render_markdown_table(["A"], [["1"]], align=["middle"])


# -- render_markdown_table: pretty-print mode --------------------------------


class TestPrettyPrint:
    """Pretty-print mode pads cells to column width."""

    def test_pretty_pads_cells(self):
        """Cells are padded to uniform width per column."""
        result = render_markdown_table(
            ["Name", "Value"],
            [["a", "longvalue"], ["longername", "b"]],
            pretty=True,
        )
        lines = result.split("\n")
        # All lines should have the same length
        lengths = [len(line) for line in lines]
        assert len(set(lengths)) == 1

    def test_pretty_pads_separator(self):
        """Separator dashes expand to column width."""
        result = render_markdown_table(
            ["Name", "X"],
            [["longname", "y"]],
            pretty=True,
        )
        sep = result.split("\n")[1]
        # The separator should have dashes padded to at least "longname" width
        assert "--------" in sep

    def test_pretty_with_alignment(self):
        """Pretty mode preserves alignment markers."""
        result = render_markdown_table(
            ["Name", "Count"],
            [["alpha", "100"]],
            align=["left", "right"],
            pretty=True,
        )
        sep = result.split("\n")[1]
        parts = [p.strip() for p in sep.strip("|").split("|")]
        # Left: starts with :
        assert parts[0].startswith(":")
        assert not parts[0].endswith(":")
        # Right: ends with :
        assert parts[1].endswith(":")
        assert not parts[1].startswith(":")


# -- render_markdown_table: pipe escaping ------------------------------------


class TestPipeEscaping:
    """Pipe character handling in cell content."""

    def test_bare_pipe_escaped(self):
        """A bare pipe in a cell is escaped to \\|."""
        result = render_markdown_table(
            ["Col"],
            [["a|b"]],
        )
        assert "a\\|b" in result

    def test_pipe_in_backtick_span_not_escaped(self):
        """A pipe inside backtick span is preserved as-is."""
        result = render_markdown_table(
            ["Col"],
            [["`a|b`"]],
        )
        assert "`a|b`" in result

    def test_pipe_outside_backtick_escaped(self):
        """Pipes outside backticks are escaped, those inside are not."""
        result = render_markdown_table(
            ["Col"],
            [["x|y `a|b` z|w"]],
        )
        # Outside backticks: x\|y and z\|w
        # Inside backticks: a|b (preserved)
        assert "x\\|y" in result
        assert "`a|b`" in result
        assert "z\\|w" in result

    def test_pipe_in_header_escaped(self):
        """Pipes in header values are escaped too."""
        result = render_markdown_table(
            ["A|B"],
            [["1"]],
        )
        assert "A\\|B" in result


# -- render_markdown_table: validation ---------------------------------------


class TestValidation:
    """Error handling for invalid inputs."""

    def test_newline_in_cell_raises(self):
        """Newline in cell content raises ValueError."""
        with pytest.raises(ValueError, match="newline"):
            render_markdown_table(["A"], [["line1\nline2"]])

    def test_newline_in_header_raises(self):
        """Newline in header raises ValueError."""
        with pytest.raises(ValueError, match="newline"):
            render_markdown_table(["A\nB"], [["1"]])

    def test_row_shorter_than_headers_padded(self):
        """Short row is padded with empty strings."""
        result = render_markdown_table(
            ["A", "B", "C"],
            [["1"]],
        )
        # Row should have 3 cells: "1", "", ""
        data_line = result.split("\n")[2]
        cells = [c.strip() for c in data_line.strip("|").split("|")]
        assert cells == ["1", "", ""]

    def test_row_longer_than_headers_raises(self):
        """Row with more cells than headers raises ValueError."""
        with pytest.raises(ValueError, match="3 cells.*2 headers"):
            render_markdown_table(["A", "B"], [["1", "2", "3"]])


# -- _parse_table: escaped pipes ---------------------------------------------


class TestParseTableEscapedPipes:
    """_parse_table handles escaped pipe characters."""

    def test_escaped_pipe_in_cell(self):
        """A \\| in cell content renders as a literal pipe."""
        lines = [
            "| Name | Value |",
            "| --- | --- |",
            "| cmd | a\\|b |",
        ]
        html = _parse_table(lines)
        assert "<td>a|b</td>" in html

    def test_escaped_pipe_in_header(self):
        """A \\| in header content renders as a literal pipe."""
        lines = [
            "| A\\|B | C |",
            "| --- | --- |",
            "| 1 | 2 |",
        ]
        html = _parse_table(lines)
        assert "<th>A|B</th>" in html

    def test_multiple_escaped_pipes(self):
        """Multiple escaped pipes in one cell."""
        lines = [
            "| Col |",
            "| --- |",
            "| x\\|y\\|z |",
        ]
        html = _parse_table(lines)
        assert "<td>x|y|z</td>" in html


# -- _parse_table: alignment markers ----------------------------------------


class TestParseTableAlignment:
    """_parse_table produces aligned HTML from separator markers."""

    def test_left_alignment(self):
        """Left-aligned separator produces text-align: left."""
        lines = [
            "| Name |",
            "| :--- |",
            "| val |",
        ]
        html = _parse_table(lines)
        assert 'style="text-align: left"' in html

    def test_right_alignment(self):
        """Right-aligned separator produces text-align: right."""
        lines = [
            "| Count |",
            "| ---: |",
            "| 42 |",
        ]
        html = _parse_table(lines)
        assert 'style="text-align: right"' in html

    def test_center_alignment(self):
        """Center-aligned separator produces text-align: center."""
        lines = [
            "| Label |",
            "| :---: |",
            "| mid |",
        ]
        html = _parse_table(lines)
        assert 'style="text-align: center"' in html

    def test_alignment_on_th_and_td(self):
        """Alignment is applied to both th and td elements."""
        lines = [
            "| Name |",
            "| :---: |",
            "| val |",
        ]
        html = _parse_table(lines)
        assert '<th style="text-align: center">' in html
        assert '<td style="text-align: center">' in html

    def test_mixed_alignment(self):
        """Different alignments per column."""
        lines = [
            "| Left | Center | Right |",
            "| :--- | :---: | ---: |",
            "| a | b | c |",
        ]
        html = _parse_table(lines)
        assert 'text-align: left' in html
        assert 'text-align: center' in html
        assert 'text-align: right' in html

    def test_no_alignment_markers(self):
        """Plain separator produces no style attributes."""
        lines = [
            "| A | B |",
            "| --- | --- |",
            "| 1 | 2 |",
        ]
        html = _parse_table(lines)
        assert "text-align" not in html


# -- _parse_table: backward compatibility -----------------------------------


class TestParseTableBackwardCompat:
    """Existing tables without alignment or escaped pipes still work."""

    def test_basic_table_unchanged(self):
        """A plain table renders as before."""
        lines = [
            "| Name | Value |",
            "| --- | --- |",
            "| foo | bar |",
        ]
        html = _parse_table(lines)
        assert "<thead>" in html
        assert "<tbody>" in html
        assert "<th>Name</th>" in html
        assert "<th>Value</th>" in html
        assert "<td>foo</td>" in html
        assert "<td>bar</td>" in html

    def test_no_separator_table(self):
        """Table without separator: all rows in tbody."""
        lines = [
            "| a | b |",
            "| c | d |",
        ]
        html = _parse_table(lines)
        assert "<thead>" not in html
        assert "<tbody>" in html
        assert "<td>" in html

    def test_empty_input(self):
        """Empty input returns empty string."""
        assert _parse_table([]) == ""
