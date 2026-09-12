package tokenizer

import (
	"reflect"
	"testing"
)

// typeNames renders the token stream's type names, which several ported tests
// assert on directly.
func typeNames(tokens []Token) []string {
	names := make([]string, len(tokens))
	for i, tok := range tokens {
		names[i] = tokenTypeName(tok)
	}
	return names
}

// one tokenizes content and returns its single token, failing when the
// document produced any other number.
func one(t *testing.T, content string) Token {
	t.Helper()
	tokens := Tokenize(content)
	if len(tokens) != 1 {
		t.Fatalf("Tokenize(%q) produced %d tokens (%v), want 1",
			content, len(tokens), typeNames(tokens))
	}
	return tokens[0]
}

// TestCodeBlock is the ported TestCodeBlock class.
func TestCodeBlock(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   string
		want CodeBlock
	}{
		{
			name: "a fence with a language",
			in:   "```python\nprint('hi')\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "python",
				Lines: []string{"print('hi')"}, LineStart: 1,
			},
		},
		{
			name: "a bare fence has no language",
			in:   "```\nfoo\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "",
				Lines: []string{"foo"}, LineStart: 1,
			},
		},
		{
			name: "annotation lines after the fence belong to the block",
			in:   "```js\nlet x = 1; // [1]\n```\n[1]: assign x",
			want: CodeBlock{
				Span: Span{1, 4}, Lang: "js",
				Lines:       []string{"let x = 1; // [1]"},
				Annotations: []Annotation{{Key: "1", Note: "assign x"}},
				LineStart:   1,
			},
		},
		{
			name: "a hash inside a fence is code, not a heading",
			in:   "```python\n# this is a comment\nprint('hello')\n```",
			want: CodeBlock{
				Span: Span{1, 4}, Lang: "python",
				Lines:     []string{"# this is a comment", "print('hello')"},
				LineStart: 1,
			},
		},
		{
			name: "the validate marker is absent by default",
			in:   "```python\nprint('hi')\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "python",
				Lines: []string{"print('hi')"}, LineStart: 1,
			},
		},
		{
			name: "the validate marker",
			in:   "```python validate\nprint('hi')\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "python",
				Lines: []string{"print('hi')"}, LineStart: 1, Validate: true,
			},
		},
		{
			name: "the whole info-string vocabulary at once",
			in:   "```python run validate lines=5\nprint('hi')\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "python",
				Lines: []string{"print('hi')"}, Run: true,
				LineNumbers: true, LineStart: 5, Validate: true,
			},
		},
		{
			name: "a bare validate fence names a language, not the marker",
			in:   "```validate\nfoo\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "validate",
				Lines: []string{"foo"}, LineStart: 1,
			},
		},
		{
			name: "an unknown info token is ignored",
			in:   "```python nonsense validate\nprint('hi')\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "python",
				Lines: []string{"print('hi')"}, LineStart: 1, Validate: true,
			},
		},
		{
			name: "bare lines numbers from 1",
			in:   "```python lines\nx\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "python", Lines: []string{"x"},
				LineNumbers: true, LineStart: 1,
			},
		},
		{
			name: "an unparsable lines= keeps the default start",
			in:   "```python lines=abc\nx\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "python", Lines: []string{"x"},
				LineNumbers: true, LineStart: 1,
			},
		},
		{
			name: "an empty lines= keeps the default start",
			in:   "```python lines=\nx\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "python", Lines: []string{"x"},
				LineNumbers: true, LineStart: 1,
			},
		},
		{
			name: "a negative lines= is honored",
			in:   "```python lines=-3\nx\n```",
			want: CodeBlock{
				Span: Span{1, 3}, Lang: "python", Lines: []string{"x"},
				LineNumbers: true, LineStart: -3,
			},
		},
		{
			name: "an unterminated fence runs to the end of the document",
			in:   "```go\nunterminated fence",
			want: CodeBlock{
				Span: Span{1, 2}, Lang: "go",
				Lines: []string{"unterminated fence"}, LineStart: 1,
			},
		},
		{
			name: "a repeated annotation key keeps its place and takes the last note",
			in:   "```py\nx\n```\n[1]: one\n[2]: two\n[1]: one again",
			want: CodeBlock{
				Span: Span{1, 6}, Lang: "py", Lines: []string{"x"},
				Annotations: []Annotation{
					{Key: "1", Note: "one again"},
					{Key: "2", Note: "two"},
				},
				LineStart: 1,
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, ok := one(t, tt.in).(CodeBlock)
			if !ok {
				t.Fatalf("Tokenize(%q) produced %s, want CodeBlock",
					tt.in, tokenTypeName(one(t, tt.in)))
			}
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("Tokenize(%q) = %+v, want %+v", tt.in, got, tt.want)
			}
		})
	}
}

// TestNonNumericMarkerIsNotAnAnnotation pins the annotation pattern: the
// marker must be digits, so a "[a]: note" line after the fence stays prose and
// the code block's span stops at the closing fence.
func TestNonNumericMarkerIsNotAnAnnotation(t *testing.T) {
	t.Parallel()
	tokens := Tokenize("```py\nx\n```\n[a]: not numeric")
	if got := typeNames(tokens); !reflect.DeepEqual(got, []string{"CodeBlock", "Paragraph"}) {
		t.Fatalf("types = %v, want a CodeBlock then a Paragraph", got)
	}
	block := tokens[0].(CodeBlock)
	if block.End() != 3 || len(block.Annotations) != 0 {
		t.Errorf("block = %+v, want span 1-3 with no annotations", block)
	}
}

// TestConsecutiveCodeBlocks is the ported test that two fences in a row are
// two blocks with adjoining spans.
func TestConsecutiveCodeBlocks(t *testing.T) {
	t.Parallel()
	tokens := Tokenize("```py\na\n```\n```js\nb\n```")
	if got := typeNames(tokens); !reflect.DeepEqual(got, []string{"CodeBlock", "CodeBlock"}) {
		t.Fatalf("types = %v, want two CodeBlocks", got)
	}
	first, second := tokens[0].(CodeBlock), tokens[1].(CodeBlock)
	if first.Lang != "py" || second.Lang != "js" {
		t.Errorf("langs = %q and %q, want \"py\" and \"js\"", first.Lang, second.Lang)
	}
	if first.End() != 3 || second.Start() != 4 || second.End() != 6 {
		t.Errorf("spans = %d-%d and %d-%d, want 1-3 and 4-6",
			first.Start(), first.End(), second.Start(), second.End())
	}
}

// TestHeading is the ported TestHeading class.
func TestHeading(t *testing.T) {
	t.Parallel()
	tests := []struct {
		in   string
		want Heading
	}{
		{"# Title", Heading{Span: Span{1, 1}, Level: 1, Text: "Title"}},
		{"### Sub-sub", Heading{Span: Span{1, 1}, Level: 3, Text: "Sub-sub"}},
		{"###### Deep", Heading{Span: Span{1, 1}, Level: 6, Text: "Deep"}},
	}
	for _, tt := range tests {
		t.Run(tt.in, func(t *testing.T) {
			t.Parallel()
			got, ok := one(t, tt.in).(Heading)
			if !ok {
				t.Fatalf("Tokenize(%q) did not produce a Heading", tt.in)
			}
			if got != tt.want {
				t.Errorf("Tokenize(%q) = %+v, want %+v", tt.in, got, tt.want)
			}
		})
	}
}

// TestSevenHashesIsAParagraph pins the level bound: the heading pattern tops
// out at six hashes, so a seventh makes the line prose.
func TestSevenHashesIsAParagraph(t *testing.T) {
	t.Parallel()
	if got := tokenTypeName(one(t, "####### seven")); got != "Paragraph" {
		t.Errorf("Tokenize(\"####### seven\") produced %s, want Paragraph", got)
	}
}

// TestTable is the ported TestTable class, plus the stripping the tokenizer
// applies to every row.
func TestTable(t *testing.T) {
	t.Parallel()
	got, ok := one(t, "| A | B |\n| --- | --- |\n| 1 | 2 |").(Table)
	if !ok {
		t.Fatal("did not produce a Table")
	}
	want := Table{
		Span: Span{1, 3},
		Rows: []string{"| A | B |", "| --- | --- |", "| 1 | 2 |"},
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("Tokenize() = %+v, want %+v", got, want)
	}

	indented, ok := one(t, "  | A | B |  \n| --- | --- |").(Table)
	if !ok {
		t.Fatal("an indented table row did not produce a Table")
	}
	if !reflect.DeepEqual(indented.Rows, []string{"| A | B |", "| --- | --- |"}) {
		t.Errorf("rows = %q, want the stripped rows", indented.Rows)
	}
}

// TestUnorderedList is the ported TestUnorderedList class.
func TestUnorderedList(t *testing.T) {
	t.Parallel()
	dash, ok := one(t, "- alpha\n- beta").(UnorderedList)
	if !ok {
		t.Fatal("dashes did not produce an UnorderedList")
	}
	if want := (UnorderedList{Span: Span{1, 2}, Items: []string{"alpha", "beta"}}); !reflect.DeepEqual(dash, want) {
		t.Errorf("Tokenize() = %+v, want %+v", dash, want)
	}

	star, ok := one(t, "* one\n* two\n* three").(UnorderedList)
	if !ok {
		t.Fatal("asterisks did not produce an UnorderedList")
	}
	if !reflect.DeepEqual(star.Items, []string{"one", "two", "three"}) {
		t.Errorf("items = %q", star.Items)
	}
}

// TestOrderedList is the ported TestOrderedList class.
func TestOrderedList(t *testing.T) {
	t.Parallel()
	got, ok := one(t, "1. first\n2. second\n3. third").(OrderedList)
	if !ok {
		t.Fatal("did not produce an OrderedList")
	}
	want := OrderedList{Span: Span{1, 3}, Items: []string{"first", "second", "third"}}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("Tokenize() = %+v, want %+v", got, want)
	}

	multi, ok := one(t, "10. ten\n11. eleven").(OrderedList)
	if !ok {
		t.Fatal("multi-digit markers did not produce an OrderedList")
	}
	if !reflect.DeepEqual(multi.Items, []string{"ten", "eleven"}) {
		t.Errorf("items = %q", multi.Items)
	}
}

// TestBlockquote is the ported TestBlockquote class.
func TestBlockquote(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   string
		want Blockquote
	}{
		{
			name: "a plain quote carries no admonition",
			in:   "> hello\n> world",
			want: Blockquote{Span: Span{1, 2}, Lines: []string{"hello", "world"}},
		},
		{
			name: "a known admonition marker is detected",
			in:   "> [!WARNING]\n> Be careful",
			want: Blockquote{
				Span:  Span{1, 2},
				Lines: []string{"[!WARNING]", "Be careful"}, AdmonitionType: "WARNING",
			},
		},
		{
			name: "any word is an admonition type",
			in:   "> [!DANGER]\n> watch out",
			want: Blockquote{
				Span:  Span{1, 2},
				Lines: []string{"[!DANGER]", "watch out"}, AdmonitionType: "DANGER",
			},
		},
		{
			name: "a marker with punctuation is not an admonition",
			in:   "> [!not a word]\n> body",
			want: Blockquote{Span: Span{1, 2}, Lines: []string{"[!not a word]", "body"}},
		},
		{
			name: "a quote marker with no space still strips",
			in:   ">no space",
			want: Blockquote{Span: Span{1, 1}, Lines: []string{"no space"}},
		},
		{
			name: "a bare quote marker",
			in:   ">",
			want: Blockquote{Span: Span{1, 1}, Lines: []string{""}},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, ok := one(t, tt.in).(Blockquote)
			if !ok {
				t.Fatalf("Tokenize(%q) did not produce a Blockquote", tt.in)
			}
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("Tokenize(%q) = %+v, want %+v", tt.in, got, tt.want)
			}
		})
	}
}

// TestDefinitionList is the ported TestDefinitionList class, including the
// blank line that separates two groups and is part of the same token.
func TestDefinitionList(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   string
		want DefinitionList
	}{
		{
			name: "one term and one definition",
			in:   "Term\n: Definition",
			want: DefinitionList{
				Span: Span{1, 2},
				Entries: []DefinitionEntry{
					{Term: "Term", Definitions: []string{"Definition"}},
				},
			},
		},
		{
			name: "several definitions under one term",
			in:   "Word\n: Meaning one\n: Meaning two",
			want: DefinitionList{
				Span: Span{1, 3},
				Entries: []DefinitionEntry{
					{Term: "Word", Definitions: []string{"Meaning one", "Meaning two"}},
				},
			},
		},
		{
			name: "a blank line between two groups is part of the token",
			in:   "Alpha\n: First letter\n\nBeta\n: Second letter",
			want: DefinitionList{
				Span: Span{1, 5},
				Entries: []DefinitionEntry{
					{Term: "Alpha", Definitions: []string{"First letter"}},
					{Term: "Beta", Definitions: []string{"Second letter"}},
				},
			},
		},
		{
			name: "several blank lines between groups are consumed too",
			in:   "Alpha\n: First letter\n\n\nBeta\n: Second letter",
			want: DefinitionList{
				Span: Span{1, 6},
				Entries: []DefinitionEntry{
					{Term: "Alpha", Definitions: []string{"First letter"}},
					{Term: "Beta", Definitions: []string{"Second letter"}},
				},
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, ok := one(t, tt.in).(DefinitionList)
			if !ok {
				t.Fatalf("Tokenize(%q) did not produce a DefinitionList", tt.in)
			}
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("Tokenize(%q) = %+v, want %+v", tt.in, got, tt.want)
			}
		})
	}
}

// TestDefinitionListEndsAtANonTerm pins where the token stops: a blank line
// followed by something that is not a term-and-definition pair ends it, and
// the blank line stays outside.
func TestDefinitionListEndsAtANonTerm(t *testing.T) {
	t.Parallel()
	tokens := Tokenize("Alpha\n: First letter\n\nnot a term")
	if got := typeNames(tokens); !reflect.DeepEqual(got,
		[]string{"DefinitionList", "BlankLine", "Paragraph"}) {
		t.Fatalf("types = %v", got)
	}
	if tokens[0].End() != 2 {
		t.Errorf("the definition list ends at line %d, want 2", tokens[0].End())
	}
}

// TestThematicBreak is the ported TestThematicBreak class.
func TestThematicBreak(t *testing.T) {
	t.Parallel()
	for _, in := range []string{"---", "***", "___", "----------"} {
		t.Run(in, func(t *testing.T) {
			t.Parallel()
			got := one(t, in)
			if _, ok := got.(ThematicBreak); !ok {
				t.Fatalf("Tokenize(%q) produced %s, want ThematicBreak", in, tokenTypeName(got))
			}
			if got.Start() != 1 || got.End() != 1 {
				t.Errorf("span = %d-%d, want 1-1", got.Start(), got.End())
			}
		})
	}
}

// TestTwoDashesIsAParagraph pins the pattern's lower bound: a break needs
// three marks.
func TestTwoDashesIsAParagraph(t *testing.T) {
	t.Parallel()
	if got := tokenTypeName(one(t, "--")); got != "Paragraph" {
		t.Errorf("Tokenize(\"--\") produced %s, want Paragraph", got)
	}
}

// TestBlankLine is the ported TestBlankLine class.
func TestBlankLine(t *testing.T) {
	t.Parallel()
	for _, in := range []string{"", "   "} {
		got := one(t, in)
		if _, ok := got.(BlankLine); !ok {
			t.Errorf("Tokenize(%q) produced %s, want BlankLine", in, tokenTypeName(got))
		}
		if got.Start() != 1 || got.End() != 1 {
			t.Errorf("Tokenize(%q) span = %d-%d, want 1-1", in, got.Start(), got.End())
		}
	}
}

// TestParagraph is the ported TestParagraph class.
func TestParagraph(t *testing.T) {
	t.Parallel()
	got, ok := one(t, "Hello world\nthis is a paragraph").(Paragraph)
	if !ok {
		t.Fatal("did not produce a Paragraph")
	}
	want := Paragraph{
		Span:  Span{1, 2},
		Lines: []string{"Hello world", "this is a paragraph"},
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("Tokenize() = %+v, want %+v", got, want)
	}
}

// TestParagraphStopsBeforeEveryOtherBlock covers each break condition in the
// paragraph branch.
func TestParagraphStopsBeforeEveryOtherBlock(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		in    string
		types []string
	}{
		{
			"a definition list", "Some intro text\nTerm\n: Definition",
			[]string{"Paragraph", "DefinitionList"},
		},
		{"a blank line", "text\n\nmore", []string{"Paragraph", "BlankLine", "Paragraph"}},
		{"a fence", "text\n```py\nx\n```", []string{"Paragraph", "CodeBlock"}},
		{"a heading", "text\n# Head", []string{"Paragraph", "Heading"}},
		{"a thematic break", "text\n---", []string{"Paragraph", "ThematicBreak"}},
		{"an unordered list", "text\n- item", []string{"Paragraph", "UnorderedList"}},
		{"an ordered list", "text\n1. item", []string{"Paragraph", "OrderedList"}},
		{"a table row", "text\n| a | b |", []string{"Paragraph", "Table"}},
		{"a blockquote", "text\n> quote", []string{"Paragraph", "Blockquote"}},
		{
			"a directive", "Intro paragraph.\n:::cli my.module\n:::",
			[]string{"Paragraph", "Directive"},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			tokens := Tokenize(tt.in)
			if got := typeNames(tokens); !reflect.DeepEqual(got, tt.types) {
				t.Fatalf("Tokenize(%q) types = %v, want %v", tt.in, got, tt.types)
			}
			if lines := tokens[0].(Paragraph).Lines; len(lines) != 1 {
				t.Errorf("the paragraph absorbed %q, want one line", lines)
			}
		})
	}
}

// TestMixedDocument is the ported TestMixedDocument class: every block type
// appears in one document.
func TestMixedDocument(t *testing.T) {
	t.Parallel()
	md := "# Welcome\n\nA paragraph of text\nspanning two lines.\n\n---\n\n" +
		"## Code Example\n\n```python\n# a comment\nx = 1\n```\n\n" +
		"| Col1 | Col2 |\n| ---- | ---- |\n| a    | b    |\n\n" +
		"- item one\n- item two\n\n1. first\n2. second\n\n" +
		"> [!NOTE]\n> Take note\n\n:::cli my.module\n:::\n\nTerm\n: Its definition"
	present := map[string]bool{}
	for _, name := range typeNames(Tokenize(md)) {
		present[name] = true
	}
	for _, want := range []string{
		"Heading", "Paragraph", "ThematicBreak", "CodeBlock", "Table",
		"UnorderedList", "OrderedList", "Blockquote", "Directive",
		"DefinitionList", "BlankLine",
	} {
		if !present[want] {
			t.Errorf("the mixed document produced no %s", want)
		}
	}
}

// TestEmptyDocument and TestOnlyBlankLines are the ported edge cases: an empty
// string is one blank line, and N newlines are N+1 of them.
func TestEmptyDocument(t *testing.T) {
	t.Parallel()
	if _, ok := one(t, "").(BlankLine); !ok {
		t.Error("the empty document did not produce a BlankLine")
	}
}

func TestOnlyBlankLines(t *testing.T) {
	t.Parallel()
	tokens := Tokenize("\n\n\n")
	if len(tokens) != 4 {
		t.Fatalf("three newlines produced %d tokens, want 4", len(tokens))
	}
	for _, tok := range tokens {
		if _, ok := tok.(BlankLine); !ok {
			t.Errorf("produced %s, want BlankLine", tokenTypeName(tok))
		}
	}
}

// TestDirective is the ported TestDirective class, covering the legacy
// ":::name arg" block form that documents still carry.
func TestDirective(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   string
		want Directive
	}{
		{
			name: "a name and an argument",
			in:   ":::cli rlsbl.commands.release\n:::",
			want: Directive{
				Span: Span{1, 2}, Name: "cli", Arg: "rlsbl.commands.release",
			},
		},
		{
			name: "a body between the markers",
			in:   ":::module mylib.config\nsome body line\nanother line\n:::",
			want: Directive{
				Span: Span{1, 4}, Name: "module", Arg: "mylib.config",
				Body: []string{"some body line", "another line"},
			},
		},
		{
			name: "a name with no argument",
			in:   ":::config\n:::",
			want: Directive{Span: Span{1, 2}, Name: "config"},
		},
		{
			name: "a directive is not a thematic break",
			in:   ":::test\n:::",
			want: Directive{Span: Span{1, 2}, Name: "test"},
		},
		{
			name: "an unclosed directive runs to the end of the document",
			in:   ":::unclosed\nbody",
			want: Directive{
				Span: Span{1, 2}, Name: "unclosed", Body: []string{"body"},
			},
		},
		{
			name: "the argument keeps its interior spacing and loses none at the end",
			in:   ":::name   spaced   arg   \n:::",
			want: Directive{
				Span: Span{1, 2}, Name: "name", Arg: "spaced   arg   ",
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, ok := one(t, tt.in).(Directive)
			if !ok {
				t.Fatalf("Tokenize(%q) did not produce a Directive", tt.in)
			}
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("Tokenize(%q) = %+v, want %+v", tt.in, got, tt.want)
			}
		})
	}
}

// TestDirectiveNeedsAName pins the pattern: ":::" alone closes a directive and
// never opens one, so a bare pair is a paragraph followed by nothing else the
// directive branch claims.
func TestDirectiveNeedsAName(t *testing.T) {
	t.Parallel()
	if got := typeNames(Tokenize(":::\n:::")); !reflect.DeepEqual(got, []string{"Paragraph"}) {
		t.Errorf("Tokenize(\":::\\n:::\") types = %v, want one Paragraph", got)
	}
}

// TestDirectiveBetweenBlocks is the ported pair of placement tests.
func TestDirectiveBetweenBlocks(t *testing.T) {
	t.Parallel()
	if got := typeNames(Tokenize("## Section\n\n:::cli my.module\n:::")); !reflect.DeepEqual(
		got, []string{"Heading", "BlankLine", "Directive"}) {
		t.Errorf("types = %v", got)
	}
	if got := typeNames(Tokenize("Some intro text.\n\n:::module foo\n:::\n\nMore text.")); !reflect.DeepEqual(
		got, []string{"Paragraph", "BlankLine", "Directive", "BlankLine", "Paragraph"}) {
		t.Errorf("types = %v", got)
	}
}

// TestLineCoverage is the ported TestLineCoverage class: every line of a
// document belongs to one token and no more.
func TestLineCoverage(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   string
	}{
		{"a simple document", "# Hello\n\nWorld"},
		{
			"a mixed document",
			"# Title\n\nSome text.\n\n```go\n// comment\nfunc main() {}\n```\n" +
				"[1]: annotation\n\n---\n\n| A | B |\n| - | - |\n\n- x\n- y\n\n" +
				"1. a\n2. b\n\n> quote\n\n:::cli my.mod\n:::\n\nTerm\n: def",
		},
		{"consecutive code blocks", "```a\nfoo\n```\n```b\nbar\n```"},
		{"only blanks", "\n\n"},
		{"a heading inside a fence", "```\n# not a heading\n```"},
		{"every thematic break variant", "---\n\n***\n\n___"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			assertLineCoverage(t, tt.name, tt.in)
		})
	}
}

// TestTextBearingTokens is the ported TestTextBearingTokens class: the prose
// surface every rule that reads text runs over.
func TestTextBearingTokens(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name    string
		in      string
		bearing bool
		want    []string
	}{
		{"a heading bears its title", "## A heading", true, []string{"A heading"}},
		{
			"a table bears every row",
			"| a | b |\n| --- | --- |\n| c | d |", true,
			[]string{"| a | b |", "| --- | --- |", "| c | d |"},
		},
		{"a paragraph bears its lines", "plain text", true, []string{"plain text"}},
		{"an unordered item is parsed text", "- item", true, []string{"item"}},
		{"an ordered item is parsed text", "1. item", true, []string{"item"}},
		{"a quote bears its lines", "> quoted", true, []string{"quoted"}},
		{
			"a definition list flattens terms and definitions",
			"Term\n: meaning", true, []string{"Term", "meaning"},
		},
		{"a code block bears no prose", "```py\nx = 1\n```", false, nil},
		{"a directive bears no prose", ":::cli my.mod\n:::", false, nil},
		{"a thematic break bears no prose", "---", false, nil},
		{"a blank line bears no prose", "", false, nil},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			tok := one(t, tt.in)
			if got := IsTextBearing(tok); got != tt.bearing {
				t.Errorf("IsTextBearing(%s) = %v, want %v",
					tokenTypeName(tok), got, tt.bearing)
			}
			if got := TokenTextLines(tok); !reflect.DeepEqual(got, tt.want) {
				t.Errorf("TokenTextLines(%s) = %q, want %q",
					tokenTypeName(tok), got, tt.want)
			}
		})
	}
}

// TestOneTextEntryPerSourceLine pins the contract [TokenTextLines] documents:
// the i-th entry belongs on source line tok.Start()+i.
func TestOneTextEntryPerSourceLine(t *testing.T) {
	t.Parallel()
	for _, in := range []string{
		"| a |\n| --- |\n| c |",
		"- one\n- two\n- three",
		"1. one\n2. two",
		"> a\n> b",
		"para one\npara two",
		"# heading",
		"Term\n: def",
	} {
		tok := one(t, in)
		lines := TokenTextLines(tok)
		if want := tok.End() - tok.Start() + 1; len(lines) != want {
			t.Errorf("Tokenize(%q): %d text lines over %d source lines",
				in, len(lines), want)
		}
	}
}
