// Package serving carries the static-file primitives shared by selfblog's two
// local servers.
//
// The authoring app and the assembly preview both hand bytes off a disk tree
// to a browser on loopback. Two questions are the same in both -- what content
// type a file is served as, and what counts as a path inside the served root
// -- so they are answered here once rather than twice, slightly differently.
//
// Both servers bind [Host] and nothing else. Neither authenticates anything:
// the editor writes working trees and the preview serves an unreleased site,
// so the bind address is not configurable.
package serving

import (
	"mime"
	"path/filepath"
	"strings"
)

// Host is the one address either server binds.
const Host = "127.0.0.1"

// ContentTypes are the content types the platform's MIME database gets wrong
// often enough to be worth stating. Anything absent falls through to the
// platform database and then to the generic binary type.
var ContentTypes = map[string]string{
	".html":        "text/html; charset=utf-8",
	".js":          "text/javascript; charset=utf-8",
	".mjs":         "text/javascript; charset=utf-8",
	".css":         "text/css; charset=utf-8",
	".json":        "application/json; charset=utf-8",
	".svg":         "image/svg+xml",
	".map":         "application/json; charset=utf-8",
	".woff2":       "font/woff2",
	".woff":        "font/woff",
	".xml":         "application/xml; charset=utf-8",
	".txt":         "text/plain; charset=utf-8",
	".wasm":        "application/wasm",
	".webmanifest": "application/manifest+json",
}

// ContentType returns the content type path is served as.
func ContentType(path string) string {
	ext := strings.ToLower(splitExt(path))
	if declared, ok := ContentTypes[ext]; ok {
		return declared
	}
	if guessed := mime.TypeByExtension(ext); guessed != "" {
		return guessed
	}
	return "application/octet-stream"
}

// splitExt returns the extension of path the way Python's
// os.path.splitext(path)[1] does: the text from the last dot of the final
// component, with a leading run of dots not counting -- so ".bashrc" has no
// extension where Go's own filepath.Ext would call the whole name one.
func splitExt(path string) string {
	base := path
	if index := strings.LastIndexByte(base, filepath.Separator); index >= 0 {
		base = base[index+1:]
	}
	leading := 0
	for leading < len(base) && base[leading] == '.' {
		leading++
	}
	if index := strings.LastIndexByte(base[leading:], '.'); index >= 0 {
		return base[leading+index:]
	}
	return ""
}

// ResolveUnder joins rel under root, reporting false when the result escapes
// root.
//
// Symlinks are resolved before the containment test, so a link inside the
// served tree cannot be followed out of it. The caller decides what an escape
// looks like on the wire -- the editor answers a refusal, the preview answers
// its 404 page.
func ResolveUnder(root string, rel string) (string, bool) {
	root = realpath(root)
	full := realpath(filepath.Join(append([]string{root}, strings.Split(rel, "/")...)...))
	if full != root && !strings.HasPrefix(full, root+string(filepath.Separator)) {
		return "", false
	}
	return full, true
}

// realpath resolves path to an absolute, symlink-free path, leaving the
// components that do not exist as they were written.
//
// That last part is why this is not filepath.EvalSymlinks: a server resolves
// the address of a file that is not there on every 404, and EvalSymlinks
// refuses a path whose tail is missing. Python's os.path.realpath resolves as
// far as the filesystem goes and keeps the rest, which is the behavior both
// servers were written against.
func realpath(path string) string {
	abs, err := filepath.Abs(path)
	if err != nil {
		abs = filepath.Clean(path)
	}
	current, rest := abs, ""
	for {
		if resolved, err := filepath.EvalSymlinks(current); err == nil {
			return filepath.Join(resolved, rest)
		}
		parent := filepath.Dir(current)
		if parent == current {
			return abs
		}
		rest = filepath.Join(filepath.Base(current), rest)
		current = parent
	}
}
