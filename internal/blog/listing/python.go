package listing

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
	"unicode"

	"github.com/smm-h/selfdoc/internal/util"
)

// pyStr reproduces the Python idiom str(value or "") the declaration reader
// applies to every optional string key: an absent or falsy value becomes the
// empty string, and anything else becomes its str() rendering.
//
// A list or a table renders through fmt.Sprint rather than Python's own
// container repr. Both are rejected by the key checks before any refusal could
// quote one, so the difference cannot reach a message.
func pyStr(value any) string {
	switch typed := value.(type) {
	case nil:
		return ""
	case string:
		return typed
	case bool:
		if typed {
			return "True"
		}
		return ""
	case int64:
		if typed == 0 {
			return ""
		}
		return strconv.FormatInt(typed, 10)
	case float64:
		if typed == 0 {
			return ""
		}
		return util.PythonFloatRepr(typed)
	case []any:
		if len(typed) == 0 {
			return ""
		}
		return fmt.Sprint(typed)
	case map[string]any:
		if len(typed) == 0 {
			return ""
		}
		return fmt.Sprint(typed)
	default:
		return fmt.Sprint(typed)
	}
}

// pyRepr renders value the way Python's repr() does, because the refusals
// quote the declarations they name and the quoting is part of the message.
func pyRepr(value any) string {
	switch typed := value.(type) {
	case nil:
		return "None"
	case string:
		return pyReprString(typed)
	case bool:
		if typed {
			return "True"
		}
		return "False"
	case int64:
		return strconv.FormatInt(typed, 10)
	case float64:
		return util.PythonFloatRepr(typed)
	case []any:
		parts := make([]string, 0, len(typed))
		for _, item := range typed {
			parts = append(parts, pyRepr(item))
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case map[string]any:
		keys := make([]string, 0, len(typed))
		for key := range typed {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		parts := make([]string, 0, len(keys))
		for _, key := range keys {
			parts = append(parts, pyReprString(key)+": "+pyRepr(typed[key]))
		}
		return "{" + strings.Join(parts, ", ") + "}"
	default:
		return fmt.Sprint(typed)
	}
}

// pyReprString quotes s the way Python's repr(str) does: single quotes unless
// the text holds a single quote and no double quote, a backslash escape for
// the backslash and the chosen quote, the short escapes for the newline,
// carriage return and tab, and a numeric escape for every other
// non-printable character.
func pyReprString(s string) string {
	quote := byte('\'')
	if strings.Contains(s, "'") && !strings.Contains(s, `"`) {
		quote = '"'
	}
	var out strings.Builder
	out.WriteByte(quote)
	for _, r := range s {
		switch {
		case r == rune(quote):
			out.WriteByte('\\')
			out.WriteRune(r)
		case r == '\\':
			out.WriteString(`\\`)
		case r == '\n':
			out.WriteString(`\n`)
		case r == '\r':
			out.WriteString(`\r`)
		case r == '\t':
			out.WriteString(`\t`)
		case r < 0x20 || r == 0x7f:
			out.WriteString(fmt.Sprintf(`\x%02x`, r))
		case r > 0x7f && !unicode.IsPrint(r):
			if r > 0xffff {
				out.WriteString(fmt.Sprintf(`\U%08x`, r))
			} else {
				out.WriteString(fmt.Sprintf(`\u%04x`, r))
			}
		default:
			out.WriteRune(r)
		}
	}
	out.WriteByte(quote)
	return out.String()
}

// escape escapes text for insertion into HTML, reproducing Python's
// html.escape(text, quote=True): the ampersand, the angle brackets, the double
// quote as &quot; and the apostrophe as &#x27;.
//
// This is deliberately not util.EscapeHTML, which leaves the apostrophe alone
// because the page emitters it serves were written against a private escaper
// that does. The listing's cards were written against the standard library's
// function, and a curated blurb carrying an apostrophe is the ordinary case.
func escape(text string) string {
	text = strings.ReplaceAll(text, "&", "&amp;")
	text = strings.ReplaceAll(text, "<", "&lt;")
	text = strings.ReplaceAll(text, ">", "&gt;")
	text = strings.ReplaceAll(text, `"`, "&quot;")
	return strings.ReplaceAll(text, "'", "&#x27;")
}
