package prose

import "testing"

// TestFirstSentence is the ported first_sentence suite, extended with the
// boundary cases the Python was probed on. Every want below is the string the
// Python returned for the same input.
func TestFirstSentence(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"a period ends the sentence", "Hello world. More text.", "Hello world."},
		{"an exclamation mark ends it", "Watch out! Then relax.", "Watch out!"},
		{"a question mark ends it", "Ready? Set. Go.", "Ready?"},
		{
			"no terminator returns the whole paragraph",
			"Just some words here", "Just some words here",
		},
		{"a decimal is not a boundary", "Pi is 3.14 exactly. Next.", "Pi is 3.14 exactly."},
		{"a version is not a boundary", "Requires v1.0 or newer. Also.", "Requires v1.0 or newer."},
		{"e.g. is guarded", "See e.g. the docs. Done.", "See e.g. the docs."},
		{
			"i.e. is guarded",
			"The core, i.e. the engine, runs. Yes.",
			"The core, i.e. the engine, runs.",
		},
		{
			"etc. is guarded",
			"Apples, oranges, etc. are fruit. Ok.",
			"Apples, oranges, etc. are fruit.",
		},
		{"vs. is guarded", "Cats vs. dogs is old. Next.", "Cats vs. dogs is old."},
		{"a title is guarded", "Ask Dr. Smith today. Later.", "Ask Dr. Smith today."},
		{
			"an abbreviation is matched case-insensitively",
			"ETC. is upper. Next.", "ETC. is upper.",
		},
		{"punctuation is never synthesized", "word", "word"},
		{
			"only the first paragraph is read",
			"First para start. First para end.\n\nSecond paragraph.",
			"First para start.",
		},
		{"the empty string", "", ""},
		{"a terminator at the end of the text", "Only one sentence.", "Only one sentence."},
		{"an unknown abbreviation is a boundary", "A.B. C", "A.B."},
		{"a period with no space does not split", "Hello.World. Next.", "Hello.World."},
		{"two spaces after the period still split", "x.  Two spaces. Next.", "x."},
		{"an exclamation with no space does not split", "Done!Not a break. Yes.", "Done!Not a break."},
		{
			"a non-ASCII sentence is sliced on the terminator",
			"Ünïcödé sentence here. Next.", "Ünïcödé sentence here.",
		},
		{"a bare period", ".", "."},
		{"a period that begins the paragraph after stripping", " . x", "."},
		{"a one-letter token is not an abbreviation", "a. b. c", "a."},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := FirstSentence(tt.in); got != tt.want {
				t.Errorf("FirstSentence(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

// TestFirstParagraph is the ported first_paragraph suite.
func TestFirstParagraph(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"a single paragraph", "Line one. Line two.", "Line one. Line two."},
		{
			"soft-wrapped lines are joined",
			"This paragraph is\nwrapped across three\nphysical lines.",
			"This paragraph is wrapped across three physical lines.",
		},
		{
			"it stops at a blank line",
			"First paragraph line one.\nline two.\n\nSecond paragraph.",
			"First paragraph line one. line two.",
		},
		{"leading blank lines are skipped", "\n\nActual content.", "Actual content."},
		{"the empty string", "", ""},
		{"every line is stripped", "  indented  \n  more  ", "indented more"},
		{"only blank lines yield nothing", "\n\n\n", ""},
		{"several blank lines end the paragraph once", "one\n\n\ntwo", "one"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := FirstParagraph(tt.in); got != tt.want {
				t.Errorf("FirstParagraph(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

// TestFirstParagraphHasNoLengthCap ports the assertion that the picker never
// truncates.
func TestFirstParagraphHasNoLengthCap(t *testing.T) {
	t.Parallel()
	words := make([]byte, 0, 5*200)
	for i := 0; i < 200; i++ {
		if i > 0 {
			words = append(words, ' ')
		}
		words = append(words, "word"...)
	}
	long := string(words)
	if got := FirstParagraph(long); got != long {
		t.Errorf("FirstParagraph() truncated a %d-character paragraph to %d", len(long), len(got))
	}
}

// TestJoinWrappedLines is the ported join_wrapped_lines suite, with the
// verbatim-preservation cases asserted on the whole output rather than on a
// substring.
func TestJoinWrappedLines(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   string
		want string
	}{
		{
			"a wrapped paragraph is joined",
			"Package config manages the\nloading of configuration from\ndisk.",
			"Package config manages the loading of configuration from disk.",
		},
		{
			"a blank line still separates paragraphs",
			"First paragraph\nwrapped.\n\nSecond paragraph\nwrapped.",
			"First paragraph wrapped.\n\nSecond paragraph wrapped.",
		},
		{
			"a fenced code block is verbatim",
			"Intro line\ncontinues.\n\n```\ncode line 1\ncode line 2\n```",
			"Intro line continues.\n\n```\ncode line 1\ncode line 2\n```",
		},
		{
			"a tilde fence is verbatim too",
			"~~~\nraw\n~~~\nafter",
			"~~~\nraw\n~~~\nafter",
		},
		{
			"an unterminated fence swallows the rest",
			"unterminated\n```\nfence body",
			"unterminated\n```\nfence body",
		},
		{
			"an indented preformatted block is verbatim",
			"Example usage below:\n\n    go run main.go\n    ./binary",
			"Example usage below:\n\n    go run main.go\n    ./binary",
		},
		{
			"list items are verbatim",
			"Features:\n\n- item one\n- item two",
			"Features:\n\n- item one\n- item two",
		},
		{
			"an ordered list with periods is verbatim",
			"1. first\n2. second",
			"1. first\n2. second",
		},
		{
			"an ordered list with parentheses is verbatim",
			"1) alt\n2) alt",
			"1) alt\n2) alt",
		},
		{"a plus-marked item is verbatim", "+ plus item", "+ plus item"},
		{
			"doctest lines are verbatim",
			"Example.\n\n>>> f(1)\n2",
			"Example.\n\n>>> f(1)\n2",
		},
		{
			"a doctest continuation is verbatim",
			"...doctest cont\ntext",
			"...doctest cont\ntext",
		},
		{
			"a heading ends the paragraph below it",
			"# Heading\nbody line\nmore body",
			"# Heading\nbody line more body",
		},
		{"a heading ends the paragraph above it", "body\n# Heading", "body\n# Heading"},
		{
			"seven hashes are not a heading",
			"####### too many\nhashes",
			"####### too many hashes",
		},
		{"six hashes are a heading", "###### six\nhashes", "###### six\nhashes"},
		{"a bare hash is a heading", "#\nbody", "#\nbody"},
		{"already-joined prose is unchanged", "A single already-joined sentence.", "A single already-joined sentence."},
		{"the empty string", "", ""},
		{"blank-separated single lines are unchanged", "a\n\nb\n\nc", "a\n\nb\n\nc"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := JoinWrappedLines(tt.in); got != tt.want {
				t.Errorf("JoinWrappedLines(%q) =\n%q\nwant\n%q", tt.in, got, tt.want)
			}
		})
	}
}

// TestJoinWrappedLinesIsIdempotent ports the idempotence claim in the doc
// comment, over every case the suite above covers.
func TestJoinWrappedLinesIsIdempotent(t *testing.T) {
	t.Parallel()
	for _, in := range []string{
		"Package config manages the\nloading of configuration from\ndisk.",
		"First paragraph\nwrapped.\n\nSecond paragraph\nwrapped.",
		"Intro line\ncontinues.\n\n```\ncode line 1\ncode line 2\n```",
		"Example usage below:\n\n    go run main.go\n    ./binary",
		"Features:\n\n- item one\n- item two",
		"# Heading\nbody line\nmore body",
	} {
		once := JoinWrappedLines(in)
		if twice := JoinWrappedLines(once); twice != once {
			t.Errorf("JoinWrappedLines is not idempotent on %q: %q then %q", in, once, twice)
		}
	}
}

// TestWrappedGoCommentYieldsAWholeSentence ports the end-to-end case: a
// Go-style package comment whose first sentence spans physical lines.
func TestWrappedGoCommentYieldsAWholeSentence(t *testing.T) {
	t.Parallel()
	in := "Package config loads and validates the tool's configuration\n" +
		"from disk, applying defaults and reporting errors clearly."
	want := "Package config loads and validates the tool's configuration " +
		"from disk, applying defaults and reporting errors clearly."
	if got := FirstSentence(JoinWrappedLines(in)); got != want {
		t.Errorf("FirstSentence(JoinWrappedLines()) = %q, want %q", got, want)
	}
}

// TestIsSpaceCoversPythonsInformationSeparators pins the one place Go's own
// whitespace predicate is narrower than Python's.
func TestIsSpaceCoversPythonsInformationSeparators(t *testing.T) {
	t.Parallel()
	for _, r := range []rune{0x1c, 0x1d, 0x1e, 0x1f} {
		if !isSpace(r) {
			t.Errorf("isSpace(%#U) = false, want true", r)
		}
	}
	for _, r := range []rune{' ', '\t', '\n', '\r', '\v', '\f', 0x85, 0xa0, 0x2028, 0x3000} {
		if !isSpace(r) {
			t.Errorf("isSpace(%#U) = false, want true", r)
		}
	}
	for _, r := range []rune{'a', '0', '.', 0x200b} {
		if isSpace(r) {
			t.Errorf("isSpace(%#U) = true, want false", r)
		}
	}
}
