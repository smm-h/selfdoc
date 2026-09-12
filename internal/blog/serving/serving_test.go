package serving

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestTheDeclaredTypesAnswerTheExtensionsThePlatformGetsWrong(t *testing.T) {
	cases := []struct {
		path string
		want string
	}{
		{"index.html", "text/html; charset=utf-8"},
		{"app.js", "text/javascript; charset=utf-8"},
		{"app.mjs", "text/javascript; charset=utf-8"},
		{"style.css", "text/css; charset=utf-8"},
		{"nav.json", "application/json; charset=utf-8"},
		{"icon.svg", "image/svg+xml"},
		{"app.js.map", "application/json; charset=utf-8"},
		{"face.woff2", "font/woff2"},
		{"face.woff", "font/woff"},
		{"feed.xml", "application/xml; charset=utf-8"},
		{"robots.txt", "text/plain; charset=utf-8"},
		{"engine.wasm", "application/wasm"},
		{"site.webmanifest", "application/manifest+json"},
		// The extension is matched case-insensitively, and the declared table
		// wins over whatever the platform database says.
		{"INDEX.HTML", "text/html; charset=utf-8"},
		{"css/a/deep/style.CSS", "text/css; charset=utf-8"},
	}

	for _, testCase := range cases {
		if got := ContentType(testCase.path); got != testCase.want {
			t.Errorf("ContentType(%q) = %q, want %q", testCase.path, got, testCase.want)
		}
	}
}

func TestAnExtensionThePlatformKnowsIsServedAsThePlatformSaysIt(t *testing.T) {
	if got := ContentType("logo.png"); !strings.HasPrefix(got, "image/png") {
		t.Errorf("ContentType(\"logo.png\") = %q, want the platform's image/png", got)
	}
}

func TestAnUnknownExtensionIsServedAsBytes(t *testing.T) {
	for _, path := range []string{"payload.weird", "LICENSE", ".bashrc", "trailing."} {
		if got := ContentType(path); got != "application/octet-stream" {
			t.Errorf("ContentType(%q) = %q, want application/octet-stream", path, got)
		}
	}
}

func TestSplitExtIgnoresALeadingRunOfDots(t *testing.T) {
	cases := map[string]string{
		"a.html":      ".html",
		".bashrc":     "",
		"..hidden.md": ".md",
		"noext":       "",
		"a.":          ".",
		"dir.d/file":  "",
	}
	for path, want := range cases {
		if got := splitExt(path); got != want {
			t.Errorf("splitExt(%q) = %q, want %q", path, got, want)
		}
	}
}

// servedTree writes a root with one file in it and returns the root's
// symlink-free path, which is what every containment answer is measured
// against.
func servedTree(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "site", "alpha"), 0o755); err != nil {
		t.Fatalf("writing the tree: %v", err)
	}
	if err := os.WriteFile(filepath.Join(root, "site", "alpha", "index.html"), []byte("page"), 0o644); err != nil {
		t.Fatalf("writing the page: %v", err)
	}
	resolved, err := filepath.EvalSymlinks(root)
	if err != nil {
		t.Fatalf("resolving the root: %v", err)
	}
	return resolved
}

func TestAPathInsideTheRootResolves(t *testing.T) {
	root := servedTree(t)
	site := filepath.Join(root, "site")

	cases := map[string]string{
		"alpha/index.html": filepath.Join(site, "alpha", "index.html"),
		"alpha":            filepath.Join(site, "alpha"),
		"":                 site,
		"alpha/../alpha":   filepath.Join(site, "alpha"),
	}
	for rel, want := range cases {
		got, ok := ResolveUnder(site, rel)
		if !ok {
			t.Errorf("ResolveUnder(root, %q) refused a path inside the root", rel)
			continue
		}
		if got != want {
			t.Errorf("ResolveUnder(root, %q) = %q, want %q", rel, got, want)
		}
	}
}

func TestAnAddressThatDoesNotExistStillResolves(t *testing.T) {
	// Every 404 asks for one of these, so a missing tail is not a refusal.
	root := servedTree(t)
	site := filepath.Join(root, "site")
	got, ok := ResolveUnder(site, "nothing/here/index.html")
	if !ok {
		t.Fatal("ResolveUnder refused a path whose tail does not exist")
	}
	if want := filepath.Join(site, "nothing", "here", "index.html"); got != want {
		t.Errorf("ResolveUnder = %q, want %q", got, want)
	}
}

func TestAPathEscapingTheRootIsRefused(t *testing.T) {
	root := servedTree(t)
	site := filepath.Join(root, "site")
	for _, rel := range []string{"../../etc/passwd", "..", "alpha/../../outside"} {
		if _, ok := ResolveUnder(site, rel); ok {
			t.Errorf("ResolveUnder(root, %q) served a path outside the root", rel)
		}
	}
}

func TestASymlinkOutOfTheRootCannotBeFollowed(t *testing.T) {
	root := servedTree(t)
	site := filepath.Join(root, "site")
	outside := filepath.Join(root, "outside")
	if err := os.MkdirAll(outside, 0o755); err != nil {
		t.Fatalf("writing the outside tree: %v", err)
	}
	if err := os.WriteFile(filepath.Join(outside, "secret.txt"), []byte("x"), 0o644); err != nil {
		t.Fatalf("writing the outside file: %v", err)
	}
	if err := os.Symlink(outside, filepath.Join(site, "away")); err != nil {
		t.Skipf("this filesystem refuses symlinks: %v", err)
	}

	if _, ok := ResolveUnder(site, "away/secret.txt"); ok {
		t.Error("a link inside the tree was followed out of it")
	}
}

func TestASymlinkInsideTheRootIsFollowed(t *testing.T) {
	root := servedTree(t)
	site := filepath.Join(root, "site")
	if err := os.Symlink(filepath.Join(site, "alpha"), filepath.Join(site, "beta")); err != nil {
		t.Skipf("this filesystem refuses symlinks: %v", err)
	}

	got, ok := ResolveUnder(site, "beta/index.html")
	if !ok {
		t.Fatal("a link inside the tree was refused")
	}
	if want := filepath.Join(site, "alpha", "index.html"); got != want {
		t.Errorf("ResolveUnder = %q, want %q", got, want)
	}
}

func TestTheRootItselfIsInsideTheRoot(t *testing.T) {
	root := servedTree(t)
	got, ok := ResolveUnder(root, ".")
	if !ok || got != root {
		t.Errorf("ResolveUnder(root, \".\") = %q, %v; want the root itself", got, ok)
	}
}

func TestTheHostIsTheOneAddressEitherServerBinds(t *testing.T) {
	if Host != "127.0.0.1" {
		t.Errorf("Host = %q, want 127.0.0.1", Host)
	}
}
