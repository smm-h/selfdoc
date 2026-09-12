package prose

import (
	"strings"
	"unicode"
)

// isSpace reports whether r is whitespace by Python's str.isspace()
// definition, which the ported code was written against.
//
// It is [unicode.IsSpace] plus the four information separators U+001C through
// U+001F, which Python counts as whitespace and Go does not. The four never
// appear in a Markdown document in practice; reproducing them is what keeps
// "same behavior" literal rather than approximate.
func isSpace(r rune) bool {
	if r >= 0x1c && r <= 0x1f {
		return true
	}
	return unicode.IsSpace(r)
}

// trimSpace is Python's str.strip() with no argument: it trims the runs of
// [isSpace] runes from both ends of s.
func trimSpace(s string) string {
	return strings.TrimFunc(s, isSpace)
}
