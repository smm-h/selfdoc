package verify

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/smm-h/selfdoc/internal/blog/shared"
)

// breakEverything injects one defect per asserted property, in a fixed order.
//
// The order and the exact content are shared with
// testdata/record_python_report.py, which builds the same tree under the
// Python this package replaces: the recording it produced is what
// TestTheReportIsByteIdenticalToThePython compares against, so a change here
// is a re-recording rather than an edit.
func breakEverything(t *testing.T, root string) {
	t.Helper()
	siteDir := filepath.Join(root, "site")

	writeFile(t, filepath.Join(siteDir, "gamma", "index.html"),
		page("Gamma", canonicalBase+"/gamma/", pageOptions{
			CSSHref: chromeRef(t, "gamma/index.html"),
		}))
	writeFile(t, filepath.Join(siteDir, "beta", "index.html"),
		page("Beta", canonicalBase+"/beta/", pageOptions{
			Version: "1.9.0", CSSHref: chromeRef(t, "beta/index.html"),
		}))
	removeFile(t, filepath.Join(siteDir, "alpha", "guide", "index.html"))
	removeFile(t, filepath.Join(siteDir, "robots.txt"))
	writeFile(t, filepath.Join(siteDir, "cv", "index.html"),
		page("", canonicalBase+"/cv/", pageOptions{
			CSSHref: chromeRef(t, "cv/index.html"),
		}))
	blogIndex := filepath.Join(siteDir, "blog", "index.html")
	writeFile(t, blogIndex,
		stylesheetLinkRE.ReplaceAllString(readFile(t, blogIndex), ""))
	writeFile(t, filepath.Join(siteDir, "blog", "hello", "index.html"),
		page("Hello", canonicalBase+"/blog/hello/", pageOptions{
			Version: "1.0.0",
			Body: "<blockquote><em>[selfdoc: python_ref target=x " +
				"— not yet resolved]</em></blockquote>",
			CSSHref: chromeRef(t, "blog/hello/index.html"),
		}))
	writeFile(t, filepath.Join(siteDir, "alpha", "_headers"), "leaked")
	sitemap := filepath.Join(siteDir, "sitemap.xml")
	writeFile(t, sitemap, strings.Replace(readFile(t, sitemap), "</urlset>",
		"  <url><loc>https://old.example.net/alpha/</loc></url>\n</urlset>", 1))
}

// TestTheReportIsByteIdenticalToThePython holds the whole rendered report to
// the bytes the Python verifier produced for the same tree.
//
// Every message this package emits is a diagnostic somebody reads out of a
// failed deploy, so the summary line, the per-check blocks, the indentation
// and the wording are all part of the port rather than incidental formatting.
func TestTheReportIsByteIdenticalToThePython(t *testing.T) {
	root := newAssembly(t)
	if report := verifyTree(t, root); !report.OK() {
		t.Fatalf("the clean tree did not verify:\n%s", report.ErrorText())
	}
	breakEverything(t, root)

	recorded, err := os.ReadFile(
		filepath.Join("testdata", "failing-tree-report.txt"))
	if err != nil {
		t.Fatalf("read recording: %v", err)
	}
	got := verifyTree(t, root).ErrorText() + "\n"
	if got != string(recorded) {
		t.Fatalf("report differs from the Python's:\n--- got ---\n%s\n--- want ---\n%s",
			got, recorded)
	}
}

// TestTheBrokenTreeExercisesEveryCheckThatCanFailOffline names which checks
// the recording covers, so a check dropping out of it is visible rather than
// silently unmeasured.
//
// The two checks absent are cross-project-links, whose finding needs a
// published target the manifests disagree about, and outbound-links, which is
// not configured on this tree.
func TestTheBrokenTreeExercisesEveryCheckThatCanFailOffline(t *testing.T) {
	root := newAssembly(t)
	breakEverything(t, root)
	failed := checksThatFailed(verifyTree(t, root))

	for _, check := range Checks {
		switch check {
		case "home-project", "manifest-posts-emitted", "feed-links",
			"cross-project-links", "outbound-links":
			continue
		}
		if !failed[check] {
			t.Errorf("%s reported nothing on the broken tree", check)
		}
	}
}

// TestTheRecordingNamesTheSiteLevelBlogSegment guards the one constant the
// recording's wording depends on: a post's address segment. A rename would
// change every post path in the report without changing a line of this
// package.
func TestTheRecordingNamesTheSiteLevelBlogSegment(t *testing.T) {
	recorded, err := os.ReadFile(
		filepath.Join("testdata", "failing-tree-report.txt"))
	if err != nil {
		t.Fatalf("read recording: %v", err)
	}
	if !strings.Contains(string(recorded), "site/"+shared.PostsSegment+"/hello/") {
		t.Fatalf("the recording does not address a post under %q",
			shared.PostsSegment)
	}
}
