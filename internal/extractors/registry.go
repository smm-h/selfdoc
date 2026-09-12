package extractors

import (
	"fmt"
	"sort"
	"sync"

	"github.com/smm-h/selfdoc/internal/effects"
)

// Factory builds an extractor bound to an effects handle.
//
// The handle is a constructor argument rather than a per-call one because only
// one extractor needs it -- the Python extractor runs an embedded driver under
// python3 -- and threading it through eight signatures that ignore it would say
// the opposite of what is true.
type Factory func(handle *effects.Handle) Extractor

// knownLanguages is the authority on which languages selfdoc ships an
// extractor for. A name on this list with no registered factory is a wiring
// mistake, reported as such; a name that is not on it is a language selfdoc
// does not support, answered with a stub.
var knownLanguages = []string{
	"python",
	"go",
	"typescript",
	"zig",
	"swift",
	"kotlin",
	"dart",
	"svelte",
	"sql",
}

// detectionOrder is the priority order auto-detection walks.
//
// Svelte comes before TypeScript because a Svelte project also has TypeScript
// files and a tsconfig.json, so TypeScript would win every Svelte project.
// SQL is absent on purpose: a SQL source path is declared in selfdoc.json and
// never auto-detected, because a .sql file in a repository says nothing about
// what the repository is.
var detectionOrder = []string{
	"python",
	"go",
	"svelte",
	"typescript",
	"zig",
	"swift",
	"kotlin",
	"dart",
}

var (
	registryMu sync.RWMutex
	registry   = map[string]Factory{}
)

// KnownLanguages lists every language selfdoc ships an extractor for.
func KnownLanguages() []string {
	return append([]string(nil), knownLanguages...)
}

// DetectionOrder lists the languages auto-detection tries, in priority order.
func DetectionOrder() []string {
	return append([]string(nil), detectionOrder...)
}

// IsKnownLanguage reports whether selfdoc ships an extractor for name.
func IsKnownLanguage(name string) bool {
	for _, known := range knownLanguages {
		if known == name {
			return true
		}
	}
	return false
}

// Register records the factory for a language. Each language package calls it
// from an init function, so linking the package in is what makes the language
// available.
//
// It panics on a name that is not a known language and on a second
// registration of the same name: both are mistakes in the language package
// itself, visible the moment the binary starts.
func Register(name string, factory Factory) {
	if !IsKnownLanguage(name) {
		panic(fmt.Sprintf("extractors: %q is not a known language; add it to knownLanguages first", name))
	}
	if factory == nil {
		panic(fmt.Sprintf("extractors: %q registered a nil factory", name))
	}
	registryMu.Lock()
	defer registryMu.Unlock()
	if _, exists := registry[name]; exists {
		panic(fmt.Sprintf("extractors: %q registered twice", name))
	}
	registry[name] = factory
}

// Registered lists the languages whose packages are linked into this binary,
// sorted.
func Registered() []string {
	registryMu.RLock()
	defer registryMu.RUnlock()
	names := make([]string, 0, len(registry))
	for name := range registry {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

// Lookup builds the extractor registered for a language.
//
// It reports an error for a known language whose package is not linked in,
// rather than answering with a stub: the project declared a language selfdoc
// supports, and quietly rendering "no extractor for 'python'" across its pages
// would blame the project for a wiring mistake in selfdoc. A language selfdoc
// does not support is not an error -- it returns false, and the caller
// substitutes NewStub.
func Lookup(name string, handle *effects.Handle) (Extractor, bool, error) {
	registryMu.RLock()
	factory, ok := registry[name]
	registryMu.RUnlock()
	if ok {
		return factory(handle), true, nil
	}
	if IsKnownLanguage(name) {
		return nil, false, fmt.Errorf(
			"extractors: no extractor registered for %q, which selfdoc supports: "+
				"the language's package is not linked into this binary", name)
	}
	return nil, false, nil
}

// DetectedLanguage is one language auto-detection found in a directory.
type DetectedLanguage struct {
	// Path is the directory the language was detected in.
	Path string
	// Language is the language's registry name.
	Language string
}

// DetectLanguage auto-detects a project's language from the marker files in
// dir, returning the empty string when none is detected.
func DetectLanguage(dir string, handle *effects.Handle) (string, error) {
	for _, name := range detectionOrder {
		extractor, ok, err := Lookup(name, handle)
		if err != nil {
			return "", err
		}
		if !ok {
			continue
		}
		if extractor.Detect(dir) {
			return name, nil
		}
	}
	return "", nil
}

// DetectLanguages reports every language detected in dir, not just the first.
// A polyglot repository answers with several, in detection-priority order.
func DetectLanguages(dir string, handle *effects.Handle) ([]DetectedLanguage, error) {
	var results []DetectedLanguage
	for _, name := range detectionOrder {
		extractor, ok, err := Lookup(name, handle)
		if err != nil {
			return nil, err
		}
		if !ok {
			continue
		}
		if extractor.Detect(dir) {
			results = append(results, DetectedLanguage{Path: dir, Language: name})
		}
	}
	return results, nil
}

// SourceEntry is a declared source path with its language and the extractor
// that reads it.
type SourceEntry struct {
	// Path is the source path as selfdoc.json declares it, relative to the
	// project's base directory.
	Path string
	// Language is the language's registry name.
	Language string
	// Extractor reads this path's sources.
	Extractor Extractor
}

// ResolveSourceEntries resolves a config's source declarations into entries
// carrying their extractors.
//
// A project that publishes no code declares no source entries, so an absent or
// empty source key yields none.
func ResolveSourceEntries(config map[string]any, handle *effects.Handle) ([]SourceEntry, error) {
	items, err := sourceItems(config)
	if err != nil {
		return nil, err
	}
	entries := make([]SourceEntry, 0, len(items))
	for i, item := range items {
		language, err := stringField(item, "language", i)
		if err != nil {
			return nil, err
		}
		path, err := stringField(item, "path", i)
		if err != nil {
			return nil, err
		}
		extractor, ok, err := Lookup(language, handle)
		if err != nil {
			return nil, err
		}
		if !ok {
			extractor = NewStub(language)
		}
		entries = append(entries, SourceEntry{Path: path, Language: language, Extractor: extractor})
	}
	return entries, nil
}

// SourcePaths lists just the declared source paths. It is empty for a project
// that publishes no code.
func SourcePaths(config map[string]any) ([]string, error) {
	items, err := sourceItems(config)
	if err != nil {
		return nil, err
	}
	paths := make([]string, 0, len(items))
	for i, item := range items {
		path, err := stringField(item, "path", i)
		if err != nil {
			return nil, err
		}
		paths = append(paths, path)
	}
	return paths, nil
}

// sourceItems reads the config's source array as a list of declarations.
func sourceItems(config map[string]any) ([]map[string]any, error) {
	raw, ok := config["source"]
	if !ok || raw == nil {
		return nil, nil
	}
	list, ok := raw.([]any)
	if !ok {
		if typed, ok := raw.([]map[string]any); ok {
			return typed, nil
		}
		return nil, fmt.Errorf("selfdoc.json: 'source' must be an array, got %T", raw)
	}
	items := make([]map[string]any, 0, len(list))
	for i, entry := range list {
		item, ok := entry.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("selfdoc.json: source entry %d must be an object, got %T", i, entry)
		}
		items = append(items, item)
	}
	return items, nil
}

// stringField reads a required string field off one source declaration.
func stringField(item map[string]any, field string, index int) (string, error) {
	raw, ok := item[field]
	if !ok {
		return "", fmt.Errorf("selfdoc.json: source entry %d has no '%s'", index, field)
	}
	value, ok := raw.(string)
	if !ok {
		return "", fmt.Errorf("selfdoc.json: source entry %d has a non-string '%s' (%T)", index, field, raw)
	}
	return value, nil
}
