package registry

import (
	"os"
	"sort"
	"strings"
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
