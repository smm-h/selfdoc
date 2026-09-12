package sitedirectives

import (
	"os"
	"path/filepath"
	"strings"

	"github.com/smm-h/selfdoc/internal/blog/listing"
	"github.com/smm-h/selfdoc/internal/blog/site"
	"github.com/smm-h/selfdoc/internal/build"
	"github.com/smm-h/selfdoc/internal/config"
	"github.com/smm-h/selfdoc/internal/effects"
	"github.com/smm-h/selfdoc/internal/util"
)

// HomeListingPath returns where the home project declares its curated
// listing.
func HomeListingPath(dirPath string, cfg map[string]any) string {
	docsDir := util.PythonStrOrEmpty(cfg["docs"])
	if docsDir == "" {
		docsDir = "docs/"
	}
	return filepath.Join(dirPath, strings.TrimRight(docsDir, "/"), "projects.toml")
}

// BuildHomeProject builds the home project with the assembly's data in scope.
//
// This is the only build that can resolve a site-level directive, and the
// refusals below are why: the manifests are what a version badge and a post
// highlight are read from, and no project's own repository holds them. A
// missing context stops the build before a page is written -- there is no
// rendering of an empty region and no placeholder.
//
// Directive resolution happens per markdown source and never learns which
// emitted page it is writing into, so the regions come out of the build
// addressed from the output root. [RefreshOutputRegions] then re-renders each
// one against its own page's hop -- the same pass the assembly runs on every
// deploy, run here so the home project's own build output is correct on its
// own.
//
// The project's selfdoc.json is loaded here rather than taken as an argument:
// the config this build runs on is not the document on disk, since the
// site-level directives are registered into it, and the one place that
// registration belongs is here.
func BuildHomeProject(
	dirPath string,
	siteManifests string,
	theme string,
	includeDrafts bool,
	h *effects.Handle,
) (map[string]bool, error) {
	if siteManifests == "" {
		return nil, errorf(
			"--site-manifests is required by --target home: the home "+
				"project's pages carry site-level directives (%s) that render "+
				"from the assembly's manifests, and this repository holds "+
				"none of them. Point it at the assembly checkout's "+
				"manifests/ directory.",
			strings.Join(SiteDirectives, ", "),
		)
	}
	if info, err := os.Stat(siteManifests); err != nil || !info.IsDir() {
		return nil, errorf(
			"--site-manifests names %s, which is not a directory. It is the "+
				"assembly checkout's manifests/ directory.",
			util.PythonRepr(siteManifests),
		)
	}

	cfg, err := config.Load(dirPath)
	if err != nil {
		return nil, err
	}

	var curated *listing.Listing
	listingPath := HomeListingPath(dirPath, cfg)
	if info, err := os.Stat(listingPath); err == nil && info.Mode().IsRegular() {
		loaded, err := listing.Load(listingPath)
		if err != nil {
			return nil, err
		}
		curated = &loaded
	}

	manifests, err := site.LoadAssemblyManifests(siteManifests)
	if err != nil {
		return nil, err
	}
	context := SiteContext{
		Manifests: manifests,
		Listing:   curated,
		HomeSlug:  util.PythonStrOrEmpty(topology(cfg)["slug"]),
	}

	buildConfig := make(map[string]any, len(cfg)+1)
	for key, value := range cfg {
		buildConfig[key] = value
	}
	declared := map[string]any{}
	if own, isObject := cfg["directives"].(map[string]any); isObject {
		for name, script := range own {
			declared[name] = script
		}
	}
	for name, directive := range Directives(&context) {
		declared[name] = directive
	}
	buildConfig["directives"] = declared

	written, err := build.Build(build.Options{
		DirPath:       dirPath,
		Config:        buildConfig,
		IncludeDrafts: includeDrafts,
		Theme:         theme,
	}, h)
	if err != nil {
		return nil, err
	}

	outputDir := util.PythonStrOrEmpty(cfg["output"])
	if outputDir == "" {
		outputDir = "docs/_build/"
	}
	if _, err := RefreshOutputRegions(
		filepath.Join(dirPath, strings.TrimRight(outputDir, "/")), context, h,
	); err != nil {
		return nil, err
	}
	return written, nil
}

// topology is the config's topology block, or an empty one when it declares
// none.
func topology(cfg map[string]any) map[string]any {
	if block, isObject := cfg["topology"].(map[string]any); isObject {
		return block
	}
	return map[string]any{}
}
