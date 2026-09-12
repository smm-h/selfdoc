package address

import (
	"fmt"
	"strings"
	"unicode"
)

// pythonRepr quotes s the way Python's repr() of a string does.
//
// Two of the validation errors interpolate a path with Python's !r
// conversion, so reproducing repr is what keeps those messages byte for byte.
// The rules: single quotes, switching to double quotes when the value contains
// a single quote and no double quote; backslash, the chosen quote, newline,
// carriage return and tab take their short escapes; and every character
// Python calls unprintable -- the Other and Separator categories, minus the
// ASCII space -- becomes \xNN, \uXXXX or \UXXXXXXXX by code-point width.
func pythonRepr(s string) string {
	quote := byte('\'')
	if strings.Contains(s, "'") && !strings.Contains(s, `"`) {
		quote = '"'
	}
	var b strings.Builder
	b.WriteByte(quote)
	for _, r := range s {
		switch {
		case r == rune(quote) || r == '\\':
			b.WriteByte('\\')
			b.WriteRune(r)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r == '\t':
			b.WriteString(`\t`)
		case !pythonIsPrintable(r):
			switch {
			case r < 0x100:
				fmt.Fprintf(&b, `\x%02x`, r)
			case r < 0x10000:
				fmt.Fprintf(&b, `\u%04x`, r)
			default:
				fmt.Fprintf(&b, `\U%08x`, r)
			}
		default:
			b.WriteRune(r)
		}
	}
	b.WriteByte(quote)
	return b.String()
}

// pythonIsPrintable reports whether r is printable by Python's definition:
// everything except the Unicode Other and Separator categories, with the ASCII
// space as the one exception that is printable.
func pythonIsPrintable(r rune) bool {
	if r == ' ' {
		return true
	}
	return !unicode.In(r, unicode.C, unicode.Z)
}
