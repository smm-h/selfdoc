package html

import (
	"strings"
	"unicode/utf8"
)

// pySpaceClass is the character class Python's re module gives `\s` when it
// matches a str, spelled for Go's regexp engine.
//
// Go's own `\s` is the five ASCII characters plus the space, so a regex
// ported verbatim would stop recognizing the vertical tab, the information
// separators, NEL, the no-break space and the Unicode space separators --
// every one of which turns up in prose that reaches this package through a
// pasted document. Patterns that read prose use this class; patterns that
// read markup this package itself emitted use Go's `\s`, because that
// markup is ASCII by construction.
const pySpaceClass = "[\\t\\n\\v\\f\\r \\x{1c}-\\x{1f}\\x{85}\\x{a0}\\x{1680}\\x{2000}-\\x{200a}\\x{2028}\\x{2029}\\x{202f}\\x{205f}\\x{3000}]"

// isPySpace reports whether r is whitespace to Python -- what str.isspace
// answers, which is what str.strip removes.
func isPySpace(r rune) bool {
	switch r {
	case '\t', '\n', '\v', '\f', '\r', ' ',
		0x1c, 0x1d, 0x1e, 0x1f, 0x85, 0xa0, 0x1680,
		0x2028, 0x2029, 0x202f, 0x205f, 0x3000:
		return true
	}
	return r >= 0x2000 && r <= 0x200a
}

// pyStrip removes leading and trailing whitespace the way Python's
// str.strip() does.
func pyStrip(s string) string { return strings.TrimFunc(s, isPySpace) }

// pyCapitalize renders s the way Python's str.capitalize() does: the first
// character upper-cased and every later one lower-cased.
func pyCapitalize(s string) string {
	if s == "" {
		return ""
	}
	r, size := utf8.DecodeRuneInString(s)
	return strings.ToUpper(string(r)) + strings.ToLower(s[size:])
}

// runesBack returns the offset n runes before pos in s, clamped at 0.
//
// Python's slicing counts characters, so a lookback window of "200
// characters" is not 200 bytes once a page carries anything outside ASCII.
func runesBack(s string, pos, n int) int {
	i := pos
	for k := 0; k < n && i > 0; k++ {
		_, size := utf8.DecodeLastRuneInString(s[:i])
		i -= size
	}
	return i
}
