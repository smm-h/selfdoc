package golang

import (
	"strings"
	"unicode"
)

// isPySpace reports whether r is whitespace by Python's str.isspace rule, which
// is Unicode whitespace plus the four ASCII separator control characters. Go's
// own unicode.IsSpace omits the separators.
func isPySpace(r rune) bool {
	return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f)
}

// pyStrip is Python's str.strip() with no argument.
func pyStrip(s string) string { return strings.TrimFunc(s, isPySpace) }

// pyRStrip is Python's str.rstrip() with no argument.
func pyRStrip(s string) string { return strings.TrimRightFunc(s, isPySpace) }

// splitWhitespaceOnce is Python's str.split(None, 1): leading whitespace is
// skipped, the split happens at the first run of whitespace, and the remainder
// keeps whatever trailing whitespace it had.
func splitWhitespaceOnce(s string) []string {
	rest := strings.TrimLeftFunc(s, isPySpace)
	if rest == "" {
		return nil
	}
	for i, r := range rest {
		if isPySpace(r) {
			tail := strings.TrimLeftFunc(rest[i:], isPySpace)
			if tail == "" {
				return []string{rest[:i]}
			}
			return []string{rest[:i], tail}
		}
	}
	return []string{rest}
}
