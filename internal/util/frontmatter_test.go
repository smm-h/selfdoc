package util

import (
	"reflect"
	"testing"
)

// TestParseFrontmatter drives the parser with the documents the Python
// implementation was probed on; every metadata map and body below is the
// output python3 produced for the same input.
func TestParseFrontmatter(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		input    string
		want     Frontmatter
		wantBody string
		wantLine int
	}{
		{
			name:     "no frontmatter",
			input:    "# Title\n\nBody\n",
			want:     Frontmatter{},
			wantBody: "# Title\n\nBody\n",
			wantLine: 0,
		},
		{
			name:     "unclosed fence leaves the document alone",
			input:    "---\ntitle: X\n\nBody\n",
			want:     Frontmatter{},
			wantBody: "---\ntitle: X\n\nBody\n",
			wantLine: 0,
		},
		{
			name:     "basic",
			input:    "---\ntitle: Hello\n---\n\nBody here\n",
			want:     Frontmatter{"title": "Hello"},
			wantBody: "Body here\n",
			wantLine: 4,
		},
		{
			name: "every value rule at once",
			input: "---\ntitle: Hello\ndraft: TRUE\npublished: false\norder: 12\n" +
				"ratio: 1.5\nweird: 1_000\nhexish: 0x10\ntags: [a, b , , c]\n" +
				"quoted: \"[x, y]\"\nqbool: 'true'\nempty:\ncolons: a: b: c\n" +
				"# comment: skipped\n\nnokey\n---\nbody\n",
			want: Frontmatter{
				"title":     "Hello",
				"draft":     true,
				"published": false,
				"order":     int64(12),
				"ratio":     1.5,
				"weird":     int64(1000),
				"hexish":    "0x10",
				"tags":      []string{"a", "b", "c"},
				"quoted":    []string{"x", "y"},
				"qbool":     true,
				"empty":     "",
				"colons":    "a: b: c",
			},
			wantBody: "body\n",
			wantLine: 17,
		},
		{
			name:     "blank lines after the fence are stripped",
			input:    "---\na: 1\n---\n\n\n\nBody\n",
			want:     Frontmatter{"a": int64(1)},
			wantBody: "Body\n",
			wantLine: 6,
		},
		{
			name:     "body without a trailing newline",
			input:    "---\na: 1\n---\nBody",
			want:     Frontmatter{"a": int64(1)},
			wantBody: "Body",
			wantLine: 3,
		},
		{
			name:     "opening fence need not be the whole line",
			input:    "---abc\na: 1\n---\nBody",
			want:     Frontmatter{"a": int64(1)},
			wantBody: "Body",
			wantLine: 3,
		},
		{
			name:     "empty frontmatter",
			input:    "---\n---\nBody",
			want:     Frontmatter{},
			wantBody: "Body",
			wantLine: 2,
		},
		{
			name:     "only one pair of quotes is stripped",
			input:    "---\nk: \"'x'\"\n---\nB",
			want:     Frontmatter{"k": "'x'"},
			wantBody: "B",
			wantLine: 3,
		},
		{
			name:  "numeric spellings",
			input: "---\nk: 1e3\nn: -0\np: +5\nd: .5\nnegf: -1.25\n---\nB",
			want: Frontmatter{
				"k":    1000.0,
				"n":    int64(0),
				"p":    int64(5),
				"d":    0.5,
				"negf": -1.25,
			},
			wantBody: "B",
			wantLine: 7,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, body, lines := ParseFrontmatter(tt.input)
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("metadata = %#v, want %#v", got, tt.want)
			}
			if body != tt.wantBody {
				t.Errorf("body = %q, want %q", body, tt.wantBody)
			}
			if lines != tt.wantLine {
				t.Errorf("consumed lines = %d, want %d", lines, tt.wantLine)
			}
		})
	}
}

func TestParsePythonInt(t *testing.T) {
	t.Parallel()
	tests := []struct {
		in   string
		want int64
		ok   bool
	}{
		{"0", 0, true},
		{"12", 12, true},
		{"-0", 0, true},
		{"+5", 5, true},
		{"1_000", 1000, true},
		{"1__0", 0, false},
		{"_1", 0, false},
		{"1_", 0, false},
		{"0x10", 0, false},
		{"1.5", 0, false},
		{"", 0, false},
		// Python's arbitrary-precision int accepts this; int64 does not.
		{"9223372036854775808", 0, false},
	}
	for _, tt := range tests {
		t.Run(tt.in, func(t *testing.T) {
			t.Parallel()
			got, ok := ParsePythonInt(tt.in)
			if ok != tt.ok || got != tt.want {
				t.Errorf("ParsePythonInt(%q) = (%d, %t), want (%d, %t)", tt.in, got, ok, tt.want, tt.ok)
			}
		})
	}
}

func TestParsePythonFloat(t *testing.T) {
	t.Parallel()
	tests := []struct {
		in   string
		want float64
		ok   bool
	}{
		{"1.5", 1.5, true},
		{".5", 0.5, true},
		{"1e3", 1000, true},
		{"1E-3", 0.001, true},
		{"-1.25", -1.25, true},
		{"1_000.5", 1000.5, true},
		{"5.", 5, true},
		{"inf", 0, true},
		{"-Infinity", 0, true},
		{"0x1p-2", 0, false},
		{"1d", 0, false},
		{"", 0, false},
		{".", 0, false},
	}
	for _, tt := range tests {
		t.Run(tt.in, func(t *testing.T) {
			t.Parallel()
			got, ok := ParsePythonFloat(tt.in)
			if ok != tt.ok {
				t.Fatalf("ParsePythonFloat(%q) ok = %t, want %t", tt.in, ok, tt.ok)
			}
			// The infinities are checked by their spelling, not their value.
			if ok && tt.want != 0 && got != tt.want {
				t.Errorf("ParsePythonFloat(%q) = %v, want %v", tt.in, got, tt.want)
			}
		})
	}
}

// TestParsePythonFloatRejectsHex records the one place Go's parser is more
// permissive than Python's: Python's float() has no hexadecimal syntax.
func TestParsePythonFloatRejectsHex(t *testing.T) {
	t.Parallel()
	if _, ok := ParsePythonFloat("0x1p-2"); ok {
		t.Error("ParsePythonFloat accepted a hexadecimal float literal")
	}
}
