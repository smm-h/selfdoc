package excludes

import (
	"reflect"
	"testing"
)

// probeNames is the name set every pattern below was run against in Python,
// so a row's want list is python3's answer for the same pattern.
var probeNames = []string{
	"a", "b", "c", "d", "e", "-", "]", "[", "z", "a-c", "ab", "x/y",
	"test_core.py", "tests", "foo_test.go", "[]",
}

// TestMatchReproducesPythonFnmatch pins the matcher against the answers
// Python's fnmatch gave for the same pattern and name set. The bracket rows
// exist because Python's set syntax differs from filepath.Match's in every
// corner: a leading "]", a first or last "-", a reversed range, an
// unterminated bracket.
func TestMatchReproducesPythonFnmatch(t *testing.T) {
	t.Parallel()
	tests := []struct {
		pattern string
		want    []string
	}{
		{"[a-c]", []string{"a", "b", "c"}},
		{"[-a]", []string{"a", "-"}},
		{"[a-]", []string{"a", "-"}},
		{"[z-a]", nil},
		{"[!a-c]", []string{"d", "e", "-", "]", "[", "z"}},
		{"[]]", []string{"]"}},
		{"[!]]", []string{"a", "b", "c", "d", "e", "-", "[", "z"}},
		{"[]", []string{"[]"}},
		{"[a-c-e]", []string{"a", "b", "c", "e", "-"}},
		{"[abc]", []string{"a", "b", "c"}},
		{"[!a]", []string{"b", "c", "d", "e", "-", "]", "[", "z"}},
		{"*", probeNames},
		{"?", []string{"a", "b", "c", "d", "e", "-", "]", "[", "z"}},
		{"*/*", []string{"x/y"}},
		{"a*c", []string{"a-c"}},
		{"test_*", []string{"test_core.py"}},
		{"*_test.*", []string{"foo_test.go"}},
		{"**/tests", nil},
	}
	for _, tc := range tests {
		t.Run(tc.pattern, func(t *testing.T) {
			t.Parallel()
			var got []string
			for _, name := range probeNames {
				if Match(name, tc.pattern) {
					got = append(got, name)
				}
			}
			if !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("%q matched %#v, want %#v", tc.pattern, got, tc.want)
			}
		})
	}
}

// TestMatchStarCrossesSlashes states the difference from filepath.Match that
// the exclusion patterns depend on.
func TestMatchStarCrossesSlashes(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name, pattern string
		want          bool
	}{
		{"pkg/internal/test_core.py", "*test_*", true},
		{"pkg/internal/core.py", "*test_*", false},
		{"a/b/c", "a*c", true},
		{"a/b/c", "a?b?c", true},
		{"", "*", true},
		{"", "", true},
		{"", "[a]", false},
		{"x", "", false},
		{"abc", "a**c", true},
	}
	for _, tc := range tests {
		t.Run(tc.name+" vs "+tc.pattern, func(t *testing.T) {
			t.Parallel()
			if got := Match(tc.name, tc.pattern); got != tc.want {
				t.Fatalf("Match(%q, %q) = %v, want %v", tc.name, tc.pattern, got, tc.want)
			}
		})
	}
}

func TestShouldSkipDir(t *testing.T) {
	t.Parallel()
	tests := []struct {
		dirname string
		want    bool
	}{
		{".venv", true},
		{"node_modules", true},
		{"__pycache__", true},
		{"zig-cache", true},
		{".zig-cache", true},
		{"mylib.egg-info", true},
		{"src", false},
		{"egg-info", false},
		{"", false},
	}
	for _, tc := range tests {
		t.Run(tc.dirname, func(t *testing.T) {
			t.Parallel()
			if got := ShouldSkipDir(tc.dirname); got != tc.want {
				t.Fatalf("ShouldSkipDir(%q) = %v, want %v", tc.dirname, got, tc.want)
			}
		})
	}
}

func TestIsExcluded(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		relPath  string
		patterns []string
		want     bool
	}{
		{"a basename pattern reaches any depth", "pkg/sub/test_core.py", DefaultExcludes, true},
		{"a suffix pattern reaches any depth", "pkg/sub/core_test.go", DefaultExcludes, true},
		{"a directory component is tested too", "pkg/tests/helper.py", DefaultExcludes, true},
		{"an ordinary file is not excluded", "pkg/sub/core.py", DefaultExcludes, false},
		{"the any-depth prefix is stripped", "pkg/sub/generated.py", []string{"**/generated.py"}, true},
		{"the any-depth prefix matches at the root too", "generated.py", []string{"**/generated.py"}, true},
		{"a path pattern matches the whole path", "docs/_build/x.md", []string{"docs/_build/*"}, true},
		{"no patterns excludes nothing", "anything/at/all.py", nil, false},
		{"the original spelling is tried as well", "a/b", []string{"**/a/b"}, true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := IsExcluded(tc.relPath, tc.patterns); got != tc.want {
				t.Fatalf("IsExcluded(%q, %#v) = %v, want %v", tc.relPath, tc.patterns, got, tc.want)
			}
		})
	}
}

func TestPatternsFor(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name   string
		config map[string]any
		want   []string
	}{
		{
			name:   "no gen block is the defaults alone",
			config: map[string]any{"gen": nil},
			want:   []string{"test_*", "*_test.*", "__pycache__", "tests"},
		},
		{
			name:   "an empty config is the defaults alone",
			config: map[string]any{},
			want:   []string{"test_*", "*_test.*", "__pycache__", "tests"},
		},
		{
			name:   "gen.exclude is appended after the defaults",
			config: map[string]any{"gen": map[string]any{"exclude": []any{"vendor/*", "*.pb.go"}}},
			want:   []string{"test_*", "*_test.*", "__pycache__", "tests", "vendor/*", "*.pb.go"},
		},
		{
			name:   "a gen block with no exclude is the defaults alone",
			config: map[string]any{"gen": map[string]any{}},
			want:   []string{"test_*", "*_test.*", "__pycache__", "tests"},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := PatternsFor(tc.config); !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("PatternsFor = %#v, want %#v", got, tc.want)
			}
		})
	}
}

// TestPatternsForDoesNotAliasTheDefaults guards the one way a caller could
// corrupt every later walk: appending to a returned slice that shares
// DefaultExcludes' backing array.
func TestPatternsForDoesNotAliasTheDefaults(t *testing.T) {
	t.Parallel()
	patterns := PatternsFor(map[string]any{})
	patterns = append(patterns, "clobber")
	if len(DefaultExcludes) != 4 || DefaultExcludes[0] != "test_*" {
		t.Fatalf("DefaultExcludes was reached through the returned slice: %#v", DefaultExcludes)
	}
	_ = patterns
}

func TestGoToolchainIgnoresDir(t *testing.T) {
	cases := map[string]bool{
		"testdata": true, "vendor": true, ".git": true, "_scratch": true,
		"internal": false, "cmd": false, "vendored": false, "mytestdata": false,
	}
	for name, want := range cases {
		if got := GoToolchainIgnoresDir(name); got != want {
			t.Errorf("GoToolchainIgnoresDir(%q) = %v, want %v", name, got, want)
		}
	}
}

func TestGoToolchainIgnoresPath(t *testing.T) {
	cases := map[string]bool{
		".":                      false,
		"":                       false,
		"internal/lint":          false,
		"internal/lint/testdata": true,
		"vendor/example.com/dep": true,
		"a/_b/c":                 true,
		"a/.b":                   true,
	}
	for relDir, want := range cases {
		if got := GoToolchainIgnoresPath(relDir); got != want {
			t.Errorf("GoToolchainIgnoresPath(%q) = %v, want %v", relDir, got, want)
		}
	}
}
