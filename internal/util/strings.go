package util

import (
	"strings"
	"time"
)

// EscapeHTML escapes s for insertion into HTML text or a double-quoted
// attribute value: "&", "<", ">" and the double quote, in that order.
//
// The apostrophe is deliberately NOT escaped, so the output matches Python's
// html.escape(s, quote=True) rather than Go's html.EscapeString, which also
// rewrites "'" to "&#39;" and would change every rendered page.
func EscapeHTML(s string) string {
	s = strings.ReplaceAll(s, "&", "&amp;")
	s = strings.ReplaceAll(s, "<", "&lt;")
	s = strings.ReplaceAll(s, ">", "&gt;")
	return strings.ReplaceAll(s, `"`, "&quot;")
}

// FormatDateLong renders t as Python's strftime("%B %-d, %Y") does in the C
// locale: the English month name, the day of the month without a leading zero,
// a comma, and the four-digit year -- "September 1, 2026".
func FormatDateLong(t time.Time) string {
	return t.Format("January 2, 2006")
}

// ResolveDirectivePath resolves a directive's path attribute against the
// project's base directory.
//
// This is the one place filesystem directive paths are resolved, so every
// directive that reads a path attribute behaves identically and any future
// normalization or sandboxing has a single home.
func ResolveDirectivePath(baseDir, path string) string {
	return PathJoin(baseDir, path)
}

// PathJoin reproduces Python's posixpath.join, which is what every ported call
// site was written against.
//
// It differs from [path/filepath.Join] in two ways that reach real documents:
// an absolute later element REPLACES everything before it instead of being
// appended, and the result is never cleaned, so "docs" joined with "../x" stays
// "docs/../x" rather than collapsing to "x". Use [path/filepath.Join] for a new
// path that no Python call site constrains.
func PathJoin(parts ...string) string {
	if len(parts) == 0 {
		return ""
	}
	joined := parts[0]
	for _, part := range parts[1:] {
		switch {
		case strings.HasPrefix(part, "/"):
			joined = part
		case joined == "" || strings.HasSuffix(joined, "/"):
			joined += part
		default:
			joined += "/" + part
		}
	}
	return joined
}
