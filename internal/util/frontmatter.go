package util

import (
	"regexp"
	"strconv"
	"strings"
)

// Frontmatter is the parsed metadata block of a Markdown template, in the
// hand-rolled dialect selfdoc has always used. Values are one of string, bool,
// int64, float64 or []string.
type Frontmatter = map[string]any

// ParseFrontmatter parses the YAML-like frontmatter of a Markdown document.
//
// When text starts with "---", the key/value pairs up to the next line that is
// exactly "---" after trimming become the metadata and everything after it
// becomes the body, with the body's leading blank lines removed. When there is
// no frontmatter -- text does not start with "---", or the closing fence is
// missing -- the metadata is empty and the body is text unchanged.
//
// The dialect is deliberately not YAML, and existing documents depend on every
// rule below:
//
//   - A line is split on its FIRST colon; a line with no colon is skipped, as
//     is an empty line and a line starting with "#".
//   - Key and value are both trimmed of surrounding whitespace.
//   - One pair of wrapping quotes (either ' or ") is stripped from the value
//     BEFORE any other interpretation, so `tags: "[a, b]"` is still a list and
//     `draft: "true"` is still a boolean.
//   - `[a, b, c]` becomes a []string of the trimmed, non-empty items.
//   - Otherwise a value equal to "true" or "false" case-insensitively becomes a
//     bool; else a Python-integer literal becomes an int64; else a
//     Python-float literal becomes a float64; else the value stays a string.
//   - There is no nesting, no multi-line value and no comment stripping inside
//     a value.
//
// The third return value is the number of source lines consumed before the
// body's first line -- the fence, the metadata lines, the closing fence and any
// blank lines stripped after it -- so a caller can map a body line number back
// to its line in text. It is zero when there is no frontmatter.
func ParseFrontmatter(text string) (Frontmatter, string, int) {
	if !strings.HasPrefix(text, "---") {
		return Frontmatter{}, text, 0
	}
	lines := strings.Split(text, "\n")
	end := -1
	for idx := 1; idx < len(lines); idx++ {
		if strings.TrimSpace(lines[idx]) == "---" {
			end = idx
			break
		}
	}
	if end == -1 {
		return Frontmatter{}, text, 0
	}

	metadata := Frontmatter{}
	for _, raw := range lines[1:end] {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		colon := strings.Index(line, ":")
		if colon == -1 {
			continue
		}
		key := strings.TrimSpace(line[:colon])
		metadata[key] = frontmatterValue(strings.TrimSpace(line[colon+1:]))
	}

	rest := strings.Join(lines[end+1:], "\n")
	body := strings.TrimLeft(rest, "\n")
	consumed := end + 1 + (len(rest) - len(body))
	return metadata, body, consumed
}

// frontmatterValue interprets one trimmed frontmatter value.
func frontmatterValue(value string) any {
	if len(value) >= 2 && value[0] == value[len(value)-1] && (value[0] == '"' || value[0] == '\'') {
		value = value[1 : len(value)-1]
	}
	if strings.HasPrefix(value, "[") && strings.HasSuffix(value, "]") {
		items := []string{}
		for _, item := range strings.Split(value[1:len(value)-1], ",") {
			if trimmed := strings.TrimSpace(item); trimmed != "" {
				items = append(items, trimmed)
			}
		}
		return items
	}
	switch strings.ToLower(value) {
	case "true":
		return true
	case "false":
		return false
	}
	if n, ok := ParsePythonInt(value); ok {
		return n
	}
	if f, ok := ParsePythonFloat(value); ok {
		return f
	}
	return value
}

// pythonIntRe is Python's int() literal grammar for a base-10 ASCII string:
// an optional sign, then digits with single underscores allowed between them.
var pythonIntRe = regexp.MustCompile(`^[+-]?[0-9](?:_?[0-9])*$`)

// pythonFloatRe is Python's float() literal grammar: an optional sign, then a
// digit-or-point mantissa with single underscores allowed between digits, then
// an optional decimal exponent. Hexadecimal floats, which Go's parser accepts
// and Python's does not, are excluded by construction.
var pythonFloatRe = regexp.MustCompile(
	`^[+-]?(?:[0-9](?:_?[0-9])*\.?(?:[0-9](?:_?[0-9])*)?|\.[0-9](?:_?[0-9])*)(?:[eE][+-]?[0-9](?:_?[0-9])*)?$`)

// pythonInfNanRe is the rest of Python's float() grammar: the special values,
// case-insensitive, with an optional sign.
var pythonInfNanRe = regexp.MustCompile(`^(?i:[+-]?(?:inf|infinity|nan))$`)

// ParsePythonInt parses s the way Python's int() does for a base-10 string,
// reporting whether it is a valid integer literal. Underscores between digits
// are accepted, as Python accepts them; a hexadecimal or octal prefix is not.
//
// One bound Python does not have: a literal outside the int64 range is
// reported invalid, where Python's arbitrary-precision int would accept it. In
// frontmatter such a value then stays a string instead of becoming a number.
func ParsePythonInt(s string) (int64, bool) {
	if !pythonIntRe.MatchString(s) {
		return 0, false
	}
	n, err := strconv.ParseInt(strings.ReplaceAll(s, "_", ""), 10, 64)
	if err != nil {
		return 0, false
	}
	return n, true
}

// ParsePythonFloat parses s the way Python's float() does, reporting whether it
// is a valid float literal. It accepts underscores between digits and the
// signed spellings of inf, infinity and nan, and rejects the hexadecimal float
// syntax Go's own parser would otherwise accept.
func ParsePythonFloat(s string) (float64, bool) {
	if !pythonFloatRe.MatchString(s) && !pythonInfNanRe.MatchString(s) {
		return 0, false
	}
	f, err := strconv.ParseFloat(strings.ReplaceAll(s, "_", ""), 64)
	if err != nil {
		return 0, false
	}
	return f, true
}
