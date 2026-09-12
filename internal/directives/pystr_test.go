package directives

import "testing"

// TestPyRepr pins the ported repr against real CPython output. The expected
// column is what `python3 -c 'print(repr(v))'` printed for each input, because
// the "Unexpected line inside directive block" message interpolates a repr and
// must read the same as the surface it replaces.
func TestPyRepr(t *testing.T) {
	tests := []struct {
		in   string
		want string
	}{
		{"abc", `'abc'`},
		{"it's", `"it's"`},
		{`say "hi"`, `'say "hi"'`},
		{`both ' and "`, `'both \' and "'`},
		{"tab\there", `'tab\there'`},
		{"nl\nhere", `'nl\nhere'`},
		{`back\slash`, `'back\\slash'`},
		{"héllo", `'héllo'`},
		{"\x00null", `'\x00null'`},
		{"\x7f", `'\x7f'`},
		{"a\x1cb", `'a\x1cb'`},
		{"emoji \U0001F600", `'emoji 😀'`},
		{"\u200b zero width", `'\u200b zero width'`},
		{`:@: src="foo"`, `':@: src="foo"'`},
		{"::: body without separator", `'::: body without separator'`},
	}
	for _, tc := range tests {
		if got := pyRepr(tc.in); got != tc.want {
			t.Errorf("pyRepr(%q) = %s, want %s", tc.in, got, tc.want)
		}
	}
}

// TestPyStrip covers the characters Python's str.strip trims that Go's
// strings.TrimSpace does not: the four information separators.
func TestPyStrip(t *testing.T) {
	tests := []struct {
		in   string
		want string
	}{
		{"", ""},
		{"  a  ", "a"},
		{"\t\n\v\f\r a \r\n", "a"},
		{"\x1c\x1d\x1e\x1fa\x1c", "a"},
		{"\u00a0a\u00a0", "a"},
		{"\u2003a\u2003", "a"},
		{"a b", "a b"},
	}
	for _, tc := range tests {
		if got := pyStrip(tc.in); got != tc.want {
			t.Errorf("pyStrip(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}
