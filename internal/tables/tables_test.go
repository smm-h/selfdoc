package tables

import (
	"strings"
	"testing"
)

// TestRenderMarkdownTable is the ported render_markdown_table suite. Every
// want string below is what the Python implementation returned for the same
// arguments.
func TestRenderMarkdownTable(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name    string
		headers []string
		rows    [][]string
		align   []string
		pretty  bool
		want    string
	}{
		{
			name:    "two columns and two rows",
			headers: []string{"Name", "Value"},
			rows:    [][]string{{"alpha", "1"}, {"beta", "2"}},
			want: "| Name | Value |\n" +
				"| --- | --- |\n" +
				"| alpha | 1 |\n" +
				"| beta | 2 |",
		},
		{
			name:    "three columns and one row",
			headers: []string{"A", "B", "C"},
			rows:    [][]string{{"x", "y", "z"}},
			want:    "| A | B | C |\n| --- | --- | --- |\n| x | y | z |",
		},
		{
			name:    "single column",
			headers: []string{"Item"},
			rows:    [][]string{{"one"}, {"two"}},
			want:    "| Item |\n| --- |\n| one |\n| two |",
		},
		{
			name:    "one data row",
			headers: []string{"X", "Y"},
			rows:    [][]string{{"a", "b"}},
			want:    "| X | Y |\n| --- | --- |\n| a | b |",
		},
		{
			name:    "no data rows leaves header and separator",
			headers: []string{"Col1", "Col2"},
			rows:    nil,
			want:    "| Col1 | Col2 |\n| --- | --- |",
		},
		{
			name:    "left alignment",
			headers: []string{"A", "B"},
			rows:    [][]string{{"1", "2"}},
			align:   []string{"left", "left"},
			want:    "| A | B |\n| :--- | :--- |\n| 1 | 2 |",
		},
		{
			name:    "right alignment",
			headers: []string{"A", "B"},
			rows:    [][]string{{"1", "2"}},
			align:   []string{"right", "right"},
			want:    "| A | B |\n| ---: | ---: |\n| 1 | 2 |",
		},
		{
			name:    "center alignment",
			headers: []string{"A", "B"},
			rows:    [][]string{{"1", "2"}},
			align:   []string{"center", "center"},
			want:    "| A | B |\n| :---: | :---: |\n| 1 | 2 |",
		},
		{
			name:    "mixed alignment",
			headers: []string{"A", "B", "C"},
			rows:    [][]string{{"1", "2", "3"}},
			align:   []string{"left", "center", "right"},
			want:    "| A | B | C |\n| :--- | :---: | ---: |\n| 1 | 2 | 3 |",
		},
		{
			name:    "align shorter than headers leaves the rest unaligned",
			headers: []string{"A", "B", "C"},
			rows:    [][]string{{"1", "2", "3"}},
			align:   []string{"left"},
			want:    "| A | B | C |\n| :--- | --- | --- |\n| 1 | 2 | 3 |",
		},
		{
			name:    "align longer than headers ignores the extras",
			headers: []string{"A", "B"},
			rows:    [][]string{{"1", "2"}},
			align:   []string{"left", "center", "right", "left"},
			want:    "| A | B |\n| :--- | :---: |\n| 1 | 2 |",
		},
		{
			name:    "pretty pads every cell to the column width",
			headers: []string{"Name", "Value"},
			rows:    [][]string{{"a", "longvalue"}, {"longername", "b"}},
			pretty:  true,
			want: "| Name       | Value     |\n" +
				"| ---------- | --------- |\n" +
				"| a          | longvalue |\n" +
				"| longername | b         |",
		},
		{
			name:    "pretty extends the separator dashes",
			headers: []string{"Name", "X"},
			rows:    [][]string{{"longname", "y"}},
			pretty:  true,
			want:    "| Name     | X   |\n| -------- | --- |\n| longname | y   |",
		},
		{
			name:    "pretty preserves the alignment markers",
			headers: []string{"Name", "Count"},
			rows:    [][]string{{"alpha", "100"}},
			align:   []string{"left", "right"},
			pretty:  true,
			want:    "| Name  | Count |\n| :---- | ----: |\n| alpha | 100   |",
		},
		{
			name:    "pretty measures a cell in characters, not bytes",
			headers: []string{"A"},
			rows:    [][]string{{"ünïcödé"}},
			pretty:  true,
			want:    "| A       |\n| ------- |\n| ünïcödé |",
		},
		{
			name:    "pretty measures a header in characters too",
			headers: []string{"Ünï"},
			rows:    [][]string{{"a"}},
			pretty:  true,
			want:    "| Ünï |\n| --- |\n| a   |",
		},
		{
			name:    "a bare pipe in a cell is escaped",
			headers: []string{"Col"},
			rows:    [][]string{{"a|b"}},
			want:    "| Col |\n| --- |\n| a\\|b |",
		},
		{
			name:    "a pipe inside a backtick span is preserved",
			headers: []string{"Col"},
			rows:    [][]string{{"`a|b`"}},
			want:    "| Col |\n| --- |\n| `a|b` |",
		},
		{
			name:    "pipes outside a backtick span are escaped",
			headers: []string{"Col"},
			rows:    [][]string{{"x|y `a|b` z|w"}},
			want:    "| Col |\n| --- |\n| x\\|y `a|b` z\\|w |",
		},
		{
			name:    "a pipe in a header is escaped",
			headers: []string{"A|B"},
			rows:    [][]string{{"1"}},
			want:    "| A\\|B |\n| --- |\n| 1 |",
		},
		{
			name:    "a pipe after an unclosed backtick is escaped",
			headers: []string{"Col"},
			rows:    [][]string{{"a`b|c"}},
			want:    "| Col |\n| --- |\n| a`b\\|c |",
		},
		{
			name:    "a short row is padded with empty cells",
			headers: []string{"A", "B", "C"},
			rows:    [][]string{{"1"}},
			want:    "| A | B | C |\n| --- | --- | --- |\n| 1 |  |  |",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, err := RenderMarkdownTable(tt.headers, tt.rows, tt.align, tt.pretty)
			if err != nil {
				t.Fatalf("RenderMarkdownTable() error = %v", err)
			}
			if got != tt.want {
				t.Errorf("RenderMarkdownTable() =\n%q\nwant\n%q", got, tt.want)
			}
		})
	}
}

// TestRenderMarkdownTableErrors pins every error condition and its message,
// which is the text the Python's ValueError carried.
func TestRenderMarkdownTableErrors(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name    string
		headers []string
		rows    [][]string
		align   []string
		want    string
	}{
		{
			name:    "empty headers",
			headers: nil,
			want:    "headers must not be empty",
		},
		{
			name:    "invalid alignment",
			headers: []string{"A"},
			rows:    [][]string{{"1"}},
			align:   []string{"middle"},
			want:    "invalid alignment 'middle', must be one of: left, center, right",
		},
		{
			name:    "an empty alignment is invalid too",
			headers: []string{"A"},
			rows:    [][]string{{"1"}},
			align:   []string{""},
			want:    "invalid alignment '', must be one of: left, center, right",
		},
		{
			name:    "an alignment holding a single quote is double-quoted",
			headers: []string{"A"},
			rows:    [][]string{{"1"}},
			align:   []string{"mid'dle"},
			want:    `invalid alignment "mid'dle", must be one of: left, center, right`,
		},
		{
			name:    "an alignment holding a double quote stays single-quoted",
			headers: []string{"A"},
			rows:    [][]string{{"1"}},
			align:   []string{`mid"dle`},
			want:    "invalid alignment 'mid\"dle', must be one of: left, center, right",
		},
		{
			name:    "an unprintable character in an alignment is escaped",
			headers: []string{"A"},
			rows:    [][]string{{"1"}},
			align:   []string{"a\x01b"},
			want:    `invalid alignment 'a\x01b', must be one of: left, center, right`,
		},
		{
			name:    "a newline in a cell",
			headers: []string{"A"},
			rows:    [][]string{{"line1\nline2"}},
			want:    "cell values must not contain newline characters",
		},
		{
			name:    "a newline in a header",
			headers: []string{"A\nB"},
			rows:    [][]string{{"1"}},
			want:    "cell values must not contain newline characters",
		},
		{
			name:    "a row with more cells than headers",
			headers: []string{"A", "B"},
			rows:    [][]string{{"1", "2", "3"}},
			want:    "row 0 has 3 cells, but only 2 headers",
		},
		{
			name:    "the offending row index is named",
			headers: []string{"A"},
			rows:    [][]string{{"1"}, {"2", "3"}},
			want:    "row 1 has 2 cells, but only 1 headers",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			_, err := RenderMarkdownTable(tt.headers, tt.rows, tt.align, false)
			if err == nil {
				t.Fatalf("RenderMarkdownTable() error = nil, want %q", tt.want)
			}
			if err.Error() != tt.want {
				t.Errorf("RenderMarkdownTable() error = %q, want %q", err, tt.want)
			}
		})
	}
}

// TestPrettyLinesAreUniformWidth ports the assertion that pretty mode makes
// every rendered line the same length.
func TestPrettyLinesAreUniformWidth(t *testing.T) {
	t.Parallel()
	got, err := RenderMarkdownTable(
		[]string{"Name", "Value"},
		[][]string{{"a", "longvalue"}, {"longername", "b"}},
		nil, true,
	)
	if err != nil {
		t.Fatalf("RenderMarkdownTable() error = %v", err)
	}
	lines := strings.Split(got, "\n")
	for _, line := range lines[1:] {
		if len(line) != len(lines[0]) {
			t.Errorf("line %q is %d wide, want %d", line, len(line), len(lines[0]))
		}
	}
}

// TestEscapePipes drives the escaper directly, including the unclosed-backtick
// rescan and the alternating spans a rescan must not disturb.
func TestEscapePipes(t *testing.T) {
	t.Parallel()
	tests := []struct{ in, want string }{
		{"a|b", `a\|b`},
		{"`a|b`", "`a|b`"},
		{"x|y `a|b` z|w", "x\\|y `a|b` z\\|w"},
		{"a`b|c", "a`b\\|c"},
		{"``", "``"},
		{"|", `\|`},
		{"`|", "`\\|"},
		{"a`b`c|d", "a`b`c\\|d"},
		{"`a`|`b`", "`a`\\|`b`"},
		{"`a|b`c|d`e|f", "`a|b`c\\|d`e\\|f"},
		{"", ""},
		{"plain text", "plain text"},
	}
	for _, tt := range tests {
		t.Run(tt.in, func(t *testing.T) {
			t.Parallel()
			if got := EscapePipes(tt.in); got != tt.want {
				t.Errorf("EscapePipes(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

// TestEscapePipesIsRuneSafe checks that a multi-byte character neither loses
// bytes nor shifts the rescan position, which a byte-indexed port would break.
func TestEscapePipesIsRuneSafe(t *testing.T) {
	t.Parallel()
	if got, want := EscapePipes("é|ü"), `é\|ü`; got != want {
		t.Errorf("EscapePipes() = %q, want %q", got, want)
	}
	if got, want := EscapePipes("é`ü|ö"), "é`ü\\|ö"; got != want {
		t.Errorf("EscapePipes() = %q, want %q", got, want)
	}
}
