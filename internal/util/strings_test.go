package util

import (
	"testing"
	"time"
)

func TestEscapeHTML(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"empty", "", ""},
		{"plain", "hello", "hello"},
		{"ampersand first", "&", "&amp;"},
		{"angle brackets", "<b>", "&lt;b&gt;"},
		{"double quote", `say "hi"`, "say &quot;hi&quot;"},
		{"apostrophe is left alone", "don't", "don't"},
		{
			"already-escaped text is escaped again",
			"&amp;",
			"&amp;amp;",
		},
		{
			"attribute payload",
			`<a href="x?a=1&b=2">it's</a>`,
			"&lt;a href=&quot;x?a=1&amp;b=2&quot;&gt;it's&lt;/a&gt;",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := EscapeHTML(tt.in); got != tt.want {
				t.Errorf("EscapeHTML(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

// TestTitleCase compares against the output python3's str.title() produced for
// the same inputs.
func TestTitleCase(t *testing.T) {
	t.Parallel()
	tests := []struct {
		in   string
		want string
	}{
		{"", ""},
		{"hello world", "Hello World"},
		{"don't stop", "Don'T Stop"},
		{"a1b", "A1B"},
		{"HELLO world", "Hello World"},
		{"foo-bar baz", "Foo-Bar Baz"},
		{"x_y", "X_Y"},
		{"3rd place", "3Rd Place"},
		{"ÉCOLE française", "École Française"},
		{"straße", "Straße"},
		{"i18n api", "I18N Api"},
		{"  leading", "  Leading"},
		{"multi  space", "Multi  Space"},
		{"O'Neill mcdonald", "O'Neill Mcdonald"},
		{"已完成 ok", "已完成 Ok"},
		{"a.b.c", "A.B.C"},
		{"hello\tworld\nnew", "Hello\tWorld\nNew"},
		// The full title-case mappings, which a single-rune conversion misses.
		{"ßx", "Ssx"},
		{"a ßb", "A Ssb"},
		{"ﬀx", "Ffx"},
		{"ǉx", "ǈx"},
	}
	for _, tt := range tests {
		t.Run(tt.in, func(t *testing.T) {
			t.Parallel()
			if got := TitleCase(tt.in); got != tt.want {
				t.Errorf("TitleCase(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

// TestFormatDateLong compares against strftime("%B %-d, %Y").
func TestFormatDateLong(t *testing.T) {
	t.Parallel()
	tests := []struct {
		in   time.Time
		want string
	}{
		{time.Date(2026, 9, 1, 0, 0, 0, 0, time.UTC), "September 1, 2026"},
		{time.Date(2026, 9, 12, 13, 45, 0, 0, time.UTC), "September 12, 2026"},
		{time.Date(2026, 1, 31, 0, 0, 0, 0, time.UTC), "January 31, 2026"},
		{time.Date(1999, 12, 25, 0, 0, 0, 0, time.UTC), "December 25, 1999"},
		{time.Date(2026, 11, 9, 0, 0, 0, 0, time.UTC), "November 9, 2026"},
	}
	for _, tt := range tests {
		t.Run(tt.want, func(t *testing.T) {
			t.Parallel()
			if got := FormatDateLong(tt.in); got != tt.want {
				t.Errorf("FormatDateLong = %q, want %q", got, tt.want)
			}
		})
	}
}

// TestPathJoin compares against posixpath.join, including the two cases
// path/filepath.Join answers differently.
func TestPathJoin(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		parts []string
		want  string
	}{
		{"no parts", nil, ""},
		{"one part", []string{"docs"}, "docs"},
		{"simple", []string{"docs", "index.md"}, "docs/index.md"},
		{"existing separator is not doubled", []string{"docs/", "index.md"}, "docs/index.md"},
		{"empty base", []string{"", "index.md"}, "index.md"},
		{"empty tail keeps the separator", []string{"docs", ""}, "docs/"},
		{"an absolute tail replaces the base", []string{"docs", "/etc/passwd"}, "/etc/passwd"},
		{"the result is not cleaned", []string{"docs", "../x"}, "docs/../x"},
		{"three parts", []string{"a", "b", "c"}, "a/b/c"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := PathJoin(tt.parts...); got != tt.want {
				t.Errorf("PathJoin(%q) = %q, want %q", tt.parts, got, tt.want)
			}
		})
	}
}

func TestResolveDirectivePath(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name    string
		baseDir string
		path    string
		want    string
	}{
		{"relative", "/proj", "docs/x.md", "/proj/docs/x.md"},
		{"absolute path wins", "/proj", "/abs/x.md", "/abs/x.md"},
		{"parent traversal is preserved", "/proj", "../x.md", "/proj/../x.md"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := ResolveDirectivePath(tt.baseDir, tt.path); got != tt.want {
				t.Errorf("ResolveDirectivePath = %q, want %q", got, tt.want)
			}
		})
	}
}
