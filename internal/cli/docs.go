package cli

import (
	"os"
	"path/filepath"
	"strings"

	"github.com/smm-h/selfdoc/internal/blog/assembly"
	"github.com/smm-h/selfdoc/internal/effects"
	"github.com/smm-h/selfdoc/internal/util"
	"github.com/smm-h/strictcli/go/strictcli"
)

func (c *cli) registerDocs() {
	group := c.app.Group("docs", "Publish this project's documentation to the unified assembly without a release")

	group.Command("publish",
		"Publish this project's documentation to the assembly without a release. Builds the docs locally, pushes the built site, its manifest and its membership record into the assembly repo via the Git Data API -- deleting the pages this project published before and no longer produces -- then dispatches a shared-only workflow to regenerate cross-project elements.",
		c.cmdDocsPublish,
		strictcli.WithEffect(strictcli.EffectMutating),
		// Consequential for the same reason `post publish` is:
		// locally-authored content becomes publicly readable at the moment
		// this runs, with no tag and no release standing between the working
		// tree and the live site. It also deletes: a page this project
		// published before and no longer builds disappears for readers in the
		// same commit.
		strictcli.WithConsequential(),
		strictcli.WithGrants(assemblyDispatchGrant),
	)
}

func (c *cli) cmdDocsPublish(ctx *strictcli.Context, kwargs map[string]any) strictcli.Outcome {
	handle := effects.FromContext(ctx)
	dir := c.dir()

	cfg, outcome, ok := c.requireConfig()
	if !ok {
		return outcome
	}

	repo := configString(cfg, "assembly", "repo")
	if repo == "" {
		return c.failf("Error: assembly.repo not configured in selfdoc.json.")
	}
	slug := configString(cfg, "topology", "slug")
	if slug == "" {
		return c.failf("Error: topology.slug not configured in selfdoc.json.")
	}

	version, _ := cfg["version"].(string)
	if version == "" {
		version = util.DetectProjectVersion(dir, "0.0.0")
	}

	// The same build the deploy runs on a cloned checkout, run here on the
	// working tree.
	if err := assembly.BuildSourceProject(assembly.BuildOptions{
		SourceDir: dir,
		Scope:     "full",
	}, handle); err != nil {
		return c.fail(err)
	}

	outputRel := strings.TrimRight(outputDirOf(cfg), "/")
	outputDir := filepath.Join(dir, outputRel)
	if info, err := os.Stat(outputDir); err != nil || !info.IsDir() {
		return c.failf("Error: the build produced no output at %s; there is "+
			"nothing to publish.", outputDir)
	}

	summary, err := assembly.PublishProjectDocs(assembly.PublishOptions{
		Repo:         repo,
		Slug:         slug,
		OutputDir:    outputDir,
		Version:      version,
		ManifestPath: filepath.Join(dir, ".selfdoc", "manifest.json"),
	}, handle)
	if err != nil {
		return c.fail(err)
	}

	// Dispatch a shared-only rebuild so the listing, feed, sitemap and search
	// index take account of what just changed.
	if outcome, ok := c.dispatchSharedRebuild(handle, repo); !ok {
		return outcome
	}

	removal := ""
	if len(summary.Deleted) > 0 {
		removal = ", removing " + itoa(len(summary.Deleted)) + " page(s) it no longer builds"
	}
	c.printf("Published %d documentation file(s) for %s to %s%s. Shared elements will regenerate.\n",
		len(summary.Published), slug, repo, removal)
	return strictcli.Exit(0)
}
