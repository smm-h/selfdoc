package extractors

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

// fakeExtractor stands in for a language package in the registry tests. It
// detects a directory by the marker file it was built with.
type fakeExtractor struct {
	Base
	marker string
}

func newFake(language, marker string) Factory {
	return func() Extractor {
		fake := &fakeExtractor{marker: marker}
		fake.Base = NewBase(language, map[string]Handler{
			"ref": func(path string, _ *string, _ []string, _ []string, _ string, _ map[string]string) (string, error) {
				return "ref:" + path, nil
			},
		})
		return fake
	}
}

func (f *fakeExtractor) Detect(dir string) bool {
	return IsFile(filepath.Join(dir, f.marker))
}

// withRegistry replaces the language registry for the duration of one test.
func withRegistry(t *testing.T, factories map[string]Factory) {
	t.Helper()
	registryMu.Lock()
	previous := registry
	registry = map[string]Factory{}
	for name, factory := range factories {
		registry[name] = factory
	}
	registryMu.Unlock()
	t.Cleanup(func() {
		registryMu.Lock()
		registry = previous
		registryMu.Unlock()
	})
}

// allFakes registers every language in the detection order with its real
// marker file, so the detection tests exercise the order rather than which
// packages happen to be linked into this test binary.
func allFakes() map[string]Factory {
	return map[string]Factory{
		"python":     newFake("python", "pyproject.toml"),
		"go":         newFake("go", "go.mod"),
		"svelte":     newFake("svelte", "svelte.config.js"),
		"typescript": newFake("typescript", "tsconfig.json"),
		"zig":        newFake("zig", "build.zig"),
		"swift":      newFake("swift", "Package.swift"),
		"kotlin":     newFake("kotlin", "build.gradle.kts"),
		"dart":       newFake("dart", "pubspec.yaml"),
		"sql":        newFake("sql", ".never-detected"),
	}
}

func touch(t *testing.T, dir, name string) {
	t.Helper()
	if err := os.WriteFile(filepath.Join(dir, name), nil, 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestKnownLanguages(t *testing.T) {
	t.Parallel()
	want := []string{"python", "go", "typescript", "zig", "swift", "kotlin", "dart", "svelte", "sql"}
	got := KnownLanguages()
	if len(got) != len(want) {
		t.Fatalf("KnownLanguages = %#v, want %#v", got, want)
	}
	for _, name := range want {
		if !IsKnownLanguage(name) {
			t.Errorf("%q is not reported as a known language", name)
		}
	}
	if IsKnownLanguage("rust") {
		t.Error("rust is reported as a known language")
	}
}

// TestDetectionOrder pins the two properties of the order that are decisions
// rather than accidents.
func TestDetectionOrder(t *testing.T) {
	t.Parallel()
	order := DetectionOrder()
	index := map[string]int{}
	for i, name := range order {
		index[name] = i
	}
	svelte, hasSvelte := index["svelte"]
	typescript, hasTypeScript := index["typescript"]
	if !hasSvelte || !hasTypeScript {
		t.Fatalf("detection order %#v is missing svelte or typescript", order)
	}
	if svelte >= typescript {
		t.Error("svelte must be tried before typescript: a Svelte project also has a tsconfig.json")
	}
	if _, hasSQL := index["sql"]; hasSQL {
		t.Error("sql must not be auto-detected: it is declared in selfdoc.json")
	}
}

func TestKnownLanguagesIsACopy(t *testing.T) {
	t.Parallel()
	first := KnownLanguages()
	first[0] = "mutated"
	if KnownLanguages()[0] == "mutated" {
		t.Fatal("KnownLanguages handed out the backing array")
	}
	order := DetectionOrder()
	order[0] = "mutated"
	if DetectionOrder()[0] == "mutated" {
		t.Fatal("DetectionOrder handed out the backing array")
	}
}

func TestRegisterRefusesAnUnknownLanguage(t *testing.T) {
	withRegistry(t, nil)
	defer func() {
		if recover() == nil {
			t.Fatal("registering an unknown language did not panic")
		}
	}()
	Register("rust", newFake("rust", "Cargo.toml"))
}

func TestRegisterRefusesADuplicate(t *testing.T) {
	withRegistry(t, nil)
	Register("zig", newFake("zig", "build.zig"))
	defer func() {
		if recover() == nil {
			t.Fatal("registering the same language twice did not panic")
		}
	}()
	Register("zig", newFake("zig", "build.zig"))
}

func TestRegisterRefusesANilFactory(t *testing.T) {
	withRegistry(t, nil)
	defer func() {
		if recover() == nil {
			t.Fatal("registering a nil factory did not panic")
		}
	}()
	Register("zig", nil)
}

func TestRegisteredListsWhatIsLinkedIn(t *testing.T) {
	withRegistry(t, map[string]Factory{
		"go":     newFake("go", "go.mod"),
		"python": newFake("python", "pyproject.toml"),
	})
	if want := []string{"go", "python"}; !reflect.DeepEqual(Registered(), want) {
		t.Fatalf("Registered = %#v, want %#v", Registered(), want)
	}
}

func TestLookup(t *testing.T) {
	withRegistry(t, map[string]Factory{"zig": newFake("zig", "build.zig")})

	extractor, ok, err := Lookup("zig")
	if err != nil || !ok {
		t.Fatalf("Lookup(zig) = (_, %v, %v), want (_, true, nil)", ok, err)
	}
	if extractor.Name() != "zig" {
		t.Fatalf("extractor name = %q, want zig", extractor.Name())
	}

	if _, ok, err := Lookup("rust"); ok || err != nil {
		t.Fatalf("Lookup(rust) = (_, %v, %v), want (_, false, nil)", ok, err)
	}

	if _, _, err := Lookup("python"); err == nil {
		t.Fatal("a known language with no registered factory was answered without an error")
	}
}

func TestDetectLanguage(t *testing.T) {
	withRegistry(t, allFakes())

	t.Run("python", func(t *testing.T) {
		dir := t.TempDir()
		touch(t, dir, "pyproject.toml")
		assertDetect(t, dir, "python")
	})

	t.Run("go", func(t *testing.T) {
		dir := t.TempDir()
		touch(t, dir, "go.mod")
		assertDetect(t, dir, "go")
	})

	t.Run("typescript", func(t *testing.T) {
		dir := t.TempDir()
		touch(t, dir, "tsconfig.json")
		assertDetect(t, dir, "typescript")
	})

	t.Run("nothing in an empty directory", func(t *testing.T) {
		assertDetect(t, t.TempDir(), "")
	})

	t.Run("python beats go", func(t *testing.T) {
		dir := t.TempDir()
		touch(t, dir, "pyproject.toml")
		touch(t, dir, "go.mod")
		assertDetect(t, dir, "python")
	})

	t.Run("go beats typescript", func(t *testing.T) {
		dir := t.TempDir()
		touch(t, dir, "go.mod")
		touch(t, dir, "tsconfig.json")
		assertDetect(t, dir, "go")
	})

	t.Run("svelte beats typescript", func(t *testing.T) {
		dir := t.TempDir()
		touch(t, dir, "svelte.config.js")
		touch(t, dir, "tsconfig.json")
		assertDetect(t, dir, "svelte")
	})
}

func assertDetect(t *testing.T, dir, want string) {
	t.Helper()
	got, err := DetectLanguage(dir)
	if err != nil {
		t.Fatal(err)
	}
	if got != want {
		t.Fatalf("DetectLanguage = %q, want %q", got, want)
	}
}

func TestDetectLanguages(t *testing.T) {
	withRegistry(t, allFakes())

	t.Run("a single language", func(t *testing.T) {
		dir := t.TempDir()
		touch(t, dir, "pyproject.toml")
		got, err := DetectLanguages(dir)
		if err != nil {
			t.Fatal(err)
		}
		if len(got) != 1 || got[0].Language != "python" || got[0].Path != dir {
			t.Fatalf("DetectLanguages = %#v", got)
		}
	})

	t.Run("all three in detection order", func(t *testing.T) {
		dir := t.TempDir()
		touch(t, dir, "pyproject.toml")
		touch(t, dir, "go.mod")
		touch(t, dir, "tsconfig.json")
		got, err := DetectLanguages(dir)
		if err != nil {
			t.Fatal(err)
		}
		var languages []string
		for _, entry := range got {
			languages = append(languages, entry.Language)
		}
		if want := []string{"python", "go", "typescript"}; !reflect.DeepEqual(languages, want) {
			t.Fatalf("languages = %#v, want %#v", languages, want)
		}
	})

	t.Run("an empty directory detects nothing", func(t *testing.T) {
		got, err := DetectLanguages(t.TempDir())
		if err != nil {
			t.Fatal(err)
		}
		if len(got) != 0 {
			t.Fatalf("DetectLanguages = %#v, want none", got)
		}
	})
}

func TestResolveSourceEntries(t *testing.T) {
	withRegistry(t, allFakes())

	t.Run("a single entry", func(t *testing.T) {
		config := map[string]any{"source": []any{
			map[string]any{"path": "mylib/", "language": "python"},
		}}
		entries, err := ResolveSourceEntries(config)
		if err != nil {
			t.Fatal(err)
		}
		if len(entries) != 1 {
			t.Fatalf("entries = %#v", entries)
		}
		if entries[0].Path != "mylib/" || entries[0].Language != "python" {
			t.Fatalf("entry = %#v", entries[0])
		}
		if entries[0].Extractor.Name() != "python" {
			t.Fatalf("extractor = %q", entries[0].Extractor.Name())
		}
	})

	t.Run("several entries keep their order", func(t *testing.T) {
		config := map[string]any{"source": []any{
			map[string]any{"path": "src/", "language": "python"},
			map[string]any{"path": "lib/", "language": "python"},
		}}
		entries, err := ResolveSourceEntries(config)
		if err != nil {
			t.Fatal(err)
		}
		if len(entries) != 2 || entries[0].Path != "src/" || entries[1].Path != "lib/" {
			t.Fatalf("entries = %#v", entries)
		}
	})

	t.Run("an unsupported language gets a stub", func(t *testing.T) {
		config := map[string]any{"source": []any{
			map[string]any{"path": "lib/", "language": "ruby"},
		}}
		entries, err := ResolveSourceEntries(config)
		if err != nil {
			t.Fatal(err)
		}
		if len(entries) != 1 || entries[0].Language != "ruby" {
			t.Fatalf("entries = %#v", entries)
		}
		markdown, err := entries[0].Extractor.Extract("ref", map[string]string{"path": "Foo"}, nil, nil, "/base")
		if err != nil {
			t.Fatal(err)
		}
		if want := "> *[selfdoc: no extractor for 'ruby']*"; markdown != want {
			t.Fatalf("stub extract = %q, want %q", markdown, want)
		}
	})

	t.Run("no source key yields no entries", func(t *testing.T) {
		entries, err := ResolveSourceEntries(map[string]any{})
		if err != nil {
			t.Fatal(err)
		}
		if len(entries) != 0 {
			t.Fatalf("entries = %#v, want none", entries)
		}
	})

	t.Run("a malformed entry is an error", func(t *testing.T) {
		config := map[string]any{"source": []any{map[string]any{"path": "lib/"}}}
		if _, err := ResolveSourceEntries(config); err == nil {
			t.Fatal("a source entry with no language was accepted")
		}
		config = map[string]any{"source": "lib/"}
		if _, err := ResolveSourceEntries(config); err == nil {
			t.Fatal("a non-array source was accepted")
		}
	})
}

func TestSourcePaths(t *testing.T) {
	t.Parallel()
	config := map[string]any{"source": []any{
		map[string]any{"path": "selfdoc/", "language": "python"},
		map[string]any{"path": "tests/", "language": "python"},
	}}
	got, err := SourcePaths(config)
	if err != nil {
		t.Fatal(err)
	}
	if want := []string{"selfdoc/", "tests/"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("SourcePaths = %#v, want %#v", got, want)
	}

	empty, err := SourcePaths(map[string]any{})
	if err != nil {
		t.Fatal(err)
	}
	if len(empty) != 0 {
		t.Fatalf("SourcePaths = %#v, want none", empty)
	}
}
