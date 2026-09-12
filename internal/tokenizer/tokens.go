// Package tokenizer is a standalone Markdown block tokenizer.
//
// It splits Markdown source into a flat slice of typed block tokens. Each
// token carries 1-based start and end line numbers, so a caller knows which
// source lines produced it; the tokens cover every line of the input once,
// with no gaps and no overlaps.
//
// The package imports nothing of selfdoc's -- it is designed for reuse outside
// the project.
package tokenizer

// Span is the 1-based, inclusive range of source lines a token covers. Every
// token type embeds it, which is how each satisfies [Token].
type Span struct {
	// StartLine is the first source line the token covers, counting the
	// first line of the input as 1.
	StartLine int
	// EndLine is the last source line the token covers, inclusive.
	EndLine int
}

// Start returns the first source line the token covers.
func (s Span) Start() int { return s.StartLine }

// End returns the last source line the token covers, inclusive.
func (s Span) End() int { return s.EndLine }

// Token is one block-level element of a tokenized document. Every token
// reports the source lines it came from.
type Token interface {
	// Start is the first source line the token covers (1-based).
	Start() int
	// End is the last source line the token covers, inclusive.
	End() int
}

// TextBearingToken is implemented by every token type that carries prose a
// reader sees on the page.
//
// Code blocks, directives, thematic breaks and blank lines are excluded
// structurally: a rule that reads prose runs over exactly the types
// implementing this interface, and can never reach a fenced example or an
// unresolved directive marker.
//
// Headings and tables are members. They were left out originally because
// their text is not stored line-per-line the way a paragraph's is, which meant
// every prose rule -- empty alt text, meaningless alt text, generic anchor
// text, broken cross-references, spelling -- silently skipped page titles and
// every table cell. [TokenTextLines] handles their shapes, so the exclusion is
// gone.
type TextBearingToken interface {
	Token
	// TextLines returns the text the token contributes, one entry per
	// source line.
	TextLines() []string
}

// Annotation is one trailing "[N]: note" line attached to a fenced code block.
type Annotation struct {
	// Key is the marker number as written, without its brackets.
	Key string
	// Note is the annotation text.
	Note string
}

// CodeBlock is a fenced code block, plus the annotation lines that follow its
// closing fence.
type CodeBlock struct {
	Span
	// Lang is the first token of the info string, or "" for a bare fence.
	Lang string
	// Lines are the code lines between the fences, verbatim.
	Lines []string
	// Annotations are the "[N]: note" lines after the closing fence, in the
	// order they were written. A repeated key keeps its first position and
	// takes the last note, which is what the Python dict did.
	Annotations []Annotation
	// Run is set by the "run" info-string token.
	Run bool
	// LineNumbers is set by the "lines" or "lines=N" info-string token.
	LineNumbers bool
	// LineStart is the first line number to display, 1 unless "lines=N"
	// named another.
	LineStart int
	// Validate is set by the "validate" info-string token: an opt-in
	// declaration that this block is a self-contained program, so selfdoc
	// check may hand it to the validator command configured for Lang.
	Validate bool
}

// Heading is an ATX heading.
type Heading struct {
	Span
	// Level is the number of leading hashes, 1 through 6.
	Level int
	// Text is the heading text after the hashes and their following
	// whitespace.
	Text string
}

// TextLines returns the heading's text as a single entry.
func (h Heading) TextLines() []string { return []string{h.Text} }

// Table is a run of pipe-delimited rows, each stripped of surrounding
// whitespace. Separator rows are kept: parsing the table's structure is the
// renderer's job, not the tokenizer's.
type Table struct {
	Span
	// Rows are the table's source lines, stripped.
	Rows []string
}

// TextLines returns the table's rows, one entry per source line.
func (t Table) TextLines() []string { return t.Rows }

// UnorderedList is a run of "-" or "*" list items with their markers stripped.
type UnorderedList struct {
	Span
	// Items are the item texts, without the list marker.
	Items []string
}

// TextLines returns the list's items, one entry per source line.
func (l UnorderedList) TextLines() []string { return l.Items }

// OrderedList is a run of "N." list items with their markers stripped.
type OrderedList struct {
	Span
	// Items are the item texts, without the list marker.
	Items []string
}

// TextLines returns the list's items, one entry per source line.
func (l OrderedList) TextLines() []string { return l.Items }

// Blockquote is a run of ">"-prefixed lines, each with the marker and one
// following space removed.
type Blockquote struct {
	Span
	// Lines are the quoted lines, without the ">" marker.
	Lines []string
	// AdmonitionType is the name inside a leading "[!NAME]" marker, or ""
	// when the first line carries none. The marker's name is never empty,
	// so "" is unambiguous.
	AdmonitionType string
}

// TextLines returns the quoted lines, one entry per source line.
func (b Blockquote) TextLines() []string { return b.Lines }

// DefinitionEntry is one term with its definitions.
type DefinitionEntry struct {
	// Term is the term line, stripped.
	Term string
	// Definitions are the ": "-prefixed lines under the term, with the
	// prefix removed.
	Definitions []string
}

// DefinitionList is a run of term-and-definition pairs, possibly separated by
// blank lines the token also covers.
type DefinitionList struct {
	Span
	// Entries are the term/definition pairs, in source order.
	Entries []DefinitionEntry
}

// TextLines returns each term followed by its definitions, flattened.
func (d DefinitionList) TextLines() []string {
	var lines []string
	for _, entry := range d.Entries {
		lines = append(lines, entry.Term)
		lines = append(lines, entry.Definitions...)
	}
	return lines
}

// ThematicBreak is a horizontal rule: a line of only dashes, asterisks or
// underscores.
type ThematicBreak struct {
	Span
}

// BlankLine is a line that is empty or only whitespace.
type BlankLine struct {
	Span
}

// Directive is the legacy ":::name arg ... :::" block form. The newer marker
// syntax is parsed elsewhere; this token exists because documents still carry
// the old form.
type Directive struct {
	Span
	// Name is the directive name after the opening ":::".
	Name string
	// Arg is the rest of the opening line, or "" when there was none.
	Arg string
	// Body are the lines between the opening and closing ":::".
	Body []string
}

// Paragraph is a run of lines that no other block claimed.
type Paragraph struct {
	Span
	// Lines are the paragraph's source lines, verbatim.
	Lines []string
}

// TextLines returns the paragraph's lines, one entry per source line.
func (p Paragraph) TextLines() []string { return p.Lines }

// IsTextBearing reports whether tok carries prose a reader sees on the page --
// whether it implements [TextBearingToken].
func IsTextBearing(tok Token) bool {
	_, ok := tok.(TextBearingToken)
	return ok
}

// TokenTextLines returns the text a content-bearing token contributes, one
// entry per line.
//
// The i-th entry corresponds to source line tok.Start()+i, so a caller holding
// a token and an index knows the real line a diagnostic belongs on. A token
// that bears no text returns nil.
//
// The text is the token's parsed text: list markers, blockquote markers and
// heading hashes are already stripped, so a column measured against these
// strings is not a column in the source line. A caller that needs exact
// columns should read the raw source lines the token spans instead
// (tok.Start() through tok.End()).
func TokenTextLines(tok Token) []string {
	if bearing, ok := tok.(TextBearingToken); ok {
		return bearing.TextLines()
	}
	return nil
}
