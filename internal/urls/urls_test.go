package urls

import (
	"strings"
	"testing"
)

// Both builders must satisfy the interface, which is the Go counterpart of the
// two isinstance(b, URLBuilder) assertions in the Python suite.
var (
	_ URLBuilder = (*SimpleURLBuilder)(nil)
	_ URLBuilder = (*TopologyURLBuilder)(nil)
)

// TestSimpleURLBuilderPageURL is the ported TestSimpleURLBuilderPageUrl class.
func TestSimpleURLBuilderPageURL(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name    string
		baseURL string
		path    string
		want    string
	}{
		{"a simple path", "https://example.com", "guide/", "https://example.com/guide/"},
		{
			"a nested path", "https://example.com", "en/1.0.0/guide/",
			"https://example.com/en/1.0.0/guide/",
		},
		{"an html path", "https://example.com", "index.html", "https://example.com/index.html"},
		{"an empty path", "https://example.com", "", "https://example.com/"},
		{"a leading slash is stripped", "https://example.com", "/guide/", "https://example.com/guide/"},
		{"a trailing slash on the base", "https://example.com/", "guide/", "https://example.com/guide/"},
		{
			"several trailing slashes on the base", "https://example.com///",
			"guide/", "https://example.com/guide/",
		},
		{"a path that is just a slash", "https://example.com", "/", "https://example.com/"},
		{"a query string is preserved", "https://example.com", "?q=test", "https://example.com/?q=test"},
		{"a fragment is preserved", "https://example.com", "#section", "https://example.com/#section"},
		{"an http scheme with a port", "http://localhost:8080", "guide/", "http://localhost:8080/guide/"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := NewSimpleURLBuilder(tt.baseURL).PageURL(tt.path); got != tt.want {
				t.Errorf("PageURL(%q) = %q, want %q", tt.path, got, tt.want)
			}
		})
	}
}

// TestSimpleURLBuilderNeverDoublesASlash ports the edge case that a trailing
// slash on the base and a leading slash on the path cannot collide.
func TestSimpleURLBuilderNeverDoublesASlash(t *testing.T) {
	t.Parallel()
	url := NewSimpleURLBuilder("https://example.com/").PageURL("/guide/")
	if after := strings.SplitN(url, "://", 2)[1]; strings.Contains(after, "//") {
		t.Errorf("PageURL() = %q, which doubles a slash", url)
	}
}

// TestSimpleURLBuilderAssetURL is the ported TestSimpleURLBuilderAssetUrl
// class.
func TestSimpleURLBuilderAssetURL(t *testing.T) {
	t.Parallel()
	tests := []struct{ path, want string }{
		{"og-index.png", "https://example.com/og-index.png"},
		{"style.css", "https://example.com/style.css"},
		{"", "https://example.com/"},
		{"en/sitemap.xml", "https://example.com/en/sitemap.xml"},
	}
	b := NewSimpleURLBuilder("https://example.com")
	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			t.Parallel()
			if got := b.AssetURL(tt.path); got != tt.want {
				t.Errorf("AssetURL(%q) = %q, want %q", tt.path, got, tt.want)
			}
		})
	}
}

// TestSimpleURLBuilderFeedURL is the ported TestSimpleURLBuilderFeedUrl class.
func TestSimpleURLBuilderFeedURL(t *testing.T) {
	t.Parallel()
	for _, base := range []string{"https://example.com", "https://example.com/"} {
		want := "https://example.com/feed.xml"
		if got := NewSimpleURLBuilder(base).FeedURL(); got != want {
			t.Errorf("NewSimpleURLBuilder(%q).FeedURL() = %q, want %q", base, got, want)
		}
	}
}

// TestSimpleURLBuilderBase is the ported TestSimpleURLBuilderBase class.
func TestSimpleURLBuilderBase(t *testing.T) {
	t.Parallel()
	tests := []struct{ baseURL, want string }{
		{"https://example.com", "https://example.com"},
		{"https://example.com/", "https://example.com"},
		{"https://example.com/docs", "https://example.com/docs"},
		{"https://example.com/docs/", "https://example.com/docs"},
		{"http://localhost:8080", "http://localhost:8080"},
	}
	for _, tt := range tests {
		t.Run(tt.baseURL, func(t *testing.T) {
			t.Parallel()
			if got := NewSimpleURLBuilder(tt.baseURL).Base(); got != tt.want {
				t.Errorf("Base() = %q, want %q", got, tt.want)
			}
		})
	}
}

// TestSimpleURLBuilderIsNotMounted pins the three mount answers a standalone
// project gives.
func TestSimpleURLBuilderIsNotMounted(t *testing.T) {
	t.Parallel()
	b := NewSimpleURLBuilder("https://example.com")
	if b.Mounted() {
		t.Error("Mounted() = true, want false")
	}
	if got := b.MountPrefix(); got != "" {
		t.Errorf("MountPrefix() = %q, want \"\"", got)
	}
	if got, want := b.SiteRoot(), "https://example.com/"; got != want {
		t.Errorf("SiteRoot() = %q, want %q", got, want)
	}
}

// TestTopologyURLBuilderPageURL is the ported TestTopologyURLBuilderPageUrl
// class.
func TestTopologyURLBuilderPageURL(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name     string
		docsBase string
		path     string
		want     string
	}{
		{
			"a simple path", "https://docs.smmh.dev", "guide/",
			"https://docs.smmh.dev/selfdoc/guide/",
		},
		{
			"a nested path", "https://docs.smmh.dev", "en/1.0.0/guide/",
			"https://docs.smmh.dev/selfdoc/en/1.0.0/guide/",
		},
		{"an empty path", "https://docs.smmh.dev", "", "https://docs.smmh.dev/selfdoc/"},
		{
			"a leading slash is stripped", "https://docs.smmh.dev", "/guide/",
			"https://docs.smmh.dev/selfdoc/guide/",
		},
		{
			"a trailing slash on the base is stripped", "https://docs.smmh.dev/",
			"guide/", "https://docs.smmh.dev/selfdoc/guide/",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			b := NewTopologyURLBuilder(tt.docsBase, "selfdoc")
			if got := b.PageURL(tt.path); got != tt.want {
				t.Errorf("PageURL(%q) = %q, want %q", tt.path, got, tt.want)
			}
		})
	}
}

// TestTopologyURLBuilderSiteLevelPaths is the ported
// TestTopologyURLBuilderSiteLevelPaths class.
//
// Posts are the site's, not the project's, and drop the slug: the assembly
// serves every project's posts from one shared "blog/" at the site root. A URL
// carrying the slug names an address the site does not serve, which is what a
// project page's link to its own post used to be.
func TestTopologyURLBuilderSiteLevelPaths(t *testing.T) {
	t.Parallel()
	b := NewTopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
	tests := []struct {
		name string
		path string
		want string
	}{
		{"a post drops the slug", "blog/hello/", "https://docs.smmh.dev/blog/hello/"},
		{"the blog index drops the slug", "blog/", "https://docs.smmh.dev/blog/"},
		{
			// "blog-guide/" is documentation about blogging, not a post.
			"a page merely starting with blog keeps the slug", "blog-guide/",
			"https://docs.smmh.dev/selfdoc/blog-guide/",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := b.PageURL(tt.path); got != tt.want {
				t.Errorf("PageURL(%q) = %q, want %q", tt.path, got, tt.want)
			}
		})
	}

	// A post's OG card is the project's file, in the project's subtree.
	want := "https://docs.smmh.dev/selfdoc/og-blog-hello.png"
	if got := b.AssetURL("og-blog-hello.png"); got != want {
		t.Errorf("AssetURL() = %q, want %q", got, want)
	}
}

// TestTopologyURLBuilderIsMounted pins the three mount answers a mounted
// project gives.
func TestTopologyURLBuilderIsMounted(t *testing.T) {
	t.Parallel()
	b := NewTopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
	if !b.Mounted() {
		t.Error("Mounted() = false, want true")
	}
	if got, want := b.MountPrefix(), "selfdoc/"; got != want {
		t.Errorf("MountPrefix() = %q, want %q", got, want)
	}
	if got, want := b.SiteRoot(), "https://docs.smmh.dev/"; got != want {
		t.Errorf("SiteRoot() = %q, want %q", got, want)
	}
}

// TestTopologyURLBuilderAssetAndFeedURL is the ported pair of asset and feed
// classes.
func TestTopologyURLBuilderAssetAndFeedURL(t *testing.T) {
	t.Parallel()
	b := NewTopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
	if got, want := b.AssetURL("og-index.png"), "https://docs.smmh.dev/selfdoc/og-index.png"; got != want {
		t.Errorf("AssetURL() = %q, want %q", got, want)
	}
	if got, want := b.AssetURL(""), "https://docs.smmh.dev/selfdoc/"; got != want {
		t.Errorf("AssetURL(\"\") = %q, want %q", got, want)
	}
	if got, want := b.FeedURL(), "https://docs.smmh.dev/selfdoc/feed.xml"; got != want {
		t.Errorf("FeedURL() = %q, want %q", got, want)
	}
}

// TestTopologyURLBuilderBase is the ported TestTopologyURLBuilderBase class.
func TestTopologyURLBuilderBase(t *testing.T) {
	t.Parallel()
	for _, base := range []string{"https://docs.smmh.dev", "https://docs.smmh.dev/"} {
		want := "https://docs.smmh.dev/selfdoc"
		if got := NewTopologyURLBuilder(base, "selfdoc").Base(); got != want {
			t.Errorf("NewTopologyURLBuilder(%q, ...).Base() = %q, want %q", base, got, want)
		}
	}
}

// TestCrossProjectURL asserts that a link into another project is the docs
// base, that project's slug and the path -- for every slug, with nothing
// declared per project anywhere.
func TestCrossProjectURL(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		slug string
		path string
		want string
	}{
		{
			name: "a project on the site",
			slug: "rlsbl", path: "guide/",
			want: "https://docs.smmh.dev/rlsbl/guide/",
		},
		{
			name: "an empty path is the project's front page",
			slug: "rlsbl", path: "",
			want: "https://docs.smmh.dev/rlsbl/",
		},
		{
			name: "a slug nothing declares resolves the same way",
			slug: "unknown", path: "page/",
			want: "https://docs.smmh.dev/unknown/page/",
		},
		{
			name: "a leading slash on the path is stripped",
			slug: "rlsbl", path: "/guide/",
			want: "https://docs.smmh.dev/rlsbl/guide/",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			b := NewTopologyURLBuilder("https://docs.smmh.dev", "selfdoc")
			if got := b.CrossProjectURL(tt.slug, tt.path); got != tt.want {
				t.Errorf("CrossProjectURL(%q, %q) = %q, want %q",
					tt.slug, tt.path, got, tt.want)
			}
		})
	}
}
