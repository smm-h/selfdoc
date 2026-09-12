package check

import (
	"os"
	"sort"
)

// sortedKeys returns a map's keys in sorted order, which is the order every
// page-by-page pass walks a docs dictionary in.
func sortedKeys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for key := range m {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

// configString reads a string config key, answering fallback when the key is
// absent. A key present but holding something other than a string answers the
// empty string, which is what the Python's own string operations on it
// produced.
func configString(config map[string]any, key, fallback string) string {
	raw, present := config[key]
	if !present {
		return fallback
	}
	value, _ := raw.(string)
	return value
}

// configDict reads a dict config key. An absent key, a null and a value of
// another type all answer nil -- Python's “config.get(key) or {}“.
func configDict(config map[string]any, key string) map[string]any {
	value, _ := config[key].(map[string]any)
	return value
}

// configList reads a list config key, answering nil for an absent key, a null
// and a value of another type -- Python's “config.get(key) or []“.
func configList(config map[string]any, key string) []any {
	value, _ := config[key].([]any)
	return value
}

// stringList reads a list-of-strings value, skipping any entry that is not a
// string.
func stringList(raw any) []string {
	items, _ := raw.([]any)
	result := make([]string, 0, len(items))
	for _, item := range items {
		if value, isString := item.(string); isString {
			result = append(result, value)
		}
	}
	return result
}

// lineOf is a diagnostic's line as the registry's constructor takes it.
func lineOf(line int) *int { return &line }

// isFile reports whether path is an existing regular file, the question
// Python's os.path.isfile answers.
func isFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}

// isDir reports whether path is an existing directory, the question Python's
// os.path.isdir answers.
func isDir(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}
