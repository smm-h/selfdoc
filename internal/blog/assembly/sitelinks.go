package assembly

import (
	stdhtml "html"
	"os"
	"strings"

	"github.com/smm-h/selfdoc/internal/blog/chrome"
	"github.com/smm-h/selfdoc/internal/effects"
	"github.com/smm-h/selfdoc/internal/resolution"
)

// RelativizeSiteLinks re-expresses every clickable link in the assembled tree
// that names the site's own base as a document-relative reference, and returns
// the site-relative paths it changed.
//
// A link a reader clicks has to resolve under whatever mount the tree is
// served from -- production, a preview, a mirror -- so the one addressed at
// "https://<site>/blog/" is wrong in a way the file-existence half of the
// resolution check can never see: the page it names really is there, on
// production, which is where the click quietly goes from everywhere else.
// [github.com/smm-h/selfdoc/internal/resolution] states the rule and refuses a
// tree that breaks it.
//
// This runs over every page in the tree, beside the chrome re-pointing pass
// and for the same reason. The assembly is never rebuilt whole: a project's
// subtree is replaced only when that project deploys, so pages an older
// toolchain wrote outlive it, and a rule the verification applies to the whole
// tree would otherwise refuse every deploy over pages the dispatch did not
// write and could not fix. Sweeping them here is what lets the tree converge.
//
// pages are site-relative HTML paths, as [chrome.EmittedPages] returns them.
// canonicalBase is the site's own base URL; a reference to any other host is
// somebody else's address and is left alone.
func RelativizeSiteLinks(
	siteDir, canonicalBase string, pages []string, h *effects.Handle,
) ([]string, error) {
	base := strings.TrimRight(canonicalBase, "/")
	if base == "" {
		return nil, errorf("canonical base is required to recognise a link that names this site")
	}
	changed := make([]string, 0)
	for _, pageRel := range pages {
		path := sitePath(siteDir, pageRel)
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		pageHTML := string(raw)
		hop := chrome.SiteRootPrefix(pageRel)
		rewritten := resolution.RewriteNavigationReferences(
			pageHTML,
			func(ref string) (string, bool) { return relativeSiteHref(ref, base, hop) },
		)
		if rewritten == pageHTML {
			continue
		}
		if err := h.AtomicWrite(path, []byte(rewritten), effects.ModeDefault); err != nil {
			return nil, err
		}
		changed = append(changed, pageRel)
	}
	return changed, nil
}

// relativeSiteHref returns the document-relative spelling of an href that
// names this site, and whether it named it at all.
//
// hop is the reference from the page carrying the link back to the site root.
// Whether the link is this site's is asked of the resolution package, which is
// the authority the check itself reads; the cut is then made on the attribute
// as written, so whatever escaping the rest of the reference carries survives
// untouched. An attribute whose base is spelled some other way than the value
// that answered the question is left alone rather than cut at a guessed
// offset.
func relativeSiteHref(ref, base, hop string) (string, bool) {
	if _, ours := resolution.SiteRelativePath(stdhtml.UnescapeString(ref), base); !ours {
		return "", false
	}
	rest := ""
	switch {
	case ref == base:
	case strings.HasPrefix(ref, base+"/"):
		rest = ref[len(base)+1:]
	default:
		return "", false
	}
	relative := hop + rest
	if relative == "" {
		// The site root, addressed from a page at the site root.
		relative = "./"
	}
	return relative, true
}
