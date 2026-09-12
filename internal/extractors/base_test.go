package extractors

import "testing"

func TestBaseExtractDispatch(t *testing.T) {
	t.Parallel()

	var seen struct {
		path        string
		target      *string
		body        []string
		sourcePaths []string
		baseDir     string
		attrs       map[string]string
	}
	base := NewBase("python", map[string]Handler{
		"ref": func(
			path string,
			target *string,
			body []string,
			sourcePaths []string,
			baseDir string,
			attrs map[string]string,
		) (string, error) {
			seen.path = path
			seen.target = target
			seen.body = body
			seen.sourcePaths = sourcePaths
			seen.baseDir = baseDir
			seen.attrs = attrs
			return "resolved", nil
		},
	})

	got, err := base.Extract(
		"ref",
		map[string]string{"path": "mylib.core", "target": "Widget", "exclude": "x"},
		[]string{"body"},
		[]string{"mylib/"},
		"/base",
	)
	if err != nil {
		t.Fatal(err)
	}
	if got != "resolved" {
		t.Fatalf("Extract = %q, want %q", got, "resolved")
	}
	if seen.path != "mylib.core" {
		t.Errorf("path = %q", seen.path)
	}
	if seen.target == nil || *seen.target != "Widget" {
		t.Errorf("target = %v", seen.target)
	}
	if seen.baseDir != "/base" || len(seen.sourcePaths) != 1 || seen.attrs["exclude"] != "x" {
		t.Errorf("handler saw %#v", seen)
	}
}

// TestBaseExtractDistinguishesAnAbsentTarget pins the difference a directive
// depends on: no target means "the whole file", an empty target is a lookup.
func TestBaseExtractDistinguishesAnAbsentTarget(t *testing.T) {
	t.Parallel()
	var absent, empty bool
	base := NewBase("go", map[string]Handler{
		"code-test": func(_ string, target *string, _ []string, _ []string, _ string, _ map[string]string) (string, error) {
			if target == nil {
				absent = true
			} else if *target == "" {
				empty = true
			}
			return "", nil
		},
	})

	if _, err := base.Extract("code-test", map[string]string{"path": "x_test.go"}, nil, nil, "."); err != nil {
		t.Fatal(err)
	}
	if !absent {
		t.Error("a directive with no target attribute did not present a nil target")
	}

	if _, err := base.Extract("code-test", map[string]string{"path": "x_test.go", "target": ""}, nil, nil, "."); err != nil {
		t.Fatal(err)
	}
	if !empty {
		t.Error("a directive with an empty target attribute did not present an empty target")
	}
}

func TestBaseExtractUnknownDirective(t *testing.T) {
	t.Parallel()
	base := NewBase("python", map[string]Handler{})
	got, err := base.Extract("nonsense", map[string]string{}, nil, nil, ".")
	if err != nil {
		t.Fatal(err)
	}
	want := "> *[selfdoc: unknown directive 'nonsense' for python extractor]*"
	if got != want {
		t.Fatalf("Extract = %q, want %q", got, want)
	}
}

func TestBaseDefaults(t *testing.T) {
	t.Parallel()
	base := NewBase("python", nil)

	if got := base.Name(); got != "python" {
		t.Errorf("Name = %q", got)
	}
	if got := base.FileExtensions(); len(got) != 0 {
		t.Errorf("FileExtensions = %#v, want none", got)
	}
	symbols, err := base.PublicSymbols("/x.py")
	if err != nil || len(symbols) != 0 {
		t.Errorf("PublicSymbols = (%#v, %v)", symbols, err)
	}
	if got := base.ResolvePath("core", []string{"src/"}, "/base"); got != "" {
		t.Errorf("ResolvePath = %q, want empty", got)
	}
	details, err := base.SymbolDetails("/x.py", "Foo")
	if err != nil || details != nil {
		t.Errorf("SymbolDetails = (%#v, %v)", details, err)
	}
	doc, err := base.ModuleDocstring("/x.py")
	if err != nil || doc != "" {
		t.Errorf("ModuleDocstring = (%q, %v)", doc, err)
	}
}

func TestStubExtractor(t *testing.T) {
	t.Parallel()
	stub := NewStub("swift")

	if got := stub.Name(); got != "swift" {
		t.Errorf("Name = %q, want swift", got)
	}
	if stub.Detect(t.TempDir()) {
		t.Error("the stub detected a project")
	}
	if got := stub.FileExtensions(); len(got) != 0 {
		t.Errorf("FileExtensions = %#v, want none", got)
	}
	symbols, err := stub.PublicSymbols("/some/file.swift")
	if err != nil || len(symbols) != 0 {
		t.Errorf("PublicSymbols = (%#v, %v)", symbols, err)
	}
	if got := stub.ResolvePath("Foo", []string{"src/"}, "/base"); got != "" {
		t.Errorf("ResolvePath = %q, want empty", got)
	}

	markdown, err := stub.Extract("ref", map[string]string{"path": "Foo"}, nil, []string{"src/"}, "/base")
	if err != nil {
		t.Fatal(err)
	}
	if want := "> *[selfdoc: no extractor for 'swift']*"; markdown != want {
		t.Fatalf("Extract = %q, want %q", markdown, want)
	}
}

// TestStubSatisfiesTheProtocol is the compile-time assertion that the stub is
// a complete extractor, which is what lets an unsupported language build.
var _ Extractor = NewStub("swift")
