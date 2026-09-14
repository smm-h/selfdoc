package build

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/smm-h/selfdoc/internal/config"
	"github.com/smm-h/selfdoc/internal/effects"
	"github.com/smm-h/selfdoc/internal/resolution"
	"github.com/smm-h/selfdoc/internal/testproject"
	"github.com/smm-h/stricttest/go/hygiene"
)

// threeSiblings is the roster an assembled build is handed, out of name order
// so the rendering's own ordering is what the assertions read.
func threeSiblings() []SiblingProject {
	return []SiblingProject{
		{Slug: "gamma", Name: "Gamma", Description: "Does the gamma thing."},
		{Slug: "alpha", Name: "Alpha", Description: "Does the alpha thing."},
		{Slug: "beta", Name: "Beta", Description: ""},
	}
}

// buildWithSiblings builds the fixture project and returns its index page.
func buildWithSiblings(t *testing.T, siblings []SiblingProject) string {
	t.Helper()
	hygiene.Isolate(t)
	dir := testproject.Make(t, map[string]any{"docs": "docs/", "output": "docs/_build/"})
	cfg, err := config.Load(dir)
	if err != nil {
		t.Fatalf("loading the fixture config: %v", err)
	}
	empty := ""
	opts := NewSingleOptions()
	opts.DirPath = dir
	opts.Config = cfg
	opts.MountLocale = &empty
	opts.MountVersion = &empty
	opts.VersionOverride = &empty
	opts.WriteBaselines = false
	opts.Siblings = siblings
	result, err := BuildSingle(opts, effects.Unbound())
	if err != nil {
		t.Fatalf("BuildSingle: %v", err)
	}
	page, ok := result.HTMLFiles["index.html"]
	if !ok {
		t.Fatalf("the build wrote no index.html; keys: %v", sortedKeys(result.HTMLFiles))
	}
	return page
}

// TestAStandaloneBuildEmitsNoSiblingBlock: a project deployed on its own has
// no siblings, and nothing may invent them.
func TestAStandaloneBuildEmitsNoSiblingBlock(t *testing.T) {
	page := buildWithSiblings(t, nil)
	if strings.Contains(page, SiblingsHeading) {
		t.Errorf("a build handed no siblings emitted the block:\n%s", page)
	}
	if strings.Contains(page, "sibling-projects") {
		t.Errorf("a build handed no siblings emitted the section element")
	}
}

func TestTheSiblingBlockNamesEveryOtherProjectInNameOrder(t *testing.T) {
	page := buildWithSiblings(t, threeSiblings())
	if !strings.Contains(page, SiblingsHeading) {
		t.Fatalf("the built page carries no sibling block:\n%s", page)
	}
	positions := make([]int, 0, 3)
	for _, name := range []string{"Alpha", "Beta", "Gamma"} {
		at := strings.Index(page, ">"+name+"</a>")
		if at < 0 {
			t.Fatalf("the sibling block does not name %q", name)
		}
		positions = append(positions, at)
	}
	for i := 1; i < len(positions); i++ {
		if positions[i] < positions[i-1] {
			t.Errorf("the siblings are not in name order: %v", positions)
		}
	}
	if !strings.Contains(page, "Does the alpha thing.") {
		t.Error("the sibling block drops the one-line description")
	}
}

func TestTheSiblingBlockLinksDocumentRelatively(t *testing.T) {
	page := buildWithSiblings(t, threeSiblings())
	// The page is the project's own index, which the assembly serves at
	// "<slug>/index.html", so a sibling is one hop out and then in.
	if want := `href="../alpha/"`; !strings.Contains(page, want) {
		t.Errorf("the sibling block does not carry %s", want)
	}
	if strings.Contains(page, `href="/alpha/"`) {
		t.Error("the sibling block writes an origin-absolute link")
	}
}

func TestTheSiblingBlockSitsOutsideTheIndexedBodyAndBeforeTheFooter(t *testing.T) {
	page := buildWithSiblings(t, threeSiblings())
	block := strings.Index(page, SiblingsHeading)
	footer := strings.Index(page, `<footer class="site-footer">`)
	article := strings.Index(page, "</article>")
	if block < 0 || footer < 0 || article < 0 {
		t.Fatalf("block=%d footer=%d article=%d", block, footer, article)
	}
	if block > footer {
		t.Error("the sibling block is emitted after the footer")
	}
	if block < article {
		t.Error("the sibling block is inside the indexed body, so search " +
			"returns it once per page on the site")
	}
	if !strings.Contains(page, "data-pagefind-ignore") {
		t.Error("the sibling block is not declared ignorable to the indexer")
	}
}

// TestTheSiblingBlockPassesTheResolutionRule: the block's links climb out of
// the project's output root, which is the assembled site the project is one
// subtree of. That is what the mounted form of the rule allows, and none of
// them may be absolute against the site's base.
func TestTheSiblingBlockPassesTheResolutionRule(t *testing.T) {
	hygiene.Isolate(t)
	dir := testproject.Make(t, map[string]any{
		"docs":     "docs/",
		"output":   "docs/_build/",
		"base_url": "https://docs.example.com/selfdoc",
	})
	cfg, err := config.Load(dir)
	if err != nil {
		t.Fatalf("loading the fixture config: %v", err)
	}
	empty := ""
	opts := NewSingleOptions()
	opts.DirPath = dir
	opts.Config = cfg
	opts.MountLocale = &empty
	opts.MountVersion = &empty
	opts.VersionOverride = &empty
	opts.WriteBaselines = false
	opts.Siblings = threeSiblings()
	result, err := BuildSingle(opts, effects.Unbound())
	if err != nil {
		t.Fatalf("BuildSingle: %v", err)
	}

	outputDir := t.TempDir()
	for key, pageHTML := range result.HTMLFiles {
		path := filepath.Join(outputDir, filepath.FromSlash(key))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatalf("making %s: %v", filepath.Dir(path), err)
		}
		if err := os.WriteFile(path, []byte(pageHTML), 0o644); err != nil {
			t.Fatalf("writing %s: %v", path, err)
		}
	}

	diagnostics, err := resolution.CheckOutputResolution(
		outputDir, "https://docs.example.com/selfdoc", "selfdoc/", nil,
	)
	if err != nil {
		t.Fatalf("CheckOutputResolution: %v", err)
	}
	for _, lint := range diagnostics {
		for _, slug := range []string{"alpha", "beta", "gamma"} {
			if strings.Contains(lint.Message(), slug+"/") {
				t.Errorf("the sibling block fails the resolution rule: %s %s",
					lint.File(), lint.Message())
			}
		}
	}
}

func TestTheSiblingBlockHopsFromThePagesOwnDepth(t *testing.T) {
	for _, test := range []struct{ outputKey, want string }{
		{"index.html", "../"},
		{"guide/index.html", "../../"},
		{"guide/deep/index.html", "../../../"},
		// A post is grafted out of the project's subtree to the site root,
		// so it reaches the site root from its own depth alone.
		{"blog/hello/index.html", "../../"},
	} {
		if got := siteRootHop(test.outputKey); got != test.want {
			t.Errorf("siteRootHop(%q) = %q, want %q", test.outputKey, got, test.want)
		}
	}
}

func TestSiblingsFromManifestsDropsTheHomeProjectAndTheProjectItself(t *testing.T) {
	manifests := []map[string]any{
		{"slug": "home", "name": "Home", "description": "The front page."},
		{"slug": "alpha", "name": "Alpha", "description": "Does the alpha thing."},
		{"slug": "beta", "name": "Beta", "description": "Does the beta thing."},
		{"name": "Nameless", "description": "No slug, no address."},
	}
	got := SiblingsFromManifests(manifests, "home", "alpha")
	if len(got) != 1 || got[0].Slug != "beta" {
		t.Fatalf("SiblingsFromManifests = %+v, want just beta", got)
	}
	if got[0].Description != "Does the beta thing." {
		t.Errorf("the sibling carries %q, want the manifest's description",
			got[0].Description)
	}
	// The home project's own build lists every other project: it is both the
	// home slug and the project the pages belong to.
	home := SiblingsFromManifests(manifests, "home", "home")
	if len(home) != 2 {
		t.Errorf("the home project's siblings = %+v, want alpha and beta", home)
	}
}
