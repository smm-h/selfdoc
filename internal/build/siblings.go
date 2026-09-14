package build

import (
	"sort"
	"strings"

	"github.com/smm-h/selfdoc/internal/address"
	"github.com/smm-h/selfdoc/internal/html"
	"github.com/smm-h/selfdoc/internal/util"
)

// SiblingsHeading heads the section every assembled page carries at the end of
// its body.
const SiblingsHeading = "More tools from this site"

// SiblingProject is one other project published on the same assembled site.
//
// It is what one line of the sibling block needs and nothing more: where the
// project is served, what it is called, and the one-line description its
// manifest carries.
type SiblingProject struct {
	// Slug is the site segment the project is served under.
	Slug string
	// Name is the project's display name.
	Name string
	// Description is the project's one-line description, "" when its
	// manifest states none.
	Description string
}

// footerOpen is the element the sibling block is written in front of. It is
// the last thing in the page's main column, so the block ends the body.
const footerOpen = "<footer class=\"site-footer\">"

// renderSiblings is the sibling section, or "" when there is nothing to list.
//
// siteHop is the rendering page's hop back to the site root, so every link is
// document-relative: the assembled site has to resolve under a preview and a
// mirror as well as under the deployed base, and the resolution rule refuses
// a link a reader clicks that is absolute against the site's own base.
//
// The section is marked data-pagefind-ignore. It already sits outside the
// element the indexer reads a page's body from, so nothing indexes it today;
// the attribute says so where a reader of the markup can see it, and keeps it
// true if the block ever moves.
func renderSiblings(siblings []SiblingProject, siteHop string) string {
	listed := make([]SiblingProject, 0, len(siblings))
	for _, sibling := range siblings {
		if sibling.Slug == "" {
			continue
		}
		listed = append(listed, sibling)
	}
	if len(listed) == 0 {
		return ""
	}
	sort.SliceStable(listed, func(i, j int) bool {
		return strings.ToLower(listed[i].Name) < strings.ToLower(listed[j].Name)
	})

	parts := []string{
		`<section class="sibling-projects" data-pagefind-ignore aria-labelledby="sibling-projects-heading">`,
		`<h2 id="sibling-projects-heading">` + SiblingsHeading + "</h2>",
		"<ul>",
	}
	for _, sibling := range listed {
		name := sibling.Name
		if name == "" {
			name = sibling.Slug
		}
		line := `<li><a href="` + html.EscapeHTML(siteHop+sibling.Slug+"/") + `">` +
			html.EscapeHTML(name) + "</a>"
		if sibling.Description != "" {
			line += " <span>" + html.EscapeHTML(sibling.Description) + "</span>"
		}
		parts = append(parts, line+"</li>")
	}
	parts = append(parts, "</ul>", "</section>")
	return strings.Join(parts, "\n")
}

// siteRootHop is the hop from a built page back to the root of the assembled
// site it ends up on.
//
// A project's pages are grafted under its own slug, so a page reaches the site
// root by climbing its own depth and then one more level for the slug
// directory. A post is not: the graft lifts it out of the project's subtree to
// the site root at "blog/<slug>/", so its own depth is the whole hop.
func siteRootHop(outputKey string) string {
	depth := strings.Count(outputKey, "/")
	if !address.IsSiteLevel(outputKey) {
		depth++
	}
	return strings.Repeat("../", depth)
}

// withSiblings is pageHTML with the sibling block written in front of the page
// footer, or pageHTML unchanged when there is nothing to write.
//
// A page with no footer element is left alone: the wrapper writes one on every
// page it builds, and a fragment that has none is not a page this block
// belongs at the end of.
func withSiblings(pageHTML, outputKey string, siblings []SiblingProject) string {
	block := renderSiblings(siblings, siteRootHop(outputKey))
	if block == "" {
		return pageHTML
	}
	at := strings.Index(pageHTML, footerOpen)
	if at < 0 {
		return pageHTML
	}
	return pageHTML[:at] + block + "\n" + pageHTML[at:]
}

// SiblingsFromManifests is the sibling list for one project, read off the
// assembly's manifests.
//
// Two projects are left out: the one the pages belong to, which does not link
// itself, and the home project, which is the site root every page already
// reaches rather than one of the tools the site publishes. A manifest with no
// slug names no address and is skipped.
func SiblingsFromManifests(
	manifests []map[string]any, homeSlug, selfSlug string,
) []SiblingProject {
	siblings := make([]SiblingProject, 0, len(manifests))
	for _, manifest := range manifests {
		slug := util.PythonStrOrEmpty(manifest["slug"])
		if slug == "" || slug == selfSlug || (homeSlug != "" && slug == homeSlug) {
			continue
		}
		siblings = append(siblings, SiblingProject{
			Slug:        slug,
			Name:        util.PythonStrOrEmpty(manifest["name"]),
			Description: util.PythonStrOrEmpty(manifest["description"]),
		})
	}
	return siblings
}
