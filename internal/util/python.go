package util

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode"
)

// The character classes below stand in for Python's \s, \S and \w in a ported
// regular expression. Go's versions are ASCII-only where Python's are
// Unicode-aware for a str pattern, so a pattern copied across unchanged would
// quietly stop matching a no-break space or a non-Latin identifier.
//
// PythonSpaceClass denotes the same set of runes [IsPythonSpace] accepts, so a
// scanner and a regexp that both claim to split on Python whitespace agree.
const (
	// PythonSpaceChars are the members of Python's \s, without the enclosing
	// brackets: the ASCII whitespace characters, the four ASCII information
	// separators, and the Unicode whitespace code points. A pattern that
	// composes whitespace with further characters into one class needs the
	// members, which a nested class cannot express.
	PythonSpaceChars = `\t\n\v\f\r \x{001c}-\x{001f}\x{0085}\x{00a0}\x{1680}\x{2000}-\x{200a}\x{2028}\x{2029}\x{202f}\x{205f}\x{3000}`

	// PythonWordChars are the members of Python's \w where it matches an
	// identifier character, without the enclosing brackets: a letter, a digit
	// or an underscore, in any script.
	PythonWordChars = `\p{L}\p{N}_`

	// PythonSpaceClass is Python's \s.
	PythonSpaceClass = "[" + PythonSpaceChars + "]"

	// PythonNonSpaceClass is Python's \S, the complement of
	// [PythonSpaceClass].
	PythonNonSpaceClass = "[^" + PythonSpaceChars + "]"

	// PythonWordClass is Python's \w where it matches an identifier
	// character.
	PythonWordClass = "[" + PythonWordChars + "]"
)

// IsPythonSpace reports whether r is whitespace by Python's str.isspace rule,
// the predicate str.strip and str.split use.
//
// It is [unicode.IsSpace] plus the four information separators U+001C through
// U+001F, which Python counts as whitespace and Go does not.
func IsPythonSpace(r rune) bool {
	return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f)
}

// PythonStrip reproduces Python's str.strip() with no argument: both ends
// trimmed of every character [IsPythonSpace] accepts.
//
// [strings.TrimSpace] is close but not the same -- it trims what
// [unicode.IsSpace] accepts, which omits the four information separators
// Python trims.
func PythonStrip(s string) string { return strings.TrimFunc(s, IsPythonSpace) }

// PythonLStrip reproduces Python's str.lstrip() with no argument.
func PythonLStrip(s string) string { return strings.TrimLeftFunc(s, IsPythonSpace) }

// PythonRStrip reproduces Python's str.rstrip() with no argument.
func PythonRStrip(s string) string { return strings.TrimRightFunc(s, IsPythonSpace) }

// PythonFields reproduces Python's str.split() with no argument: s split on
// runs of [IsPythonSpace] runes, with no empty items, so leading and trailing
// whitespace contribute nothing.
func PythonFields(s string) []string { return strings.FieldsFunc(s, IsPythonSpace) }

// pythonLineBreaks are the characters Python's str.splitlines() ends a line
// on. The full set is reproduced because a split feeds hashes and rendered
// documents alike, so a body carrying a form feed must normalize to the same
// bytes every time. U+001F is deliberately absent: Python's splitlines takes
// the first three information separators and not the unit separator.
var pythonLineBreaks = map[rune]bool{
	'\n': true, '\r': true, '\v': true, '\f': true,
	0x1c: true, 0x1d: true, 0x1e: true, 0x85: true,
	0x2028: true, 0x2029: true,
}

// PythonSplitLines splits text the way Python's str.splitlines() does: on
// every character in pythonLineBreaks, counting "\r\n" once, and with a
// trailing terminator producing no final empty line.
func PythonSplitLines(text string) []string {
	var lines []string
	var current strings.Builder
	runes := []rune(text)
	for index := 0; index < len(runes); index++ {
		r := runes[index]
		if !pythonLineBreaks[r] {
			current.WriteRune(r)
			continue
		}
		if r == '\r' && index+1 < len(runes) && runes[index+1] == '\n' {
			index++
		}
		lines = append(lines, current.String())
		current.Reset()
	}
	if current.Len() > 0 {
		lines = append(lines, current.String())
	}
	return lines
}

// PythonRepr renders v the way Python's repr() does -- the spelling every
// ported diagnostic that interpolates {value!r} was written against.
//
// A string is quoted by [pythonReprString]. A mapping's keys are rendered in
// sorted order rather than insertion order: Go maps carry no insertion order,
// and a diagnostic that names an object has to be reproducible. A value of a
// type Python has no counterpart for falls back to [fmt.Sprint].
func PythonRepr(v any) string {
	switch t := v.(type) {
	case nil:
		return "None"
	case bool:
		if t {
			return "True"
		}
		return "False"
	case string:
		return pythonReprString(t)
	case int:
		return strconv.Itoa(t)
	case int64:
		return strconv.FormatInt(t, 10)
	case float64:
		return PythonFloatRepr(t)
	case []any:
		parts := make([]string, 0, len(t))
		for _, item := range t {
			parts = append(parts, PythonRepr(item))
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case []map[string]any:
		parts := make([]string, 0, len(t))
		for _, item := range t {
			parts = append(parts, PythonRepr(item))
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case map[string]any:
		keys := make([]string, 0, len(t))
		for key := range t {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		parts := make([]string, 0, len(keys))
		for _, key := range keys {
			parts = append(parts, pythonReprString(key)+": "+PythonRepr(t[key]))
		}
		return "{" + strings.Join(parts, ", ") + "}"
	default:
		return fmt.Sprint(v)
	}
}

// pythonReprString quotes s the way Python's repr(str) does: single quotes,
// switching to double quotes when the text carries a single quote and no
// double quote; a backslash escape for the backslash and the chosen quote;
// the short escapes for the newline, carriage return and tab; and a numeric
// escape for every other character Python calls unprintable -- \xNN below
// U+0100, \uXXXX below U+10000, \UXXXXXXXX above it.
//
// [unicode.IsPrint] is Python's str.isprintable: the letters, marks, numbers,
// punctuation and symbols plus the ASCII space, which is the complement of
// Python's "Other or Separator, except the space" rule.
func pythonReprString(s string) string {
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
		case r == '\t':
			b.WriteString(`\t`)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case unicode.IsPrint(r):
			b.WriteRune(r)
		case r < 0x100:
			fmt.Fprintf(&b, `\x%02x`, r)
		case r < 0x10000:
			fmt.Fprintf(&b, `\u%04x`, r)
		default:
			fmt.Fprintf(&b, `\U%08x`, r)
		}
	}
	b.WriteByte(quote)
	return b.String()
}

// PythonStr renders v the way Python's str() -- and therefore an f-string
// interpolation -- renders it.
//
// A container renders through [fmt.Sprint] rather than Python's own container
// repr, which is what every ported call site did: the containers that reach a
// str() interpolation are rejected by a type check before any message could
// quote one, so the difference cannot reach a document. A value that really is
// a container to be shown goes through [PythonRepr].
func PythonStr(v any) string {
	switch t := v.(type) {
	case nil:
		return "None"
	case bool:
		if t {
			return "True"
		}
		return "False"
	case string:
		return t
	case int:
		return strconv.Itoa(t)
	case int64:
		return strconv.FormatInt(t, 10)
	case float64:
		return PythonFloatRepr(t)
	default:
		return fmt.Sprint(v)
	}
}

// PythonStrOrEmpty renders v the way Python's str(value or "") idiom does: a
// falsy value -- an absent key, a null, a false, a zero, an empty string, an
// empty container -- becomes the empty string, and anything else becomes its
// [PythonStr] rendering.
//
// Every optional string key of a config or a frontmatter block was read
// through that idiom, so an absent key and a declared empty one are the same
// answer.
func PythonStrOrEmpty(v any) string {
	switch t := v.(type) {
	case nil:
		return ""
	case bool:
		if !t {
			return ""
		}
	case string:
		return t
	case int:
		if t == 0 {
			return ""
		}
	case int64:
		if t == 0 {
			return ""
		}
	case float64:
		if t == 0 {
			return ""
		}
	case []any:
		if len(t) == 0 {
			return ""
		}
	case []map[string]any:
		if len(t) == 0 {
			return ""
		}
	case map[string]any:
		if len(t) == 0 {
			return ""
		}
	}
	return PythonStr(v)
}

// PythonTypeName renders the name Python's type(value).__name__ gives a
// decoded JSON or TOML value, for a refusal that reports the type it was
// handed instead of the one it wanted.
func PythonTypeName(v any) string {
	switch v.(type) {
	case nil:
		return "NoneType"
	case string:
		return "str"
	case bool:
		return "bool"
	case int, int64:
		return "int"
	case float64:
		return "float"
	case []any, []map[string]any:
		return "list"
	case map[string]any:
		return "dict"
	case time.Time:
		return "datetime"
	default:
		return fmt.Sprintf("%T", v)
	}
}
