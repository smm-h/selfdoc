package directives

import (
	"fmt"
	"strings"
	"unicode"
)

// pySpaceClass is the regexp character class Python's `\s` denotes for a str
// pattern, and pyNotSpaceClass is its `\S`.
//
// Go's own `\s` is the five ASCII whitespace characters and nothing else, so
// using it would make a line separated by a non-breaking space parse as one
// token where Python split it in two. The members are Python's
// str.isspace(): the C0 whitespace run, the four information separators, the
// space, NEL, NBSP, and the Unicode space/line/paragraph separators.
const (
	pySpaceClass    = `[\t-\r\x{1c}-\x{1f} \x{85}\x{a0}\p{Zs}\p{Zl}\p{Zp}]`
	pyNotSpaceClass = `[^\t-\r\x{1c}-\x{1f} \x{85}\x{a0}\p{Zs}\p{Zl}\p{Zp}]`
)

// pyWordClass is the regexp character class Python's `\w` denotes for a str
// pattern: a Unicode letter, a Unicode number, or an underscore. Go's own
// `\w` is ASCII-only.
const pyWordClass = `[\p{L}\p{N}_]`

// isPySpace reports whether r is whitespace to Python's str.isspace, the
// predicate str.strip uses.
func isPySpace(r rune) bool {
	switch r {
	case '\t', '\n', '\v', '\f', '\r', 0x1c, 0x1d, 0x1e, 0x1f, ' ', 0x85, 0xa0:
		return true
	}
	return unicode.Is(unicode.Zs, r) || unicode.Is(unicode.Zl, r) ||
		unicode.Is(unicode.Zp, r)
}

// pyStrip reproduces Python's str.strip(): both ends trimmed of every
// character str.isspace accepts.
//
// strings.TrimSpace is close but not the same -- it trims what
// unicode.IsSpace accepts, which omits the four information separators
// (U+001C-U+001F) Python trims.
func pyStrip(s string) string {
	return strings.TrimFunc(s, isPySpace)
}

// pyPrintable reports whether r is printable to Python's repr, which renders
// every other character as an escape.
//
// Python's rule is "not in category Cc, Cf, Cs, Co, Cn, Zl, Zp or Zs, except
// that the space is printable". Go's unicode.IsGraphic is the letters, marks,
// numbers, punctuation, symbols and Zs, so subtracting Zs and adding the
// space back gives Python's set.
func pyPrintable(r rune) bool {
	if r == ' ' {
		return true
	}
	return unicode.IsGraphic(r) && !unicode.Is(unicode.Zs, r)
}

// pyRepr renders s the way Python's repr(str) does -- the spelling the ported
// error messages interpolate with {value!r}.
//
// Single quotes, unless s contains a single quote and no double quote, in
// which case double quotes. Backslash, the chosen quote and the three short
// escapes are escaped by name; every other non-printable character becomes
// \xXX, \uXXXX or \UXXXXXXXX by code point width.
func pyRepr(s string) string {
	quote := byte('\'')
	if strings.ContainsRune(s, '\'') && !strings.ContainsRune(s, '"') {
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
		case r < 0x20 || r == 0x7f:
			fmt.Fprintf(&b, `\x%02x`, r)
		case r < 0x7f:
			b.WriteRune(r)
		case !pyPrintable(r):
			switch {
			case r <= 0xff:
				fmt.Fprintf(&b, `\x%02x`, r)
			case r <= 0xffff:
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
