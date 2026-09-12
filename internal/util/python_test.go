package util

import (
	"reflect"
	"regexp"
	"testing"
	"time"
)

func TestIsPythonSpace(t *testing.T) {
	space := []rune{'\t', '\n', '\v', '\f', '\r', ' ', 0x1c, 0x1d, 0x1e, 0x1f,
		0x85, 0xa0, 0x1680, 0x2000, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000}
	for _, r := range space {
		if !IsPythonSpace(r) {
			t.Errorf("IsPythonSpace(%#x) = false, want true", r)
		}
	}
	for _, r := range []rune{'a', '0', '.', 0x200b, 0x180e, 0x00b7} {
		if IsPythonSpace(r) {
			t.Errorf("IsPythonSpace(%#x) = true, want false", r)
		}
	}
}

// TestPythonSpaceClassMatchesPredicate keeps the regexp class and the scanner
// predicate one set: a rune either is Python whitespace in both or in neither.
func TestPythonSpaceClassMatchesPredicate(t *testing.T) {
	space := regexp.MustCompile(`^` + PythonSpaceClass + `$`)
	nonSpace := regexp.MustCompile(`^` + PythonNonSpaceClass + `$`)
	for r := rune(0); r <= 0x3100; r++ {
		if r >= 0xd800 && r <= 0xdfff {
			continue
		}
		want := IsPythonSpace(r)
		if got := space.MatchString(string(r)); got != want {
			t.Fatalf("PythonSpaceClass matched %#x = %v, IsPythonSpace = %v", r, got, want)
		}
		if got := nonSpace.MatchString(string(r)); got == want {
			t.Fatalf("PythonNonSpaceClass matched %#x = %v, IsPythonSpace = %v", r, got, want)
		}
	}
}

func TestPythonWordClass(t *testing.T) {
	word := regexp.MustCompile(`^` + PythonWordClass + `+$`)
	for _, s := range []string{"abc", "_x1", "Ünïcode", "١٢٣", "m²"} {
		if !word.MatchString(s) {
			t.Errorf("PythonWordClass did not match %q", s)
		}
	}
	for _, s := range []string{"a-b", "a b", "a.b"} {
		if word.MatchString(s) {
			t.Errorf("PythonWordClass matched %q", s)
		}
	}
}

func TestPythonStrip(t *testing.T) {
	cases := []struct{ in, want string }{
		{"\x1f x \x1c", "x"},
		{"\t\n\v\f\r a \r\n", "a"},
		{"\x1c\x1d\x1e\x1fa\x1c", "a"},
		{"\u00a0a\u00a0", "a"},
		{"\u2003a\u2003", "a"},
		{"　y ", "y"},
		{"", ""},
		{"   ", ""},
		{"a b", "a b"},
	}
	for _, c := range cases {
		if got := PythonStrip(c.in); got != c.want {
			t.Errorf("PythonStrip(%q) = %q, want %q", c.in, got, c.want)
		}
	}
	if got := PythonLStrip("\x1c a "); got != "a " {
		t.Errorf("PythonLStrip = %q", got)
	}
	if got := PythonRStrip(" a\x1c"); got != " a" {
		t.Errorf("PythonRStrip = %q", got)
	}
}

func TestPythonFields(t *testing.T) {
	got := PythonFields("  a b\x1fc ")
	want := []string{"a", "b", "c"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("PythonFields = %#v, want %#v", got, want)
	}
	if got := PythonFields("   "); len(got) != 0 {
		t.Errorf("PythonFields on whitespace = %#v, want empty", got)
	}
}

func TestPythonSplitLines(t *testing.T) {
	cases := []struct {
		in   string
		want []string
	}{
		{"a\vb\fc\u001cd\u0085e f", []string{"a", "b", "c", "d", "e f"}},
		{"a\r\nb\rc\nd\n", []string{"a", "b", "c", "d"}},
		{"a\n\n", []string{"a", ""}},
		{"", nil},
		{"one", []string{"one"}},
		{"a b c", []string{"a", "b", "c"}},
		// The unit separator is not a Python line break.
		{"a\x1fb", []string{"a\x1fb"}},
	}
	for _, c := range cases {
		if got := PythonSplitLines(c.in); !reflect.DeepEqual(got, c.want) {
			t.Errorf("PythonSplitLines(%q) = %#v, want %#v", c.in, got, c.want)
		}
	}
}

// TestPythonRepr compares against the output of CPython's repr(), recorded by
// running it.
func TestPythonRepr(t *testing.T) {
	cases := []struct {
		in   any
		want string
	}{
		{"plain", `'plain'`},
		{"it's", `"it's"`},
		{`say "hi"`, `'say "hi"'`},
		{`both ' and "`, `'both \' and "'`},
		{"both'\"q", `'both\'"q'`},
		{"tab\there", `'tab\there'`},
		{"nl\nhere", `'nl\nhere'`},
		{"cr\rhere", `'cr\rhere'`},
		{"nbsp\u00a0x", `'nbsp\xa0x'`},
		{"\u0085nel", `'\x85nel'`},
		{"\u001fus", `'\x1fus'`},
		{"\u2028sep", `'\u2028sep'`},
		{"\U0001f600", `'😀'`},
		{"\x00", `'\x00'`},
		{"\x7f", `'\x7f'`},
		{"a\x1cb", `'a\x1cb'`},
		{"\u200b zero width", `'\u200b zero width'`},
		{"héllo", `'héllo'`},
		{"café", `'café'`},
		{"m²", `'m²'`},
		{`\back`, `'\\back'`},
		{nil, "None"},
		{true, "True"},
		{false, "False"},
		{3, "3"},
		{int64(-7), "-7"},
		{2.0, "2.0"},
		{2.5, "2.5"},
		{[]any{1, "a", nil, true, 2.5}, `[1, 'a', None, True, 2.5]`},
		{map[string]any{"b": 1, "a": "x"}, `{'a': 'x', 'b': 1}`},
		{[]map[string]any{{"k": 1}}, `[{'k': 1}]`},
		{map[string]any{}, "{}"},
		{[]any{}, "[]"},
	}
	for _, c := range cases {
		if got := PythonRepr(c.in); got != c.want {
			t.Errorf("PythonRepr(%#v) = %s, want %s", c.in, got, c.want)
		}
	}
}

// TestPythonReprUnassigned covers the one rule a Cn code point exercises:
// Python calls an unassigned code point unprintable, so repr escapes it.
func TestPythonReprUnassigned(t *testing.T) {
	if got := PythonRepr("\u0378"); got != `'\u0378'` {
		t.Errorf("PythonRepr of an unassigned code point = %s, want '\\u0378'", got)
	}
}

func TestPythonStr(t *testing.T) {
	cases := []struct {
		in   any
		want string
	}{
		{nil, "None"},
		{"text", "text"},
		{"", ""},
		{true, "True"},
		{false, "False"},
		{0, "0"},
		{int64(12), "12"},
		{2.0, "2.0"},
	}
	for _, c := range cases {
		if got := PythonStr(c.in); got != c.want {
			t.Errorf("PythonStr(%#v) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestPythonStrOrEmpty(t *testing.T) {
	cases := []struct {
		in   any
		want string
	}{
		{nil, ""},
		{"", ""},
		{"text", "text"},
		{false, ""},
		{true, "True"},
		{0, ""},
		{int64(0), ""},
		{int64(12), "12"},
		{0.0, ""},
		{2.5, "2.5"},
		{[]any{}, ""},
		{map[string]any{}, ""},
		{[]map[string]any{}, ""},
	}
	for _, c := range cases {
		if got := PythonStrOrEmpty(c.in); got != c.want {
			t.Errorf("PythonStrOrEmpty(%#v) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestPythonTypeName(t *testing.T) {
	cases := []struct {
		in   any
		want string
	}{
		{nil, "NoneType"},
		{"s", "str"},
		{true, "bool"},
		{int64(1), "int"},
		{2, "int"},
		{1.5, "float"},
		{[]any{}, "list"},
		{[]map[string]any{}, "list"},
		{map[string]any{}, "dict"},
		{time.Time{}, "datetime"},
	}
	for _, c := range cases {
		if got := PythonTypeName(c.in); got != c.want {
			t.Errorf("PythonTypeName(%#v) = %q, want %q", c.in, got, c.want)
		}
	}
}
