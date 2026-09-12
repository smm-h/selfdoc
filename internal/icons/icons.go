// Package icons provides the language icons drawn beside a code block's
// language label.
//
// Each icon is an inline SVG with viewBox="0 0 16 16" and is kept under 500
// bytes. Two variants exist per language: colorful, which uses the language's
// brand colors, and monochrome, which paints with currentColor so the icon
// follows the surrounding text.
package icons

import "strings"

// Icon is the pair of inline SVG documents a language has.
type Icon struct {
	// Colorful paints with the language's brand colors.
	Colorful string
	// Monochrome paints with currentColor, so the icon takes the color of
	// the text around it.
	Monochrome string
}

// ValidCodeIconModes lists every accepted value of the code-icon mode, in the
// order the Python declared them. "none" suppresses icons entirely.
//
// The slice is package state a caller must not write to.
var ValidCodeIconModes = []string{"colorful", "monochrome", "none"}

// icons maps a canonical language name to its two SVG variants. Nothing
// iterates it -- every read is a lookup through [GetIcon] -- so the map's
// undefined iteration order reaches no output.
var icons = map[string]Icon{
	"python": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M8 1C5.2 1 5.5 2.2 5.5 2.2V3.5H8v.5H3.5S1 3.7 1 6.5S3.2 9 3.2 9H4.5V7.7S4.4 5.5 6.7 5.5h2.5S11 5.5 11 3.8V2.3S11.3 1 8 1zM6.3 2a.6.6 0 110 1.2.6.6 0 010-1.2z" fill="#3776AB"/><path d="M8 15c2.8 0 2.5-1.2 2.5-1.2V12.5H8V12h4.5s2.5.3 2.5-2.5S12.8 7 12.8 7H11.5v1.3s.1 2.2-2.2 2.2H6.8S5 10.5 5 12.2v1.5S4.7 15 8 15zm1.7-1a.6.6 0 110-1.2.6.6 0 010 1.2z" fill="#FFD43B"/></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M8 1C5.2 1 5.5 2.2 5.5 2.2V3.5H8v.5H3.5S1 3.7 1 6.5S3.2 9 3.2 9H4.5V7.7S4.4 5.5 6.7 5.5h2.5S11 5.5 11 3.8V2.3S11.3 1 8 1zM6.3 2a.6.6 0 110 1.2.6.6 0 010-1.2z" fill="currentColor"/><path d="M8 15c2.8 0 2.5-1.2 2.5-1.2V12.5H8V12h4.5s2.5.3 2.5-2.5S12.8 7 12.8 7H11.5v1.3s.1 2.2-2.2 2.2H6.8S5 10.5 5 12.2v1.5S4.7 15 8 15zm1.7-1a.6.6 0 110-1.2.6.6 0 010 1.2z" fill="currentColor" opacity="0.5"/></svg>`,
	},
	"javascript": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#F7DF1E"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="#000">JS</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="currentColor">JS</text></svg>`,
	},
	"typescript": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#3178C6"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="#fff">TS</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="currentColor">TS</text></svg>`,
	},
	"go": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#00ADD8"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="#fff">Go</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="currentColor">Go</text></svg>`,
	},
	"rust": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#B7410E"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="#fff">Rs</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="currentColor">Rs</text></svg>`,
	},
	"java": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#E76F00"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="#fff">Ja</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="currentColor">Ja</text></svg>`,
	},
	"bash": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#4EAA25"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="#fff">$_</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="currentColor">$_</text></svg>`,
	},
	"html": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#E34F26"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="7" font-weight="700" fill="#fff">&lt;/&gt;</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="7" font-weight="700" fill="currentColor">&lt;/&gt;</text></svg>`,
	},
	"css": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#1572B6"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="7" font-weight="700" fill="#fff">{;}</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="7" font-weight="700" fill="currentColor">{;}</text></svg>`,
	},
	"sql": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#336791"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="#fff">SQL</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="currentColor">SQL</text></svg>`,
	},
	"json": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#555"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="#fff">{}</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="currentColor">{}</text></svg>`,
	},
	"yaml": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#CB171E"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="#fff">YM</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="currentColor">YM</text></svg>`,
	},
	"toml": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#9C4121"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="#fff">TM</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="currentColor">TM</text></svg>`,
	},
	"markdown": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#333"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="#fff">M</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="9" font-weight="700" fill="currentColor">M</text></svg>`,
	},
	"c": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#A8B9CC"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="10" font-weight="700" fill="#fff">C</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="10" font-weight="700" fill="currentColor">C</text></svg>`,
	},
	"cpp": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#00599C"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="7" font-weight="700" fill="#fff">C++</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="7" font-weight="700" fill="currentColor">C++</text></svg>`,
	},
	"ruby": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#CC342D"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="#fff">Rb</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="currentColor">Rb</text></svg>`,
	},
	"php": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#777BB4"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="#fff">PHP</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="currentColor">PHP</text></svg>`,
	},
	"swift": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#F05138"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="#fff">Sw</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="currentColor">Sw</text></svg>`,
	},
	"kotlin": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#7F52FF"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="#fff">Kt</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12.5" text-anchor="middle" font-family="monospace" font-size="8" font-weight="700" fill="currentColor">Kt</text></svg>`,
	},
	"docker": {
		Colorful:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="#2496ED"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="6.5" font-weight="700" fill="#fff">Dk</text></svg>`,
		Monochrome: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/><text x="8" y="12" text-anchor="middle" font-family="monospace" font-size="6.5" font-weight="700" fill="currentColor">Dk</text></svg>`,
	},
}

// aliases maps an alternative spelling of a language to its canonical name.
var aliases = map[string]string{
	"js":         "javascript",
	"ts":         "typescript",
	"sh":         "bash",
	"shell":      "bash",
	"zsh":        "bash",
	"yml":        "yaml",
	"c++":        "cpp",
	"cxx":        "cpp",
	"md":         "markdown",
	"dockerfile": "docker",
	"py":         "python",
	"rb":         "ruby",
	"rs":         "rust",
	"kt":         "kotlin",
}

// GetIcon returns the inline SVG icon for language in the given mode, and
// whether one exists.
//
// language is matched case-insensitively and aliases are resolved ("js" ->
// "javascript", "sh" -> "bash"). mode is one of [ValidCodeIconModes]; "none"
// always reports no icon, and any unrecognized mode is treated as "colorful",
// which is what the Python did with its default argument.
func GetIcon(language, mode string) (string, bool) {
	if mode == "none" {
		return "", false
	}
	key := strings.ToLower(language)
	if canonical, ok := aliases[key]; ok {
		key = canonical
	}
	entry, ok := icons[key]
	if !ok {
		return "", false
	}
	if mode == "monochrome" {
		return entry.Monochrome, true
	}
	return entry.Colorful, true
}
