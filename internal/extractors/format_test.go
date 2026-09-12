package extractors

import (
	"reflect"
	"regexp"
	"testing"
)

func TestFormatError(t *testing.T) {
	t.Parallel()
	if got, want := FormatError("boom"), "> *[selfdoc: boom]*"; got != want {
		t.Fatalf("FormatError = %q, want %q", got, want)
	}
}

func TestSymbolHeadingAndSpan(t *testing.T) {
	t.Parallel()
	if got, want := SymbolHeading(3, "Widget"), "### `Widget`"; got != want {
		t.Fatalf("SymbolHeading = %q, want %q", got, want)
	}
	if got, want := SymbolSpan("Widget"), "`Widget`"; got != want {
		t.Fatalf("SymbolSpan = %q, want %q", got, want)
	}
}

func TestSymbolHeadingPattern(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		page  string
		match bool
	}{
		{"code span heading", "## `Execute`", true},
		{"plain heading", "### Execute", true},
		{"qualified by owner", "#### `Pipeline.Execute`", true},
		{"h1 is not a symbol heading", "# Execute", false},
		{"h5 is too deep", "##### Execute", false},
		{"different symbol", "## `Executed`", false},
		{"inside a longer page", "intro\n\n### `Execute`\n\nbody", true},
	}
	pattern := SymbolHeadingPattern("Execute")
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := pattern.MatchString(tt.page); got != tt.match {
				t.Fatalf("match(%q) = %v, want %v", tt.page, got, tt.match)
			}
		})
	}
}

func TestSymbolHeadingPatternEscapesTheName(t *testing.T) {
	t.Parallel()
	pattern := SymbolHeadingPattern("a.b")
	if pattern.MatchString("## axb") {
		t.Fatal("the dot in the symbol name was treated as a wildcard")
	}
	if !pattern.MatchString("## `a.b`") {
		t.Fatal("the escaped name did not match its own heading")
	}
}

func TestDemoteDocHeadings(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name      string
		text      string
		baseLevel int
		want      string
	}{
		{"empty text is untouched", "", 2, ""},
		{"no headings is untouched", "Just prose.\n\nMore.", 2, "Just prose.\n\nMore."},
		{
			name:      "shallowest becomes the child of the base level",
			text:      "Intro.\n\n# Usage\n\nHow.\n\n## Detail\n\nMore.",
			baseLevel: 3,
			want:      "Intro.\n\n#### Usage\n\nHow.\n\n##### Detail\n\nMore.",
		},
		{
			name:      "already nested deeply enough is left alone",
			text:      "Intro.\n\n#### Deep\n\nText.",
			baseLevel: 2,
			want:      "Intro.\n\n#### Deep\n\nText.",
		},
		{
			name:      "a heading inside a fence is content",
			text:      "Intro.\n\n```\n# not a heading\n```\n\n# Usage",
			baseLevel: 2,
			want:      "Intro.\n\n```\n# not a heading\n```\n\n### Usage",
		},
		{
			name:      "nothing goes past h6",
			text:      "###### Floor\n\n# Top",
			baseLevel: 5,
			want:      "###### Floor\n\n###### Top",
		},
		{
			name:      "an indented hash is not a heading",
			text:      "  # shell prompt\n\n# Usage",
			baseLevel: 1,
			want:      "  # shell prompt\n\n## Usage",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := DemoteDocHeadings(tt.text, tt.baseLevel); got != tt.want {
				t.Fatalf("DemoteDocHeadings =\n%q\nwant\n%q", got, tt.want)
			}
		})
	}
}

func TestParseCommaSet(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		value string
		want  []string
	}{
		{"simple", "a,b,c", []string{"a", "b", "c"}},
		{"whitespace", "a, b , c", []string{"a", "b", "c"}},
		{"single", "single", []string{"single"}},
		{"empty string", "", nil},
		{"empty parts are dropped", "a,,b,", []string{"a", "b"}},
		{"duplicates collapse", "b,a,b", []string{"a", "b"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ParseCommaSet(tt.value); !reflect.DeepEqual(got, tt.want) {
				t.Fatalf("ParseCommaSet(%q) = %#v, want %#v", tt.value, got, tt.want)
			}
		})
	}
}

func TestExcludeKeysFromAttrs(t *testing.T) {
	t.Parallel()
	if got := ExcludeKeysFromAttrs(map[string]string{}); got != nil {
		t.Fatalf("absent exclude = %#v, want nil", got)
	}
	if got := ExcludeKeysFromAttrs(map[string]string{"exclude": ""}); got != nil {
		t.Fatalf("empty exclude = %#v, want nil", got)
	}
	want := []string{"a", "b"}
	if got := ExcludeKeysFromAttrs(map[string]string{"exclude": "b, a"}); !reflect.DeepEqual(got, want) {
		t.Fatalf("exclude = %#v, want %#v", got, want)
	}
}

func TestApplyExcludeKeys(t *testing.T) {
	t.Parallel()

	build := func() *JSONObject {
		data := NewJSONObject()
		data.Set("a", int64(1))
		data.Set("b", int64(2))
		data.Set("c", int64(3))
		return data
	}

	t.Run("no keys returns the same object", func(t *testing.T) {
		data := build()
		got, errMarkdown := ApplyExcludeKeys(data, nil, "test.json")
		if errMarkdown != "" {
			t.Fatalf("unexpected error marker %q", errMarkdown)
		}
		if got != data {
			t.Fatal("a no-op filter rebuilt the object")
		}
	})

	t.Run("empty key list returns the same object", func(t *testing.T) {
		data := build()
		got, _ := ApplyExcludeKeys(data, []string{}, "test.json")
		if got != data {
			t.Fatal("a no-op filter rebuilt the object")
		}
	})

	t.Run("valid keys are dropped in place", func(t *testing.T) {
		got, errMarkdown := ApplyExcludeKeys(build(), []string{"a", "c"}, "test.json")
		if errMarkdown != "" {
			t.Fatalf("unexpected error marker %q", errMarkdown)
		}
		if want := []string{"b"}; !reflect.DeepEqual(got.Keys(), want) {
			t.Fatalf("keys = %#v, want %#v", got.Keys(), want)
		}
	})

	t.Run("a missing key is an error marker", func(t *testing.T) {
		got, errMarkdown := ApplyExcludeKeys(build(), []string{"a", "missing"}, "test.json")
		if got != nil {
			t.Fatal("a rejected filter still returned an object")
		}
		want := "> *[selfdoc: exclude key 'missing' not found in 'test.json']*"
		if errMarkdown != want {
			t.Fatalf("error marker = %q, want %q", errMarkdown, want)
		}
	})
}

func TestExtractBraceBlock(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name   string
		source string
		pos    int
		want   string
		ok     bool
	}{
		{"simple block", "f() {body}", 4, "body", true},
		{"nested braces", "{a{b}c}", 0, "a{b}c", true},
		{"brace inside a string", "{\"}\"}", 0, "\"}\"", true},
		{"escaped quote inside a string", `{"a\"}b"}`, 0, `"a\"}b"`, true},
		{"backtick string", "{`}`}", 0, "`}`", true},
		{"unmatched", "{a", 0, "", false},
		{"not a brace", "x{}", 0, "", false},
		{"out of range", "{}", 5, "", false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, ok := ExtractBraceBlock(tt.source, tt.pos)
			if ok != tt.ok || got != tt.want {
				t.Fatalf("ExtractBraceBlock = (%q, %v), want (%q, %v)", got, ok, tt.want, tt.ok)
			}
		})
	}
}

func TestCollectCommentLinesAbove(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name      string
		lines     []string
		startLine int
		prefix    string
		skipBlank bool
		want      string
	}{
		{
			name:      "go style comments",
			lines:     []string{"// Package doc comment", "// with second line", "package main"},
			startLine: 2, prefix: "//", skipBlank: true,
			want: "Package doc comment\nwith second line",
		},
		{
			name:      "zig style doc comments",
			lines:     []string{"/// Doc comment for fn", "/// second line", "pub fn foo() void {}"},
			startLine: 2, prefix: "///", skipBlank: true,
			want: "Doc comment for fn\nsecond line",
		},
		{
			name:      "skips blank lines",
			lines:     []string{"// comment", "", "func foo() {}"},
			startLine: 2, prefix: "//", skipBlank: true,
			want: "comment",
		},
		{
			name:      "stops at a blank line when told not to skip",
			lines:     []string{"// comment", "", "func foo() {}"},
			startLine: 2, prefix: "//", skipBlank: false,
			want: "",
		},
		{
			name:      "no comments",
			lines:     []string{"import fmt", "func foo() {}"},
			startLine: 1, prefix: "//", skipBlank: true,
			want: "",
		},
		{
			name:      "the first line has nothing above it",
			lines:     []string{"func foo() {}"},
			startLine: 0, prefix: "//", skipBlank: true,
			want: "",
		},
		{
			name: "stops at a non-comment",
			lines: []string{
				"var x = 1", "// only this comment", "// and this one", "func foo() {}",
			},
			startLine: 3, prefix: "//", skipBlank: true,
			want: "only this comment\nand this one",
		},
		{
			name:      "prefix with no following space",
			lines:     []string{"//no space after prefix", "func foo() {}"},
			startLine: 1, prefix: "//", skipBlank: true,
			want: "no space after prefix",
		},
		{
			name:      "an empty comment line is an empty line",
			lines:     []string{"// first", "//", "// third", "func foo() {}"},
			startLine: 3, prefix: "//", skipBlank: true,
			want: "first\n\nthird",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := CollectCommentLinesAbove(tt.lines, tt.startLine, tt.prefix, tt.skipBlank)
			if got != tt.want {
				t.Fatalf("CollectCommentLinesAbove = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestDedent(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		text string
		want string
	}{
		{"no common margin", "a\n  b", "a\n  b"},
		{"uniform margin", "    a\n    b", "a\nb"},
		{"mixed depth keeps the relative shape", "    a\n        b", "a\n    b"},
		{"whitespace-only lines are emptied and ignored", "    a\n  \n    b", "a\n\nb"},
		{"tabs and spaces do not mix into a margin", "\ta\n    b", "\ta\n    b"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := Dedent(tt.text); got != tt.want {
				t.Fatalf("Dedent(%q) = %q, want %q", tt.text, got, tt.want)
			}
		})
	}
}

func TestSplitExt(t *testing.T) {
	t.Parallel()
	tests := []struct {
		path string
		stem string
		ext  string
	}{
		{"config.json", "config", ".json"},
		{"a/b/config.toml", "a/b/config", ".toml"},
		{"README", "README", ""},
		{".gitignore", ".gitignore", ""},
		{"a.b/c", "a.b/c", ""},
		{"archive.tar.gz", "archive.tar", ".gz"},
	}
	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			stem, ext := splitExt(tt.path)
			if stem != tt.stem || ext != tt.ext {
				t.Fatalf("splitExt(%q) = (%q, %q), want (%q, %q)", tt.path, stem, ext, tt.stem, tt.ext)
			}
		})
	}
}

// TestPySpaceClassCompiles pins that the ported character classes are valid
// RE2, since every regexp in this package is built from them.
func TestPySpaceClassCompiles(t *testing.T) {
	t.Parallel()
	for _, class := range []string{pySpaceClass, pyWordClass} {
		if _, err := regexp.Compile(class); err != nil {
			t.Fatalf("character class %s does not compile: %v", class, err)
		}
	}
}
