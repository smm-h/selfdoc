// Package resolution answers whether every reference a build emitted resolves
// to a file it wrote.
//
// The build derives every address from the address package, and the test suite
// walks a built tree asserting that each emitted reference lands on an emitted
// file. This package is that assertion as a user-facing check: one lint code,
// LINK001, over the output directory.
//
// Five kinds of reference are covered, which is every kind the build emits:
//
//   - document-relative href/src attributes in the pages themselves,
//   - the absolute rel="canonical" link on each page,
//   - the absolute data-share-url addresses the share control offers,
//   - the <loc> entries of every sitemap,
//   - the entry links of the Atom feed.
//
// The last four are absolute URLs, so they are checked against the site's
// configured base: an absolute URL that points into this site must name a page
// this build wrote, and one that points elsewhere is not ours to verify. A
// share address is a reference like any other -- it is handed to a reader to
// open -- so a control that offers an address the build did not write fails
// here rather than 404ing for whoever it was shared with.
//
// # Two rules that are not about existence
//
// A reference that decides where a CLICK goes -- an <a href> -- must be
// document-relative, so neither of these is allowed:
//
//   - /blog/hello/, origin-absolute, which resolves only when the site is
//     served from an origin root and names nothing under a mount;
//   - https://<this site's base>/blog/hello/, absolute against the site's own
//     base, which is worse because it WORKS: on a preview, a mirror or any
//     other mount the click silently leaves the tree the reader is looking at
//     and lands on production. The file-existence half of this package can
//     never see it -- the page it names really is there.
//
// Absolute is right for metadata, which says where a page lives in the world:
// the canonical, the share addresses, sitemap entries and feed links, all
// checked above and none of them somewhere a click goes.
package resolution

import (
	"html"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"github.com/smm-h/selfdoc/internal/address"
	"github.com/smm-h/selfdoc/internal/lints"
)

// LintCode is the lint code every unresolvable reference is reported under.
const LintCode = "LINK001"

var (
	refAttrRE = regexp.MustCompile(`\b(href|src|data-search-base)="([^"]*)"`)
	// anchorHrefRE matches every <a> element's href -- the references a
	// reader can click, as opposed to the assets a page loads and the
	// metadata it declares.
	anchorHrefRE = regexp.MustCompile(`(?i)<a\b[^>]*?\bhref="([^"]*)"`)
	canonicalRE  = regexp.MustCompile(`<link rel="canonical" href="([^"]*)"`)
	shareURLRE   = regexp.MustCompile(`\bdata-share-url="([^"]*)"`)
	locRE        = regexp.MustCompile(`<loc>([^<]*)</loc>`)
	feedLinkRE   = regexp.MustCompile(`<link href="([^"]*)"`)
	// linkElementRE matches every <link> element, so the outbound
	// collector can read its rel.
	linkElementRE = regexp.MustCompile(`(?i)<link\b[^>]*>`)
	relAttrRE     = regexp.MustCompile(`(?i)\brel="([^"]*)"`)
)

// skipSchemes are the reference prefixes that address something other than a
// file in this output tree.
var skipSchemes = []string{
	"http://", "https://", "//", "mailto:", "data:", "javascript:", "tel:",
}

// originOnlyRels are the link relations whose href is an ORIGIN to warm up
// rather than a document to fetch. A GET at https://fonts.googleapis.com
// answers 404 and is supposed to: nothing is served there, and nothing
// navigates there. The other resource hints -- preload, prefetch,
// modulepreload -- name a real file the browser really requests, so a dead one
// is a real defect and stays collected.
var originOnlyRels = map[string]bool{
	"preconnect": true, "dns-prefetch": true,
}

// Reference is one internal reference a page writes: the attribute that
// carried it and the reference itself, unescaped.
type Reference struct {
	// Attr is the attribute name -- href, src or data-search-base.
	Attr string
	// Ref is the reference as written, with HTML entities resolved.
	Ref string
}

// emittedFiles returns every file the build wrote, as posix paths relative to
// outputDir.
func emittedFiles(outputDir string) (map[string]bool, error) {
	emitted := map[string]bool{}
	err := filepath.WalkDir(outputDir, func(full string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			return nil
		}
		name := entry.Name()
		if strings.HasSuffix(name, ".gz") || strings.HasSuffix(name, ".br") {
			return nil
		}
		rel, relErr := filepath.Rel(outputDir, full)
		if relErr != nil {
			return relErr
		}
		emitted[filepath.ToSlash(rel)] = true
		return nil
	})
	if err != nil {
		return nil, err
	}
	return emitted, nil
}

// ReferenceTarget resolves ref, written on the page at pageRel, to an output
// path.
//
// The second result is false when the reference addresses nothing on its own:
// an empty value, or a bare fragment.
func ReferenceTarget(pageRel, ref string) (string, bool) {
	ref = strings.SplitN(ref, "#", 2)[0]
	ref = strings.SplitN(ref, "?", 2)[0]
	if ref == "" {
		return "", false
	}
	target := path.Join(path.Dir(pageRel), ref)
	if strings.HasSuffix(ref, "/") || target == "." {
		target = path.Join(target, "index.html")
	}
	return target, true
}

// SiteRelativePath is the output-relative path an absolute url names.
//
// The second result is false when the URL is not this site's -- an external
// link, or a URL with no base to measure it against.
func SiteRelativePath(url, baseURL string) (string, bool) {
	if baseURL == "" {
		return "", false
	}
	base := strings.TrimRight(baseURL, "/")
	if url == base {
		return "index.html", true
	}
	if !strings.HasPrefix(url, base+"/") {
		return "", false
	}
	rest := url[len(base)+1:]
	rest = strings.SplitN(rest, "#", 2)[0]
	rest = strings.SplitN(rest, "?", 2)[0]
	if rest == "" || strings.HasSuffix(rest, "/") {
		rest += "index.html"
	}
	return path.Clean(rest), true
}

// PageReferences returns every internal reference pageHTML writes.
//
// Internal means "addressed within this site": a fragment, an empty value and
// every off-site scheme are dropped, so what is left is either a
// document-relative reference or an origin-absolute one -- which is a defect
// this package reports, not a reference to follow.
func PageReferences(pageHTML string) []Reference {
	var refs []Reference
	for _, match := range refAttrRE.FindAllStringSubmatch(pageHTML, -1) {
		ref := html.UnescapeString(match[2])
		if ref == "" || strings.HasPrefix(ref, "#") || hasAnyPrefix(ref, skipSchemes) {
			continue
		}
		refs = append(refs, Reference{Attr: match[1], Ref: ref})
	}
	return refs
}

// NavigationReferences returns every <a href> pageHTML writes, unescaped.
//
// These are the references a click follows, which is the set the
// mount-relative rule governs. Assets (src, a stylesheet link) are not here:
// they are fetched by the page rather than navigated to, and the assembly
// re-points some of them at site-level files after the graft.
func NavigationReferences(pageHTML string) []string {
	var refs []string
	for _, match := range anchorHrefRE.FindAllStringSubmatch(pageHTML, -1) {
		if ref := html.UnescapeString(match[1]); ref != "" {
			refs = append(refs, ref)
		}
	}
	return refs
}

// blankOriginHints blanks every origin-only resource hint, keeping every other
// offset.
//
// Blanking the whole element rather than collecting its href into a skip set is
// what keeps the exemption per-element: a page that both preconnects to an
// origin and links to it still has the link collected.
func blankOriginHints(pageHTML string) string {
	return linkElementRE.ReplaceAllStringFunc(pageHTML, func(element string) string {
		rel := relAttrRE.FindStringSubmatch(element)
		if rel == nil {
			return element
		}
		for _, token := range strings.Fields(rel[1]) {
			if originOnlyRels[strings.ToLower(token)] {
				return strings.Repeat(" ", len(element))
			}
		}
		return element
	})
}

// ExternalReferences returns every absolute http(s) URL pageHTML references.
//
// This is the other half of PageReferences: what this package cannot verify
// against the emitted tree, because it names somebody else's server. Whether
// those still answer is the outbound check's question.
//
// Origin-only resource hints are not references in that sense and are dropped
// before the scan -- see originOnlyRels.
func ExternalReferences(pageHTML string) []string {
	var refs []string
	for _, match := range refAttrRE.FindAllStringSubmatch(blankOriginHints(pageHTML), -1) {
		ref := html.UnescapeString(match[2])
		if strings.HasPrefix(ref, "http://") || strings.HasPrefix(ref, "https://") {
			refs = append(refs, ref)
		}
	}
	return refs
}

// escapeDepth is how many levels above the output root target sits, 0 when it
// is inside.
func escapeDepth(target string) int {
	depth := 0
	for _, segment := range strings.Split(target, "/") {
		if segment != ".." {
			break
		}
		depth++
	}
	return depth
}

// hasAnyPrefix reports whether s starts with any of prefixes.
func hasAnyPrefix(s string, prefixes []string) bool {
	for _, prefix := range prefixes {
		if strings.HasPrefix(s, prefix) {
			return true
		}
	}
	return false
}

// CheckOutputResolution checks every emitted reference in outputDir against
// what the build wrote, returning one LintCode diagnostic per unresolvable
// reference.
//
// outputDir is the build output directory; a directory that holds no HTML is
// not a built site and yields no diagnostics. baseURL is the site's configured
// base URL, used to tell this site's absolute URLs (canonicals, sitemap
// entries, feed links) from everyone else's.
//
// mountPrefix is the path segments the site serves this output under
// ("alpha/"), empty when the output root is the served root. A mounted build's
// output is one subtree of a site it cannot see: its pages address the site
// level by climbing out of the output root, and its posts are grafted OUT of
// the subtree to the site root, so neither side's references resolve within
// this directory. Those are left to the assembly's own pass over the whole
// tree, which is the only place they can be answered. What still applies here
// applies everywhere: no reference a reader clicks may be origin-absolute or
// absolute against the site's base.
func CheckOutputResolution(outputDir, baseURL, mountPrefix string) ([]lints.LintResult, error) {
	info, err := os.Stat(outputDir)
	if err != nil || !info.IsDir() {
		return nil, nil
	}
	mountDepth := 0
	if mountPrefix != "" {
		mountDepth = strings.Count(strings.Trim(mountPrefix, "/"), "/") + 1
	}
	emitted, err := emittedFiles(outputDir)
	if err != nil {
		return nil, err
	}
	var pages []string
	for rel := range emitted {
		if strings.HasSuffix(rel, ".html") {
			pages = append(pages, rel)
		}
	}
	if len(pages) == 0 {
		return nil, nil
	}
	sort.Strings(pages)

	var results []lints.LintResult
	fail := func(where, message string) {
		results = append(results, lints.MustLintResult(where, nil, LintCode, message))
	}
	checkAbsolute := func(where, kind, url string) {
		target, ours := SiteRelativePath(url, baseURL)
		if !ours {
			return
		}
		if !emitted[target] {
			fail(where, kind+" "+url+" -> "+target+", which this build did not write")
		}
	}

	for _, pageRel := range pages {
		raw, err := os.ReadFile(filepath.Join(outputDir, filepath.FromSlash(pageRel)))
		if err != nil {
			return nil, err
		}
		pageHTML := string(raw)

		// A post in a mounted build is grafted out of this subtree to the
		// site root, so it addresses its neighbours from an address this
		// directory does not have. Nothing here can answer those; the
		// assembly's pass over the assembled tree does.
		siteLevelPage := mountDepth != 0 && address.IsSiteLevel(pageRel)

		for _, reference := range PageReferences(pageHTML) {
			if strings.HasPrefix(reference.Ref, "/") {
				fail(pageRel, reference.Attr+`="`+reference.Ref+`" is `+
					"origin-absolute; the site has to resolve under any "+
					"mount point, so links are document-relative")
				continue
			}
			if siteLevelPage {
				continue
			}
			target, addresses := ReferenceTarget(pageRel, reference.Ref)
			if !addresses {
				continue
			}
			switch {
			case strings.HasPrefix(target, ".."):
				// Climbing out of a mounted build's output root reaches
				// the site, which this directory is only one subtree of.
				if escapeDepth(target) > mountDepth {
					fail(pageRel, reference.Attr+`="`+reference.Ref+
						`" escapes the output root`)
				}
			case !emitted[target]:
				fail(pageRel, reference.Attr+`="`+reference.Ref+`" -> `+
					target+", which this build did not write")
			}
		}

		for _, ref := range NavigationReferences(pageHTML) {
			if _, ours := SiteRelativePath(ref, baseURL); !ours {
				continue
			}
			fail(pageRel, `<a href="`+ref+`"> is absolute against the site's `+
				"own base; the site has to resolve under any mount point, so "+
				"a link a reader clicks is document-relative. An absolute one "+
				"works on the deployed host and silently leaves a preview or "+
				"a mirror")
		}

		for _, match := range canonicalRE.FindAllStringSubmatch(pageHTML, -1) {
			checkAbsolute(pageRel, "canonical", html.UnescapeString(match[1]))
		}

		for _, match := range shareURLRE.FindAllStringSubmatch(pageHTML, -1) {
			checkAbsolute(pageRel, "share address", html.UnescapeString(match[1]))
		}
	}

	allEmitted := make([]string, 0, len(emitted))
	for rel := range emitted {
		allEmitted = append(allEmitted, rel)
	}
	sort.Strings(allEmitted)

	for _, rel := range allEmitted {
		isSitemap := strings.HasSuffix(rel, ".xml") &&
			strings.Contains(path.Base(rel), "sitemap")
		isFeed := path.Base(rel) == "feed.xml"
		if !isSitemap && !isFeed {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(outputDir, filepath.FromSlash(rel)))
		if err != nil {
			return nil, err
		}
		body := string(raw)
		if isSitemap {
			for _, match := range locRE.FindAllStringSubmatch(body, -1) {
				loc := html.UnescapeString(match[1])
				if strings.HasSuffix(loc, ".xml") {
					// A sitemap index names sitemaps, not pages.
					if target, ours := SiteRelativePath(loc, baseURL); ours && !emitted[target] {
						fail(rel, "sitemap index entry "+loc+" was not written")
					}
					continue
				}
				checkAbsolute(rel, "sitemap entry", loc)
			}
			continue
		}
		for _, match := range feedLinkRE.FindAllStringSubmatch(body, -1) {
			link := html.UnescapeString(match[1])
			if strings.HasSuffix(link, "feed.xml") {
				continue
			}
			checkAbsolute(rel, "feed link", link)
		}
	}

	return results, nil
}
