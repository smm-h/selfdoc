package icons

import (
	"crypto/sha256"
	"encoding/hex"
	"sort"
	"strings"
	"testing"
)

// pythonCorpusDigest is the SHA-256 of the whole icon corpus as the Python
// implementation rendered it, produced by walking every canonical name and
// every alias in sorted order, asking for each of the three modes, and joining
// "<name>|<mode>|<svg>" lines with newlines (a mode with no icon contributing
// an empty svg field).
//
// It is the byte-for-byte check on the copied SVG strings: a single changed
// character in any of the 42 documents, a dropped alias, or a mode dispatched
// to the wrong variant moves the digest.
const pythonCorpusDigest = "2a9d6a42f7cc319ba0f1f6a42d2dcf9152b0516e401b0c8729f432d15ceca16d"

func corpusDigest() string {
	names := make([]string, 0, len(icons)+len(aliases))
	seen := map[string]bool{}
	for name := range icons {
		if !seen[name] {
			seen[name] = true
			names = append(names, name)
		}
	}
	for name := range aliases {
		if !seen[name] {
			seen[name] = true
			names = append(names, name)
		}
	}
	sort.Strings(names)

	var parts []string
	for _, name := range names {
		for _, mode := range ValidCodeIconModes {
			svg, _ := GetIcon(name, mode)
			parts = append(parts, name+"|"+mode+"|"+svg)
		}
	}
	sum := sha256.Sum256([]byte(strings.Join(parts, "\n")))
	return hex.EncodeToString(sum[:])
}

// TestCorpusMatchesPython is the byte-for-byte assertion over every SVG.
func TestCorpusMatchesPython(t *testing.T) {
	t.Parallel()
	if got := corpusDigest(); got != pythonCorpusDigest {
		t.Errorf("icon corpus digest = %s, want %s", got, pythonCorpusDigest)
	}
}

// TestCorpusSize pins the shape the digest is computed over, so a change that
// added a language and removed another could not keep the digest test honest
// on its own.
func TestCorpusSize(t *testing.T) {
	t.Parallel()
	if len(icons) != 21 {
		t.Errorf("len(icons) = %d, want 21", len(icons))
	}
	if len(aliases) != 14 {
		t.Errorf("len(aliases) = %d, want 14", len(aliases))
	}
}

// TestGetIcon covers the dispatch rules: mode selection, case folding, alias
// resolution, the "none" mode and an unknown language.
func TestGetIcon(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		language string
		mode     string
		wantOK   bool
		want     string
	}{
		{
			name:     "colorful is the brand variant",
			language: "go",
			mode:     "colorful",
			wantOK:   true,
			want:     icons["go"].Colorful,
		},
		{
			name:     "monochrome is the currentColor variant",
			language: "go",
			mode:     "monochrome",
			wantOK:   true,
			want:     icons["go"].Monochrome,
		},
		{
			name:     "none reports no icon",
			language: "go",
			mode:     "none",
			wantOK:   false,
		},
		{
			name:     "none wins over a known language",
			language: "python",
			mode:     "none",
			wantOK:   false,
		},
		{
			name:     "an unrecognized mode falls to colorful",
			language: "go",
			mode:     "sepia",
			wantOK:   true,
			want:     icons["go"].Colorful,
		},
		{
			name:     "the language is matched case-insensitively",
			language: "PYTHON",
			mode:     "colorful",
			wantOK:   true,
			want:     icons["python"].Colorful,
		},
		{
			name:     "js resolves to javascript",
			language: "js",
			mode:     "colorful",
			wantOK:   true,
			want:     icons["javascript"].Colorful,
		},
		{
			name:     "sh resolves to bash",
			language: "sh",
			mode:     "monochrome",
			wantOK:   true,
			want:     icons["bash"].Monochrome,
		},
		{
			name:     "an alias is matched case-insensitively too",
			language: "Dockerfile",
			mode:     "colorful",
			wantOK:   true,
			want:     icons["docker"].Colorful,
		},
		{
			name:     "c++ resolves to cpp",
			language: "c++",
			mode:     "colorful",
			wantOK:   true,
			want:     icons["cpp"].Colorful,
		},
		{
			name:     "an unknown language has no icon",
			language: "brainfuck",
			mode:     "colorful",
			wantOK:   false,
		},
		{
			name:     "the empty language has no icon",
			language: "",
			mode:     "colorful",
			wantOK:   false,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, ok := GetIcon(tt.language, tt.mode)
			if ok != tt.wantOK {
				t.Fatalf("GetIcon(%q, %q) ok = %v, want %v", tt.language, tt.mode, ok, tt.wantOK)
			}
			if got != tt.want {
				t.Errorf("GetIcon(%q, %q) = %q, want %q", tt.language, tt.mode, got, tt.want)
			}
		})
	}
}

// TestEveryIconIsSizedAndSmall pins the two invariants the package docstring
// declares: the shared viewBox, and the 500-byte budget.
func TestEveryIconIsSizedAndSmall(t *testing.T) {
	t.Parallel()
	for name, icon := range icons {
		for variant, svg := range map[string]string{
			"colorful": icon.Colorful, "monochrome": icon.Monochrome,
		} {
			if !strings.Contains(svg, `viewBox="0 0 16 16"`) {
				t.Errorf("%s/%s has no 16x16 viewBox", name, variant)
			}
			if len(svg) >= 500 {
				t.Errorf("%s/%s is %d bytes, want under 500", name, variant, len(svg))
			}
		}
	}
}

// TestEveryAliasResolves guards against an alias naming a language the table
// does not carry, which would silently mean no icon.
func TestEveryAliasResolves(t *testing.T) {
	t.Parallel()
	for alias, canonical := range aliases {
		if _, ok := icons[canonical]; !ok {
			t.Errorf("alias %q names %q, which has no icon", alias, canonical)
		}
	}
}

// TestValidCodeIconModes pins the declared modes and their order.
func TestValidCodeIconModes(t *testing.T) {
	t.Parallel()
	want := []string{"colorful", "monochrome", "none"}
	if len(ValidCodeIconModes) != len(want) {
		t.Fatalf("ValidCodeIconModes = %q, want %q", ValidCodeIconModes, want)
	}
	for i := range want {
		if ValidCodeIconModes[i] != want[i] {
			t.Errorf("ValidCodeIconModes[%d] = %q, want %q", i, ValidCodeIconModes[i], want[i])
		}
	}
}
