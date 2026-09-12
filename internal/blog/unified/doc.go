// Package unified builds one documentation site out of several constituent
// projects plus a docs-site's own cross-cutting content.
//
// Each constituent project is built from its own selfdoc.json; the docs-site's
// config supplies the orchestration through its "unified" block, which names
// the projects, their slugs and their navigation titles. Every project is
// mounted under its slug, the docs-site's own pages under "common", and the
// posts of every project land in the one site-level "blog/" tree they share.
//
// [BuildUnified] is the entry point. It wipes the output directory, injects
// every project's posts into that project's docs tree, partitions the pages,
// builds one pass per docs-site version, constituent and locale, and then
// writes the files that belong to the site rather than to a page: the landing
// page listing the projects, the shared stylesheet, the auxiliary documents,
// the root redirect stub, the Cloudflare redirect rule, the search index over
// the whole tree and the compressed companions.
//
// # The docs-site is the (N+1)th project
//
// Its own pages are a mount like any other, which is what makes the landing
// page's card links and the shared stylesheet hop correct: both are computed
// from the landing page's own address rather than from a site-root path that
// would only resolve when the site is served from an origin root.
//
// # Every write and every subprocess is declared
//
// Nothing here touches the filesystem's mutating calls or os/exec directly:
// each is routed through the effects handle the caller passes in, so a
// --dry-run records the whole unified build instead of performing it. Reads
// are not effects and use the standard library.
package unified
