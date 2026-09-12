package registry

import (
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode"

	"github.com/smm-h/selfdoc/internal/util"
)

// expandUser reproduces Python's os.path.expanduser for the two spellings a
// hand-written registry uses: a bare "~" and a "~/..." prefix, both replaced
// by the home directory the environment names. A path is returned unchanged
// when there is no home directory to substitute, as Python leaves it, and a
// "~user" spelling is left alone too -- Python resolves it through the
// password database, and no registry in the fleet writes one.
func expandUser(path string) string {
	if path != "~" && !strings.HasPrefix(path, "~"+string(os.PathSeparator)) {
		return path
	}
	home := os.Getenv("HOME")
	if home == "" {
		resolved, err := os.UserHomeDir()
		if err != nil {
			return path
		}
		home = resolved
	}
	if path == "~" {
		return home
	}
	return home + path[1:]
}

// unknownKeys returns the keys of table that allowed does not name, sorted.
func unknownKeys(table map[string]any, allowed []string) []string {
	known := make(map[string]bool, len(allowed))
	for _, key := range allowed {
		known[key] = true
	}
	unknown := make([]string, 0)
	for key := range table {
		if !known[key] {
			unknown = append(unknown, key)
		}
	}
	sort.Strings(unknown)
	return unknown
}

// asList normalizes a decoded TOML array into a slice of elements. The decoder
// answers an array of tables as []map[string]any and every other array as
// []any, and both spell the document shape Python's tomllib returns as one
// list.
func asList(value any) ([]any, bool) {
	switch typed := value.(type) {
	case []any:
		return typed, true
	case []map[string]any:
		items := make([]any, 0, len(typed))
		for _, item := range typed {
			items = append(items, item)
		}
		return items, true
	default:
		return nil, false
	}
}

// pyTypeName renders the name Python's type(value).__name__ gives a
// tomllib-decoded value, because two refusals report the type they were handed
// instead of the one they wanted.
func pyTypeName(value any) string {
	switch value.(type) {
	case nil:
		return "NoneType"
	case string:
		return "str"
	case bool:
		return "bool"
	case int64:
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
		return fmt.Sprintf("%T", value)
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
	case []map[string]any:
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
