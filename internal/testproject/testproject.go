// Package testproject builds the fixture projects the engine's tests run
// against.
//
// Every suite that exercises a whole build needs a project on disk: a
// selfdoc.json the loader accepts, a source file, and a docs tree. The
// factories here are the Go form of the Python suite's fixture factories, so
// the build, the check, the blog and the command tests all start from the same
// shapes rather than each writing its own almost-identical project.
//
// # No dependency on testing
//
// The helpers take [TB], the slice of testing.TB they use, so importing this
// package does not pull the testing flag set into anything that links it.
package testproject

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"strings"
	"sync"
)

// TB is the slice of testing.TB these helpers use.
type TB interface {
	Helper()
	Fatalf(format string, args ...any)
	Skipf(format string, args ...any)
	Setenv(key, value string)
	TempDir() string
}

// DefaultPrefix is the mount prefix the default fixture config emits its
// current version at.
//
// Empty: one locale drops the locale segment and the current version carries
// no version segment, so the pages sit at the output root.
const DefaultPrefix = ""

// Author returns the author block every fixture project declares.
//
// The block is required in selfdoc.json and is what every page's structured
// data names, so a fixture without one is not a project the loader accepts.
func Author() map[string]any {
	return map[string]any{
		"name":    "Test Author",
		"url":     "https://author.example",
		"same_as": []any{"https://github.com/testauthor"},
	}
}

// DefaultConfig returns the minimal valid selfdoc config, with the required
// versions and locales arrays, and the given overrides applied over it.
func DefaultConfig(overrides map[string]any) map[string]any {
	config := map[string]any{
		"source":        []any{map[string]any{"path": "src/", "language": "python"}},
		"base_url":      "https://example.com",
		"version":       "1.0.0",
		"versions":      []any{map[string]any{"version": "1.0.0"}},
		"locales":       []any{map[string]any{"code": "en", "label": "English", "default": true}},
		"search_engine": "pagefind",
		"author":        Author(),
	}
	for key, value := range overrides {
		config[key] = value
	}
	return config
}

// Make creates a minimal selfdoc project under a fresh directory and returns
// its path.
//
// The project carries a selfdoc.json built from DefaultConfig plus overrides,
// one Python source file, and one docs page.
func Make(t TB, overrides map[string]any) string {
	t.Helper()
	projectDir := filepath.Join(t.TempDir(), "project")
	MkdirAll(t, projectDir)

	WriteJSON(t, filepath.Join(projectDir, "selfdoc.json"), DefaultConfig(overrides))
	WriteText(t, filepath.Join(projectDir, "src", "__init__.py"), `"""Example package."""`+"\n")
	WriteText(t, filepath.Join(projectDir, "docs", "index.md"),
		"# Test Project\n\nWelcome to the docs.\n")
	return projectDir
}

// MakeVersioned creates a selfdoc project with one git tag per version and
// returns its path.
//
// Each version's tag stands at a commit whose docs/index.md names that
// version, so a multi-version build really does read different content out of
// each tag.
func MakeVersioned(t TB, versions []string, overrides map[string]any) string {
	t.Helper()
	if len(versions) == 0 {
		t.Fatalf("MakeVersioned needs at least one version")
	}
	projectDir := filepath.Join(t.TempDir(), "versioned")
	MkdirAll(t, projectDir)

	versionEntries := make([]any, 0, len(versions))
	for _, version := range versions {
		versionEntries = append(versionEntries, map[string]any{"version": version})
	}
	config := map[string]any{
		"source":        []any{map[string]any{"path": "src/", "language": "python"}},
		"base_url":      "https://example.com",
		"search_engine": "pagefind",
		"author":        Author(),
		"version":       versions[len(versions)-1],
		"versions":      versionEntries,
		"locales":       []any{map[string]any{"code": "en", "label": "English", "default": true}},
	}
	for key, value := range overrides {
		config[key] = value
	}
	WriteJSON(t, filepath.Join(projectDir, "selfdoc.json"), config)
	WriteText(t, filepath.Join(projectDir, "src", "__init__.py"), `"""Example package."""`+"\n")
	WriteText(t, filepath.Join(projectDir, "docs", "index.md"),
		"# Test Project\n\nInitial content.\n")

	Git(t, projectDir, "init")
	Git(t, projectDir, "add", ".")
	Git(t, projectDir, "commit", "-m", "initial")

	for _, version := range versions {
		WriteText(t, filepath.Join(projectDir, "docs", "index.md"),
			fmt.Sprintf("# Test Project\n\nDocumentation for version %s.\n", version))
		Git(t, projectDir, "add", "docs/index.md")
		Git(t, projectDir, "commit", "-m", "docs for "+version)
		Git(t, projectDir, "tag", "v"+version)
	}
	return projectDir
}

// MakeLocalized creates a selfdoc project with one docs directory per locale
// and returns its path.
//
// Each locale entry is a config locale object: "code" and "label" are
// required, "default" and "rtl" optional.
func MakeLocalized(t TB, locales []map[string]any, overrides map[string]any) string {
	t.Helper()
	projectDir := filepath.Join(t.TempDir(), "localized")
	MkdirAll(t, projectDir)

	localeEntries := make([]any, 0, len(locales))
	for _, locale := range locales {
		localeEntries = append(localeEntries, locale)
	}
	config := map[string]any{
		"source":        []any{map[string]any{"path": "src/", "language": "python"}},
		"base_url":      "https://example.com",
		"search_engine": "pagefind",
		"author":        Author(),
		"version":       "1.0.0",
		"locales":       localeEntries,
		"versions":      []any{map[string]any{"version": "1.0.0"}},
	}
	for key, value := range overrides {
		config[key] = value
	}
	WriteJSON(t, filepath.Join(projectDir, "selfdoc.json"), config)
	WriteText(t, filepath.Join(projectDir, "src", "__init__.py"), `"""Example package."""`+"\n")

	for _, locale := range locales {
		code, _ := locale["code"].(string)
		label, _ := locale["label"].(string)
		WriteText(t, filepath.Join(projectDir, "docs", code, "index.md"),
			fmt.Sprintf("# Test Project (%s)\n\nWelcome — %s.\n", label, label))
	}
	return projectDir
}

// WriteText writes text to path, creating the parent directories.
func WriteText(t TB, path, text string) {
	t.Helper()
	MkdirAll(t, filepath.Dir(path))
	if err := os.WriteFile(path, []byte(text), 0o644); err != nil {
		t.Fatalf("writing %s: %v", path, err)
	}
}

// WriteJSON writes value to path as indented JSON, creating the parent
// directories.
func WriteJSON(t TB, path string, value any) {
	t.Helper()
	encoded, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		t.Fatalf("encoding %s: %v", path, err)
	}
	WriteText(t, path, string(encoded)+"\n")
}

// ReadText reads a file and returns its contents, failing the test when it
// cannot be read.
func ReadText(t TB, path string) string {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("reading %s: %v", path, err)
	}
	return string(content)
}

// MkdirAll creates a directory and its parents, failing the test when it
// cannot.
func MkdirAll(t TB, dir string) {
	t.Helper()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatalf("creating %s: %v", dir, err)
	}
}

// Git runs a git command in dir, failing the test when it exits non-zero.
//
// No identity is injected: the isolation floor owns the git identity and the
// throwaway global config for the whole test, so a second source could only
// drift from it.
func Git(t TB, dir string, args ...string) {
	t.Helper()
	cmd := exec.Command("git", args...)
	cmd.Dir = dir
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("git %s in %s: %v\n%s", strings.Join(args, " "), dir, err, output)
	}
}

// pagefindOnce memoizes the search for a working Pagefind installation, which
// costs a subprocess per candidate.
var (
	pagefindOnce    sync.Once
	pagefindCommand []string
)

// RequirePagefind skips the test unless a Pagefind installation the build can
// reach is available, and makes it reachable when it is installed somewhere
// the build would not look.
//
// The build runs "python3 -m pagefind" and then "pagefind". When neither
// answers but an interpreter under the user's uv tool directory carries the
// module, a "pagefind" shim naming that interpreter is written into a
// directory prepended to PATH -- which is the second thing the build tries, so
// nothing about the build changes.
//
// It must be called before the test calls T.Parallel, because it sets an
// environment variable.
func RequirePagefind(t TB) {
	t.Helper()
	pagefindOnce.Do(func() { pagefindCommand = findPagefind() })
	if pagefindCommand == nil {
		t.Skipf("pagefind is not installed: the build indexes its output with " +
			"'python3 -m pagefind' or 'pagefind', and neither answered. " +
			"Install it with 'uv add pagefind' or 'npm install -g pagefind'.")
		return
	}
	if len(pagefindCommand) == 1 && pagefindCommand[0] == "pagefind" {
		return
	}
	if len(pagefindCommand) == 3 && pagefindCommand[0] == "python3" {
		return
	}
	shimDir := filepath.Join(t.TempDir(), "pagefind-shim")
	MkdirAll(t, shimDir)
	shim := filepath.Join(shimDir, "pagefind")
	script := "#!/bin/sh\nexec " + strings.Join(pagefindCommand, " ") + ` "$@"` + "\n"
	if err := os.WriteFile(shim, []byte(script), 0o755); err != nil {
		t.Fatalf("writing the pagefind shim: %v", err)
	}
	t.Setenv("PATH", shimDir+string(os.PathListSeparator)+os.Getenv("PATH"))
}

// findPagefind returns an argv prefix that runs Pagefind, or nil when none
// does.
func findPagefind() []string {
	candidates := [][]string{
		{"python3", "-m", "pagefind"},
		{"pagefind"},
	}
	for _, interpreter := range uvToolInterpreters() {
		candidates = append(candidates, []string{interpreter, "-m", "pagefind"})
	}
	for _, candidate := range candidates {
		cmd := exec.Command(candidate[0], append(candidate[1:], "--version")...)
		if err := cmd.Run(); err == nil {
			return candidate
		}
	}
	return nil
}

// uvToolInterpreters lists the Python interpreters uv installed for its tools,
// which is where a pip-installed Pagefind ends up on a machine whose system
// interpreter does not carry it.
//
// The home directory is read from the password database rather than from HOME,
// because the isolation floor has already replaced HOME with a throwaway
// directory by the time a test calls this.
func uvToolInterpreters() []string {
	account, err := user.Current()
	if err != nil || account.HomeDir == "" {
		return nil
	}
	matches, err := filepath.Glob(filepath.Join(
		account.HomeDir, ".local", "share", "uv", "tools", "*", "bin", "python3"))
	if err != nil {
		return nil
	}
	return matches
}

// UnifiedProject is one constituent project a unified fixture carries: its
// directory name, which is also its mount slug, and the language its source
// entry declares. An empty language means Python.
type UnifiedProject struct {
	Name     string
	Language string
}

// MakeUnified creates a monorepo whose docs-site unifies several constituent
// projects, and returns the docs-site's path.
//
// The layout is the one a real rlsbl workspace has: every project, the
// docs-site included, is a directory under "monorepo/packages/", so each
// constituent is addressed from the docs-site as "../<name>" -- which is what
// the unified config's relative paths are resolved against. Each constituent
// carries its own selfdoc.json with its own base URL and one docs page; the
// docs-site carries the "unified" block naming them all, plus the versions and
// locales arrays the unified build's passes are driven by.
//
// overrides are applied over the docs-site's config, so a test can state a
// different base URL, extra versions or a per-version project pinning without
// rebuilding the whole fixture.
func MakeUnified(t TB, projects []UnifiedProject, overrides map[string]any) string {
	t.Helper()
	packagesDir := filepath.Join(t.TempDir(), "monorepo", "packages")
	MkdirAll(t, packagesDir)

	unifiedEntries := make([]any, 0, len(projects))
	for _, project := range projects {
		language := project.Language
		if language == "" {
			language = "python"
		}
		projectDir := filepath.Join(packagesDir, project.Name)
		WriteJSON(t, filepath.Join(projectDir, "selfdoc.json"), map[string]any{
			"source":        []any{map[string]any{"path": "src/", "language": language}},
			"base_url":      "https://example.com/" + project.Name,
			"search_engine": "pagefind",
			"author":        Author(),
			"version":       "1.0.0",
		})
		WriteText(t, filepath.Join(projectDir, "src", "__init__.py"),
			`"""`+project.Name+` package."""`+"\n")
		WriteText(t, filepath.Join(projectDir, "docs", "index.md"),
			fmt.Sprintf("# %s\n\nDocs for %s.\n", project.Name, project.Name))
		unifiedEntries = append(unifiedEntries, map[string]any{"path": "../" + project.Name})
	}

	docsSiteDir := filepath.Join(packagesDir, "docs-site")
	docsSiteConfig := map[string]any{
		"source":        []any{map[string]any{"path": "src/", "language": "python"}},
		"base_url":      "https://example.com",
		"search_engine": "pagefind",
		"author":        Author(),
		"unified":       map[string]any{"projects": unifiedEntries},
		"version":       "1.0.0",
		"versions":      []any{map[string]any{"version": "1.0.0"}},
		"locales":       []any{map[string]any{"code": "en", "label": "English", "default": true}},
	}
	for key, value := range overrides {
		docsSiteConfig[key] = value
	}
	WriteJSON(t, filepath.Join(docsSiteDir, "selfdoc.json"), docsSiteConfig)
	// The docs-site needs a source entry of its own: the config requires
	// one, and it is a project like any other.
	WriteText(t, filepath.Join(docsSiteDir, "src", "__init__.py"),
		`"""Docs-site placeholder."""`+"\n")
	WriteText(t, filepath.Join(docsSiteDir, "docs", "index.md"),
		"# Unified Docs\n\nLanding page for the monorepo.\n")
	return docsSiteDir
}
