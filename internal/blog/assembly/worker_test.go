package assembly

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const (
	workerCanonicalBase = "https://docs.example.com"
	workerLegacyHost    = "blog.example.com"
)

// workerProjectSlugs and workerPostSlugs are the address space every routing
// assertion is made against.
var (
	workerProjectSlugs = []string{"alpha", "beta"}
	workerPostSlugs    = []string{"hello", "world"}
)

// workerDriver imports the generated module and prints what it routes each
// input to, so the assertion is made against the real artifact rather than
// against a second implementation of the routing.
const workerDriver = `import { routeRequest } from "./worker.mjs";
const inputs = JSON.parse(process.argv[2]);
console.log(JSON.stringify(inputs.map((url) => routeRequest(url))));
`

// workerJS renders the worker every assertion reads.
func workerJS(t *testing.T) string {
	t.Helper()
	js, err := GenerateWorkerJS(
		workerCanonicalBase, workerLegacyHost, workerProjectSlugs, workerPostSlugs,
	)
	if err != nil {
		t.Fatalf("generating the worker: %v", err)
	}
	return js
}

// requireNode skips when node is absent. node is what the worker runtime is,
// so a machine without it cannot make this assertion at all; saying so beats
// passing.
func requireNode(t *testing.T) {
	t.Helper()
	if _, err := exec.LookPath("node"); err != nil {
		t.Skip("node is the worker's runtime; without it the generated " +
			"module cannot be executed and its routing cannot be asserted.")
	}
}

// route returns what the generated worker routes each URL to, with a nil
// element standing for "serve this".
func route(t *testing.T, js string, urls []string) []*string {
	t.Helper()
	requireNode(t)
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "worker.mjs"), []byte(js), 0o644); err != nil {
		t.Fatalf("writing the worker: %v", err)
	}
	if err := os.WriteFile(filepath.Join(dir, "driver.mjs"), []byte(workerDriver), 0o644); err != nil {
		t.Fatalf("writing the driver: %v", err)
	}
	encoded, err := json.Marshal(urls)
	if err != nil {
		t.Fatalf("encoding the inputs: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, "node", "driver.mjs", string(encoded))
	command.Dir = dir
	output, err := command.Output()
	if err != nil {
		stderr := ""
		if exitErr, ok := err.(*exec.ExitError); ok {
			stderr = string(exitErr.Stderr)
		}
		t.Fatalf("running the worker under node: %v\n%s", err, stderr)
	}
	var routed []*string
	if err := json.Unmarshal(output, &routed); err != nil {
		t.Fatalf("decoding the worker's answers: %v (%s)", err, output)
	}
	return routed
}

// routes asserts a whole input-to-output table in one node run. A want of ""
// means "serve this".
func routes(t *testing.T, js string, table [][2]string) {
	t.Helper()
	urls := make([]string, len(table))
	for index, pair := range table {
		urls[index] = pair[0]
	}
	routed := route(t, js, urls)
	for index, pair := range table {
		got := "null"
		if routed[index] != nil {
			got = *routed[index]
		}
		want := pair[1]
		if want == "" {
			want = "null"
		}
		if got != want {
			t.Errorf("%s -> %s, want %s", pair[0], got, want)
		}
	}
}

// -- one hostname ------------------------------------------------------------

func TestWorkerServesTheCanonicalHost(t *testing.T) {
	// Nothing on the canonical host is redirected just for being there.
	routes(t, workerJS(t), [][2]string{
		{workerCanonicalBase + "/", ""},
		{workerCanonicalBase + "/alpha/guide/", ""},
		{workerCanonicalBase + "/blog/hello/", ""},
		{workerCanonicalBase + "/alpha/?q=x", ""},
	})
}

func TestWorkerSendsEveryOtherHostToTheSamePath(t *testing.T) {
	routes(t, workerJS(t), [][2]string{
		{"https://other.example.com/alpha/guide/", workerCanonicalBase + "/alpha/guide/"},
		{"https://smmh-preview.pages.dev/projects/", workerCanonicalBase + "/projects/"},
		{"https://other.example.com/", workerCanonicalBase + "/"},
		{"https://other.example.com/alpha/?tab=api&page=2",
			workerCanonicalBase + "/alpha/?tab=api&page=2"},
	})
}

func TestWorkerKeepsTheRetiredBlogSubdomainsPrefix(t *testing.T) {
	// The blog subdomain's whole space was the blog, so it maps under it.
	// Mapping it to the same path would send every live post link to the site
	// root, where nothing answers.
	routes(t, workerJS(t), [][2]string{
		{"https://blog.example.com/hello/", workerCanonicalBase + "/blog/hello/"},
		{"https://blog.example.com/", workerCanonicalBase + "/blog/"},
		{"https://blog.example.com/hello/?utm=x", workerCanonicalBase + "/blog/hello/?utm=x"},
	})
}

func TestWorkerWithoutALegacyBlogHostPrefixesNothing(t *testing.T) {
	js, err := GenerateWorkerJS(
		workerCanonicalBase, "", workerProjectSlugs, workerPostSlugs,
	)
	if err != nil {
		t.Fatalf("generating the worker: %v", err)
	}
	if !strings.Contains(js, "HOST_PREFIXES = new Map([])") {
		t.Error("a worker with no legacy host still declares a prefix")
	}
	if !strings.Contains(workerJS(t), workerLegacyHost) {
		t.Error("a worker with a legacy host does not declare it")
	}
	routes(t, js, [][2]string{
		{"https://blog.example.com/hello/", workerCanonicalBase + "/hello/"},
	})
}

// -- the retired locale and version scheme -----------------------------------

func TestWorkerCollapsesLocaleVersionPaths(t *testing.T) {
	routes(t, workerJS(t), [][2]string{
		{workerCanonicalBase + "/alpha/en/1.0.0/guide/", workerCanonicalBase + "/alpha/guide/"},
		{workerCanonicalBase + "/alpha/en/0.2.3/api/reference/",
			workerCanonicalBase + "/alpha/api/reference/"},
		{workerCanonicalBase + "/alpha/en/1.0.0/", workerCanonicalBase + "/alpha/"},
		{workerCanonicalBase + "/alpha/en/1.0.0", workerCanonicalBase + "/alpha/"},
	})
}

func TestWorkerCollapsesAnyVersionSegment(t *testing.T) {
	// Version-agnostic on purpose: an old deep link wants the page now.
	// Archived versions are still served at "/<slug>/v/<version>/"; what this
	// rule answers is a link to a version that was current when it was copied.
	routes(t, workerJS(t), [][2]string{
		{workerCanonicalBase + "/alpha/en/0.1/guide/", workerCanonicalBase + "/alpha/guide/"},
		{workerCanonicalBase + "/alpha/en/v2.0.0/guide/", workerCanonicalBase + "/alpha/guide/"},
		{workerCanonicalBase + "/alpha/en/1.0.0-rc.1/guide/", workerCanonicalBase + "/alpha/guide/"},
		{workerCanonicalBase + "/alpha/en/9.9.9/guide/", workerCanonicalBase + "/alpha/guide/"},
	})
}

func TestWorkerRecognisesAnyLocaleSegment(t *testing.T) {
	routes(t, workerJS(t), [][2]string{
		{workerCanonicalBase + "/alpha/fr/1.0.0/guide/", workerCanonicalBase + "/alpha/guide/"},
		{workerCanonicalBase + "/alpha/pt-br/1.0.0/guide/", workerCanonicalBase + "/alpha/guide/"},
	})
}

func TestWorkerServesTheArchiveAddress(t *testing.T) {
	// "/v/<version>/" is the current scheme for a superseded version.
	routes(t, workerJS(t), [][2]string{
		{workerCanonicalBase + "/alpha/v/1.0.0/guide/", ""},
		{workerCanonicalBase + "/alpha/v/1.0.0/", ""},
	})
}

// -- the retired post addresses ----------------------------------------------

func TestWorkerMovesProjectScopedPostAddressesToTheBlog(t *testing.T) {
	routes(t, workerJS(t), [][2]string{
		{workerCanonicalBase + "/alpha/posts/hello/", workerCanonicalBase + "/blog/hello/"},
		{workerCanonicalBase + "/alpha/posts/hello", workerCanonicalBase + "/blog/hello/"},
		{workerCanonicalBase + "/beta/posts/world/", workerCanonicalBase + "/blog/world/"},
		{workerCanonicalBase + "/alpha/posts/hello/?ref=x",
			workerCanonicalBase + "/blog/hello/?ref=x"},
	})
}

// -- unknown addresses fall through ------------------------------------------

func TestWorkerLeavesUnknownAddressesToThe404(t *testing.T) {
	// Historical-looking is not historical.
	routes(t, workerJS(t), [][2]string{
		{workerCanonicalBase + "/nosuch/en/1.0.0/guide/", ""},
		{workerCanonicalBase + "/nosuch/posts/hello/", ""},
		{workerCanonicalBase + "/alpha/posts/nosuch/", ""},
		{workerCanonicalBase + "/alpha/en/guide/page/", ""},
	})
}

func TestWorkerServesTheFlatScheme(t *testing.T) {
	// The old flat sitemap addresses are what the site serves today.
	routes(t, workerJS(t), [][2]string{
		{workerCanonicalBase + "/alpha/", ""},
		{workerCanonicalBase + "/alpha/guide/", ""},
		{workerCanonicalBase + "/blog/hello/", ""},
	})
}

// -- one hop, never two ------------------------------------------------------

func TestWorkerResolvesAForeignHostAndAHistoricalPathInOneHop(t *testing.T) {
	routes(t, workerJS(t), [][2]string{
		{"https://other.example.com/alpha/en/1.0.0/guide/",
			workerCanonicalBase + "/alpha/guide/"},
		{"https://other.example.com/alpha/posts/hello/",
			workerCanonicalBase + "/blog/hello/"},
	})
}

func TestWorkerResolvesANestedHistoricalPathInOneHop(t *testing.T) {
	// A path whose target is itself historical still answers in one 301.
	// Applying the mapping once would emit a redirect to an address that
	// redirects again.
	routes(t, workerJS(t), [][2]string{
		{workerCanonicalBase + "/alpha/en/1.0/en/1.0/deep/",
			workerCanonicalBase + "/alpha/deep/"},
		{workerCanonicalBase + "/alpha/en/1.0/en/2.0/en/3.0/deep/",
			workerCanonicalBase + "/alpha/deep/"},
		// The last pass lands on a post address, which is a second shape.
		{workerCanonicalBase + "/alpha/en/1.0/posts/hello/",
			workerCanonicalBase + "/blog/hello/"},
	})
}

func TestWorkerTerminatesOnADeeplyNestedHostilePath(t *testing.T) {
	nested := strings.Repeat("en/1.0/", 60)
	routes(t, workerJS(t), [][2]string{
		{workerCanonicalBase + "/alpha/" + nested + "deep/",
			workerCanonicalBase + "/alpha/deep/"},
	})
}

func TestWorkerRoutesNoOutputOfItsOwnAgain(t *testing.T) {
	// Every redirect target is a final address: routing it returns null.
	js := workerJS(t)
	sources := []string{
		"https://other.example.com/alpha/guide/",
		"https://blog.example.com/hello/",
		workerCanonicalBase + "/alpha/en/1.0.0/guide/",
		workerCanonicalBase + "/alpha/posts/hello/",
		workerCanonicalBase + "/alpha/en/1.0/en/1.0/deep/",
		workerCanonicalBase + "/alpha/en/1.0/posts/hello/",
		"https://blog.example.com/../alpha/en/1.0/en/1.0/x/",
		workerCanonicalBase + "/alpha/" + strings.Repeat("en/1.0/", 40) + "deep/",
	}
	targets := route(t, js, sources)
	final := make([]string, len(targets))
	for index, target := range targets {
		if target == nil {
			t.Fatalf("%s was not redirected at all", sources[index])
		}
		final[index] = *target
	}
	for index, answer := range route(t, js, final) {
		if answer != nil {
			t.Errorf("%s redirects again, to %s", final[index], *answer)
		}
	}
}

// -- structure ---------------------------------------------------------------

func TestWorkerEmbedsTheAddressSpaceAsData(t *testing.T) {
	js := workerJS(t)
	for _, want := range []string{
		`const PROJECT_SLUGS = new Set(["alpha", "beta"])`,
		`const POST_SLUGS = new Set(["hello", "world"])`,
		`["` + workerLegacyHost + `", "/blog"]`,
		"export function routeRequest(",
		"export function legacyTarget(",
		"Response.redirect(target, 301)",
		"env.ASSETS.fetch(request)",
	} {
		if !strings.Contains(js, want) {
			t.Errorf("the worker does not carry %q", want)
		}
	}
}

func TestWorkerSlugsAreSortedAndDeduplicated(t *testing.T) {
	// The generated file is stable input to input, so deploys do not churn.
	js, err := GenerateWorkerJS(
		workerCanonicalBase, workerLegacyHost,
		[]string{"beta", "alpha", "beta"},
		[]string{"world", "hello", "world"},
	)
	if err != nil {
		t.Fatalf("generating the worker: %v", err)
	}
	for _, want := range []string{
		`new Set(["alpha", "beta"])`, `new Set(["hello", "world"])`,
	} {
		if !strings.Contains(js, want) {
			t.Errorf("the worker does not carry %q", want)
		}
	}
}

func TestWorkerSizeTracksProjectsAndPostsNotPages(t *testing.T) {
	// The map is patterns plus two sets, never one entry per page.
	var slugs, posts []string
	for index := range 100 {
		slugs = append(slugs, fmt.Sprintf("project-%03d", index))
	}
	for index := range 200 {
		posts = append(posts, fmt.Sprintf("post-%03d", index))
	}
	js, err := GenerateWorkerJS(workerCanonicalBase, workerLegacyHost, slugs, posts)
	if err != nil {
		t.Fatalf("generating the worker: %v", err)
	}
	// Three hundred names at about fourteen bytes each, plus a fixed body of
	// routing.
	if len(js) >= 12000 {
		t.Errorf("the worker is %d bytes; it grows with something other than names", len(js))
	}
	if strings.Contains(js, "/guide/") {
		t.Error("the worker names an individual page")
	}
}

func TestWorkerRefusesWithoutACanonicalBase(t *testing.T) {
	if _, err := GenerateWorkerJS("", workerLegacyHost, nil, nil); err == nil {
		t.Fatal("a worker was generated with no canonical base")
	}
}

func TestWorkerTrimsATrailingSlashFromTheCanonicalBase(t *testing.T) {
	js, err := GenerateWorkerJS(workerCanonicalBase+"/", "", nil, nil)
	if err != nil {
		t.Fatalf("generating the worker: %v", err)
	}
	want := `const CANONICAL_BASE = "` + workerCanonicalBase + `";`
	if !strings.Contains(js, want) {
		t.Fatalf("the worker does not declare %q", want)
	}
}
