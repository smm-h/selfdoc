package address

import (
	"path"
	"testing"
)

// TestPageAddress is the ported TestPageAddress class: the addressing
// authority itself, over every mount shape it has to answer for.
func TestPageAddress(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name              string
		pagePath          string
		coords            Coordinates
		mount             string
		outputKey         string
		stable            string
		pinned            string
		url               string
		depth             int
		toSiteRoot        string
		toMountRoot       string
		toStableMountRoot string
	}{
		{
			name:     "the current version carries no version segment",
			pagePath: "index.html",
			coords:   Coordinates{Locale: "en", Version: "1.0.0"},
			mount:    "en", outputKey: "en/index.html",
			stable: "en/", pinned: "en/v/1.0.0/", url: "en/",
			depth: 1, toSiteRoot: "../", toMountRoot: "", toStableMountRoot: "",
		},
		{
			name:     "an archived version sits under the archive prefix",
			pagePath: "index.html",
			coords:   Coordinates{Locale: "en", Version: "1.0.0", Archived: true},
			mount:    "en/v/1.0.0", outputKey: "en/v/1.0.0/index.html",
			stable: "en/", pinned: "en/v/1.0.0/", url: "en/v/1.0.0/",
			depth: 3, toSiteRoot: "../../../", toMountRoot: "",
			toStableMountRoot: "../../",
		},
		{
			name:     "one locale means no locale segment",
			pagePath: "guide/index.html",
			coords:   Coordinates{Version: "1.0.0"},
			mount:    "", outputKey: "guide/index.html",
			stable: "guide/", pinned: "v/1.0.0/guide/", url: "guide/",
			depth: 1, toSiteRoot: "../", toMountRoot: "../",
			toStableMountRoot: "../",
		},
		{
			name:     "a nested page at the current version",
			pagePath: "guide/index.html",
			coords:   Coordinates{Locale: "en", Version: "1.0.0"},
			mount:    "en", outputKey: "en/guide/index.html",
			stable: "en/guide/", pinned: "en/v/1.0.0/guide/", url: "en/guide/",
			depth: 2, toSiteRoot: "../../", toMountRoot: "../",
			toStableMountRoot: "../",
		},
		{
			name:     "a nested archived page",
			pagePath: "guide/index.html",
			coords:   Coordinates{Locale: "en", Version: "1.0.0", Archived: true},
			mount:    "en/v/1.0.0", outputKey: "en/v/1.0.0/guide/index.html",
			stable: "en/guide/", pinned: "en/v/1.0.0/guide/",
			url:   "en/v/1.0.0/guide/",
			depth: 4, toSiteRoot: "../../../../", toMountRoot: "../",
			// Two levels further out than ToMountRoot: over v/<version>/.
			toStableMountRoot: "../../../",
		},
		{
			name:      "a deeply nested archived page",
			pagePath:  "reference/deep/notes/index.html",
			coords:    Coordinates{Locale: "fa", Version: "0.2.0", Archived: true},
			mount:     "fa/v/0.2.0",
			outputKey: "fa/v/0.2.0/reference/deep/notes/index.html",
			stable:    "fa/reference/deep/notes/",
			pinned:    "fa/v/0.2.0/reference/deep/notes/",
			url:       "fa/v/0.2.0/reference/deep/notes/",
			depth:     6, toSiteRoot: "../../../../../../", toMountRoot: "../../../",
			toStableMountRoot: "../../../../../",
		},
		{
			name:     "an unversioned page keeps its locale",
			pagePath: "about/index.html",
			coords:   Coordinates{Locale: "en"},
			mount:    "en", outputKey: "en/about/index.html",
			stable: "en/about/", pinned: "en/about/", url: "en/about/",
			depth: 2, toSiteRoot: "../../", toMountRoot: "../",
			toStableMountRoot: "../",
		},
		{
			name:     "no mount at all",
			pagePath: "blog/hello/index.html",
			coords:   Coordinates{},
			mount:    "", outputKey: "blog/hello/index.html",
			stable: "blog/hello/", pinned: "blog/hello/", url: "blog/hello/",
			depth: 2, toSiteRoot: "../../", toMountRoot: "../../",
			toStableMountRoot: "../../",
		},
		{
			name:     "a unified site mounts each constituent under its slug",
			pagePath: "guide/index.html",
			coords:   Coordinates{Locale: "en", Project: "core", Version: "1.0.0"},
			mount:    "en/core", outputKey: "en/core/guide/index.html",
			stable: "en/core/guide/", pinned: "en/core/v/1.0.0/guide/",
			url:   "en/core/guide/",
			depth: 3, toSiteRoot: "../../../", toMountRoot: "../",
			toStableMountRoot: "../",
		},
		{
			name:     "a unified archived page",
			pagePath: "guide/index.html",
			coords: Coordinates{
				Locale: "en", Project: "core", Version: "1.0.0", Archived: true,
			},
			mount:     "en/core/v/1.0.0",
			outputKey: "en/core/v/1.0.0/guide/index.html",
			stable:    "en/core/guide/", pinned: "en/core/v/1.0.0/guide/",
			url:   "en/core/v/1.0.0/guide/",
			depth: 5, toSiteRoot: "../../../../../", toMountRoot: "../",
			toStableMountRoot: "../../../",
		},
		{
			name:     "a unified unversioned page",
			pagePath: "about/index.html",
			coords:   Coordinates{Locale: "en", Project: "core"},
			mount:    "en/core", outputKey: "en/core/about/index.html",
			stable: "en/core/about/", pinned: "en/core/about/",
			url:   "en/core/about/",
			depth: 3, toSiteRoot: "../../../", toMountRoot: "../",
			toStableMountRoot: "../",
		},
		{
			name:     "a project with no locale is a single-locale unified site",
			pagePath: "index.html",
			coords:   Coordinates{Project: "core"},
			mount:    "core", outputKey: "core/index.html",
			stable: "core/", pinned: "core/", url: "core/",
			depth: 1, toSiteRoot: "../", toMountRoot: "",
			toStableMountRoot: "",
		},
		{
			name:     "a bare version needs no locale",
			pagePath: "index.html",
			coords:   Coordinates{Version: "1.0.0", Archived: true},
			mount:    "v/1.0.0", outputKey: "v/1.0.0/index.html",
			stable: "", pinned: "v/1.0.0/", url: "v/1.0.0/",
			depth: 2, toSiteRoot: "../../", toMountRoot: "",
			toStableMountRoot: "../../",
		},
		{
			name:     "a page that is not a directory index keeps its filename",
			pagePath: "404.html",
			coords:   Coordinates{Locale: "en", Version: "1.0.0"},
			mount:    "en", outputKey: "en/404.html",
			stable: "en/404.html", pinned: "en/v/1.0.0/404.html",
			url:   "en/404.html",
			depth: 1, toSiteRoot: "../", toMountRoot: "",
			toStableMountRoot: "",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			addr, err := NewPageAddress(tt.pagePath, tt.coords)
			if err != nil {
				t.Fatalf("NewPageAddress() error = %v", err)
			}
			checks := []struct {
				field, got, want string
			}{
				{"Mount", addr.Mount, tt.mount},
				{"OutputKey", addr.OutputKey, tt.outputKey},
				{"Stable", addr.Stable, tt.stable},
				{"Pinned", addr.Pinned, tt.pinned},
				{"URL()", addr.URL(), tt.url},
				{"ToSiteRoot()", addr.ToSiteRoot(), tt.toSiteRoot},
				{"ToMountRoot()", addr.ToMountRoot(), tt.toMountRoot},
				{"ToStableMountRoot()", addr.ToStableMountRoot(), tt.toStableMountRoot},
			}
			for _, c := range checks {
				if c.got != c.want {
					t.Errorf("%s = %q, want %q", c.field, c.got, c.want)
				}
			}
			if addr.Depth != tt.depth {
				t.Errorf("Depth = %d, want %d", addr.Depth, tt.depth)
			}
			if addr.PagePath != tt.pagePath {
				t.Errorf("PagePath = %q, want %q", addr.PagePath, tt.pagePath)
			}
			if addr.Locale != tt.coords.Locale || addr.Project != tt.coords.Project ||
				addr.Version != tt.coords.Version || addr.Archived != tt.coords.Archived {
				t.Errorf("coordinates were not carried through: %+v", addr)
			}
		})
	}
}

// TestStableAndArchiveMount pins the two mount accessors, which the pickers
// read to build a cross-version link.
func TestStableAndArchiveMount(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name                      string
		coords                    Coordinates
		stableMount, archiveMount string
	}{
		{
			"a locale and a version",
			Coordinates{Locale: "en", Version: "1.0"}, "en", "en/v/1.0",
		},
		{
			"an archived page names the same two mounts",
			Coordinates{Locale: "en", Version: "1.0", Archived: true},
			"en", "en/v/1.0",
		},
		{
			"no version means the archive mount is the stable one",
			Coordinates{Locale: "en"}, "en", "en",
		},
		{"no mount at all", Coordinates{}, "", ""},
		{
			"a unified project",
			Coordinates{Locale: "en", Project: "core", Version: "1.0"},
			"en/core", "en/core/v/1.0",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			addr, err := NewPageAddress("index.html", tt.coords)
			if err != nil {
				t.Fatalf("NewPageAddress() error = %v", err)
			}
			if got := addr.StableMount(); got != tt.stableMount {
				t.Errorf("StableMount() = %q, want %q", got, tt.stableMount)
			}
			if got := addr.ArchiveMount(); got != tt.archiveMount {
				t.Errorf("ArchiveMount() = %q, want %q", got, tt.archiveMount)
			}
		})
	}
}

// TestSiteRootHopReachesTheOutputRoot is the ported property test: resolving
// the output key's directory against ToSiteRoot lands on ".".
func TestSiteRootHopReachesTheOutputRoot(t *testing.T) {
	t.Parallel()
	for _, page := range []string{"index.html", "guide/index.html", "a/b/c/index.html"} {
		for _, archived := range []bool{false, true} {
			addr, err := NewPageAddress(page, Coordinates{
				Locale: "en", Version: "1.0.0", Archived: archived,
			})
			if err != nil {
				t.Fatalf("NewPageAddress(%q) error = %v", page, err)
			}
			if got := resolve(addr.OutputKey, addr.ToSiteRoot()); got != "." {
				t.Errorf("%q + %q resolves to %q, want \".\"",
					addr.OutputKey, addr.ToSiteRoot(), got)
			}
		}
	}
}

// TestMountRootHopReachesTheMountRoot is the ported property test for the hop
// to a page's own mount, at both the stable and the archive address.
func TestMountRootHopReachesTheMountRoot(t *testing.T) {
	t.Parallel()
	for _, page := range []string{"index.html", "guide/index.html", "a/b/c/index.html"} {
		addr, err := NewPageAddress(page, Coordinates{Locale: "en", Version: "1.0.0"})
		if err != nil {
			t.Fatalf("NewPageAddress(%q) error = %v", page, err)
		}
		if got := resolve(addr.OutputKey, addr.ToMountRoot()); got != "en" {
			t.Errorf("%q + %q resolves to %q, want \"en\"",
				addr.OutputKey, addr.ToMountRoot(), got)
		}
		archived, err := NewPageAddress(page, Coordinates{
			Locale: "en", Version: "1.0.0", Archived: true,
		})
		if err != nil {
			t.Fatalf("NewPageAddress(%q) error = %v", page, err)
		}
		if got := resolve(archived.OutputKey, archived.ToMountRoot()); got != "en/v/1.0.0" {
			t.Errorf("%q + %q resolves to %q, want \"en/v/1.0.0\"",
				archived.OutputKey, archived.ToMountRoot(), got)
		}
	}
}

// TestStableMountHopReachesTheStableMount is the ported property test: from an
// archive page, the hop lands on the current version's mount.
func TestStableMountHopReachesTheStableMount(t *testing.T) {
	t.Parallel()
	for _, page := range []string{"index.html", "guide/index.html", "a/b/c/index.html"} {
		addr, err := NewPageAddress(page, Coordinates{
			Locale: "en", Version: "1.0.0", Archived: true,
		})
		if err != nil {
			t.Fatalf("NewPageAddress(%q) error = %v", page, err)
		}
		if got := resolve(addr.OutputKey, addr.ToStableMountRoot()); got != "en" {
			t.Errorf("%q + %q resolves to %q, want \"en\"",
				addr.OutputKey, addr.ToStableMountRoot(), got)
		}
	}
}

// resolve joins a page's directory with a relative hop and normalizes it, the
// way a browser resolves a document-relative reference.
func resolve(outputKey, hop string) string {
	if hop == "" {
		hop = "."
	}
	return path.Clean(path.Join(path.Dir(outputKey), hop))
}

// TestPageAddressErrors pins every validation error and its message, which is
// the text the Python's ValueError carried.
func TestPageAddressErrors(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		pagePath string
		coords   Coordinates
		want     string
	}{
		{
			name:     "an empty page path",
			pagePath: "",
			coords:   Coordinates{Locale: "en", Version: "1.0.0"},
			want:     "page_path must be a non-empty relative HTML path",
		},
		{
			name:     "an absolute page path",
			pagePath: "/index.html",
			coords:   Coordinates{Locale: "en", Version: "1.0.0"},
			want:     `page_path must be relative to the mount root, got '/index.html'`,
		},
		{
			name:     "the reserved archive segment",
			pagePath: "v/index.html",
			coords:   Coordinates{Locale: "en", Version: "1.0.0"},
			want: "page path 'v/index.html' starts with the reserved segment " +
				"'v'/, which is where superseded versions are emitted. " +
				"Rename the page.",
		},
		{
			name:     "a top-level page named v",
			pagePath: "v",
			coords:   Coordinates{},
			want: "page path 'v' starts with the reserved segment 'v'/, " +
				"which is where superseded versions are emitted. " +
				"Rename the page.",
		},
		{
			name:     "archived with no version",
			pagePath: "index.html",
			coords:   Coordinates{Locale: "en", Archived: true},
			want: "archived=True needs a version: an archive address is " +
				"v/<version>/<page>/ and there is no version to name",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			_, err := NewPageAddress(tt.pagePath, tt.coords)
			if err == nil {
				t.Fatalf("NewPageAddress() error = nil, want %q", tt.want)
			}
			if err.Error() != tt.want {
				t.Errorf("NewPageAddress() error =\n%q\nwant\n%q", err, tt.want)
			}
		})
	}
}

// TestPageAddressAcceptsAQuotableName checks the repr helper is only reached
// by the error paths: a path carrying an apostrophe addresses fine.
func TestPageAddressAcceptsAQuotableName(t *testing.T) {
	t.Parallel()
	addr, err := NewPageAddress("it's/x.html", Coordinates{})
	if err != nil {
		t.Fatalf("NewPageAddress() error = %v", err)
	}
	if addr.OutputKey != "it's/x.html" || addr.Stable != "it's/x.html" {
		t.Errorf("addr = %+v", addr)
	}
}

// TestLocaleSegment is the ported TestLocaleSegment class: the one place that
// decides whether a mount carries a locale.
func TestLocaleSegment(t *testing.T) {
	t.Parallel()
	type locale struct {
		Code    string
		Label   string
		Default bool
	}
	one := []locale{{Code: "en", Label: "English", Default: true}}
	two := []locale{
		{Code: "en", Label: "English", Default: true},
		{Code: "fa", Label: "Persian"},
	}
	if got := LocaleSegment("en", one); got != "" {
		t.Errorf("a single locale yields %q, want \"\"", got)
	}
	if got := LocaleSegment("en", two); got != "en" {
		t.Errorf("LocaleSegment(\"en\", two) = %q, want \"en\"", got)
	}
	if got := LocaleSegment("fa", two); got != "fa" {
		t.Errorf("LocaleSegment(\"fa\", two) = %q, want \"fa\"", got)
	}
	if got := LocaleSegment("en", []locale{}); got != "" {
		t.Errorf("an empty locale list yields %q, want \"\"", got)
	}
	if got := LocaleSegment[locale]("en", nil); got != "" {
		t.Errorf("a nil locale list yields %q, want \"\"", got)
	}
}

// TestIsSiteLevel covers both forms the build speaks -- an output path and a
// URL path -- and the near miss that must stay a project page.
func TestIsSiteLevel(t *testing.T) {
	t.Parallel()
	tests := []struct {
		path string
		want bool
	}{
		{"blog/hello/index.html", true},
		{"blog/hello/", true},
		{"blog/", true},
		{"blog", true},
		{"/blog/hello/", true},
		{"//blog/x", true},
		{"blog.md", true},
		{"blog.html", true},
		{"blog.md/x", true},
		{"blog-guide/", false},
		{"guide/", false},
		{"BLOG/", false},
		{"", false},
	}
	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			t.Parallel()
			if got := IsSiteLevel(tt.path); got != tt.want {
				t.Errorf("IsSiteLevel(%q) = %v, want %v", tt.path, got, tt.want)
			}
		})
	}
}

// TestRootPageLink pins the single hop a root-level page writes to a sibling.
func TestRootPageLink(t *testing.T) {
	t.Parallel()
	tests := []struct{ in, want string }{
		{"index.md", "../"},
		{"guide.md", "../guide/"},
		{"guide", "../guide/"},
		{"index", "../"},
		{"a.b.md", "../a.b/"},
	}
	for _, tt := range tests {
		t.Run(tt.in, func(t *testing.T) {
			t.Parallel()
			if got := RootPageLink(tt.in); got != tt.want {
				t.Errorf("RootPageLink(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

// TestPrefixes pins the two reserved segments the scheme is built on.
func TestPrefixes(t *testing.T) {
	t.Parallel()
	if ArchivePrefix != "v" {
		t.Errorf("ArchivePrefix = %q, want \"v\"", ArchivePrefix)
	}
	if PostsPrefix != "blog" {
		t.Errorf("PostsPrefix = %q, want \"blog\"", PostsPrefix)
	}
}
