// Package assets decides where the editor's front-end comes from, declared
// rather than discovered.
//
// Two asset trees are served: tinymoon's (the framework chrome plus the editor
// tier the authoring surface is built on) and the editor's own (the shell
// page, its module, its stylesheet). Both ship inside this package -- the
// editor's as its own files, tinymoon's through the framework module this
// build compiles in.
//
// The caller still states which tinymoon it wants, because a checkout is
// routinely ahead of the released framework. There are two answers and the
// caller picks one before anything binds a port:
//
//   - a path, from --tinymoon-assets -- a checkout's assets directory;
//   - nothing, meaning the framework tree this build embeds.
//
// Neither is a fallback for the other. Either way the resolved tree is checked
// for every file the shell loads, including the editor tier, and a tree
// missing any of them is refused with all the missing names. That refusal
// exists because the alternative is a shell that loads, renders its chrome,
// and never mounts an editor -- a failure that looks like a bug in the app
// rather than a missing dependency.
package assets

import (
	"embed"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"runtime/debug"
	"strings"

	"github.com/smm-h/tinymoon"
)

// TinymoonEditorTier is the three files that make up tinymoon's editor tier.
// They were newer than any released tinymoon when the authoring app was
// written, which is why the --tinymoon-assets path exists.
var TinymoonEditorTier = []string{
	"js/editor.js",
	"js/completion.js",
	"css/editor.css",
}

// TinymoonRequired is every tinymoon file the editor shell names DIRECTLY --
// the stylesheets its page links, in the framework's own load order, and the
// modules its app imports by name.
//
// Not the transitive module graph: those imports resolve inside the served
// tree at load time, and enumerating them here would be a copy of tinymoon's
// internals that goes stale on its next refactor. The editor tier is the one
// exception: js/completion.js is reached only through js/editor.js, and it is
// named anyway because the tier's presence is the thing being checked. A test
// keeps this list and the shell's own references in step in both directions.
var TinymoonRequired = []string{
	"css/tokens.css",
	"css/base.css",
	"css/shell.css",
	"css/primitives.css",
	"css/widgets.css",
	"css/editor.css",
	"js/dom.js",
	"js/shell.js",
	"js/view.js",
	"js/states.js",
	"js/toast.js",
	"js/modal.js",
	"js/settings.js",
	"js/editor.js",
	"js/completion.js",
}

// Error reports that the front-end assets cannot be served, and the message
// says why.
//
// It is the Go counterpart of the Python surface's AssetsError, and the one
// error type a caller needs to recognize with errors.As to render an assets
// refusal as one line instead of an unexpected internal failure.
type Error struct {
	// Message is the diagnostic, rendered verbatim by Error.
	Message string
}

// Error returns the diagnostic.
func (e *Error) Error() string { return e.Message }

// ui holds the editor's own shell page, module and stylesheet.
//
//go:embed editor_ui
var ui embed.FS

// UI returns the editor's own front-end: the shell page, its module and its
// stylesheet, addressed as "index.html", "app.js" and "app.css".
func UI() fs.FS {
	sub, err := fs.Sub(ui, "editor_ui")
	if err != nil {
		// Unreachable: the directory is embedded above.
		panic(err)
	}
	return sub
}

// Tinymoon is a resolved tinymoon asset tree, ready to be served.
type Tinymoon struct {
	// FS is the tree, addressed the way the shell addresses it:
	// "css/tokens.css", "js/editor.js".
	FS fs.FS
	// Source is a human-readable note about where the tree came from, which
	// the command prints so a session never has to guess which tinymoon it is
	// looking at.
	Source string
}

// ResolveTinymoon resolves tinymoon's asset tree, or refuses.
//
// An explicit path names a tinymoon checkout's assets directory; empty means
// the framework tree this build embeds. The resolved tree is then checked for
// every file in [TinymoonRequired], and a tree missing any of them is refused
// naming all of them.
func ResolveTinymoon(explicit string) (Tinymoon, error) {
	var resolved Tinymoon
	if explicit != "" {
		path, err := filepath.Abs(expandUser(explicit))
		if err != nil {
			path = filepath.Clean(expandUser(explicit))
		}
		info, statErr := os.Stat(path)
		if statErr != nil || !info.IsDir() {
			return Tinymoon{}, &Error{Message: fmt.Sprintf(
				"--tinymoon-assets %s is not a directory. Point it at a "+
					"tinymoon checkout's 'assets' directory.",
				path,
			)}
		}
		resolved = Tinymoon{FS: os.DirFS(path), Source: path}
	} else {
		resolved = embeddedTinymoon()
	}

	if err := requireTree(resolved); err != nil {
		return Tinymoon{}, err
	}
	return resolved, nil
}

// embeddedTinymoon is the framework tree this build compiles in, named with
// the module version that produced it.
//
// There is no absent-package condition here, which is the one place this
// diverges from the Python surface: the framework is a module dependency
// rather than an environment's installed package, so a build that exists has
// the tree. The tree is still checked against [TinymoonRequired], because a
// released framework can be missing a file the shell loads.
func embeddedTinymoon() Tinymoon {
	return Tinymoon{
		FS: tinymoon.FS(),
		Source: fmt.Sprintf(
			"embedded tinymoon %s (github.com/smm-h/tinymoon)", tinymoonVersion(),
		),
	}
}

// tinymoonVersion is the framework module's version as the build recorded it,
// or "unknown" when the binary carries no module information.
func tinymoonVersion() string {
	info, ok := debug.ReadBuildInfo()
	if !ok {
		return "unknown"
	}
	for _, dep := range info.Deps {
		if dep.Path == "github.com/smm-h/tinymoon" {
			if dep.Replace != nil && dep.Replace.Version != "" {
				return dep.Replace.Version
			}
			if dep.Version != "" {
				return dep.Version
			}
		}
	}
	return "unknown"
}

// requireTree refuses a tree missing anything the shell loads, naming all of
// it.
func requireTree(tree Tinymoon) error {
	missing := make([]string, 0)
	for _, rel := range TinymoonRequired {
		info, err := fs.Stat(tree.FS, rel)
		if err != nil || info.IsDir() {
			missing = append(missing, rel)
		}
	}
	if len(missing) == 0 {
		return nil
	}

	note := ""
	for _, rel := range missing {
		if contains(TinymoonEditorTier, rel) {
			note = " The editor tier (" + strings.Join(TinymoonEditorTier, ", ") +
				") is newer than the released tinymoon package; serve the " +
				"assets from a checkout with --tinymoon-assets " +
				"<path-to-tinymoon>/assets."
			break
		}
	}
	return &Error{Message: fmt.Sprintf(
		"The tinymoon assets at %s are missing %d file(s) the editor loads: %s.%s",
		tree.Source, len(missing), strings.Join(missing, ", "), note,
	)}
}

// contains reports whether items names value.
func contains(items []string, value string) bool {
	for _, item := range items {
		if item == value {
			return true
		}
	}
	return false
}

// expandUser reproduces Python's os.path.expanduser for the two spellings a
// command line uses: a bare "~" and a "~/..." prefix, both replaced by the
// home directory the environment names. A path with no home directory to
// substitute is returned unchanged, as Python leaves it.
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
