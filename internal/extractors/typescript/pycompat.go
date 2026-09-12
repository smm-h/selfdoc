package typescript

import (
	"strings"
	"unicode"

	"github.com/smm-h/selfdoc/internal/extractors"
)

// pySpace and pyWord are the in-package spellings of the base package's
// Python-equivalent character classes. Go's own \s and \w are ASCII-only,
// where Python's are Unicode-aware for text patterns, so every regex ported
// from the Python extractor is built from these instead.
const (
	pySpace = extractors.PySpaceClass
	pyWord  = extractors.PyWordClass
)

// isPySpace reports whether r is whitespace by Python's str.isspace rule.
func isPySpace(r rune) bool {
	return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f)
}

// pyStrip is Python's str.strip() with no argument.
func pyStrip(s string) string { return strings.TrimFunc(s, isPySpace) }

// pyLStrip is Python's str.lstrip() with no argument.
func pyLStrip(s string) string { return strings.TrimLeftFunc(s, isPySpace) }

// pyRStrip is Python's str.rstrip() with no argument.
func pyRStrip(s string) string { return strings.TrimRightFunc(s, isPySpace) }

// splitExt splits path into its stem and its extension, reproducing Python's
// posixpath.splitext: the extension starts at the last dot of the last path
// element, and a leading run of dots belongs to the stem, so a dotfile has no
// extension.
func splitExt(path string) (string, string) {
	sepIndex := strings.LastIndex(path, "/")
	dotIndex := strings.LastIndex(path, ".")
	if dotIndex > sepIndex {
		filenameIndex := sepIndex + 1
		for filenameIndex < dotIndex {
			if path[filenameIndex] != '.' {
				return path[:dotIndex], path[dotIndex:]
			}
			filenameIndex++
		}
	}
	return path, ""
}
