// Package shared generates the elements of an assembled documentation site
// that belong to the site rather than to any one project.
//
// Every constituent project's own build writes a full standalone site: its
// pages, its stylesheet, its robots.txt, its llms.txt, its sitemap, its feed.
// Grafted under a project slug those site-level files end up at
// "<slug>/robots.txt" where no crawler reads them. The ones that answer are
// the ones generated here, once, for the whole site: the project listing,
// the site-wide blog index, the navigation document, the aggregated Atom feed,
// the sitemap, robots.txt, llms.txt and the root 404 page.
//
// # The address authority
//
// [PageTarget] and [PostTarget] are the one place that decides where a
// manifest entry lives on the assembled site, and [TargetOutputPath] and
// [OutputPathTarget] convert between that address and the emitted file. The
// blog index, the sitemap, the feed, the cross-project link check and the
// deploy-time verifier all address pages through them, so they cannot
// disagree about where a page is.
//
// # Escaping
//
// Every string this package interpolates into markup goes through
// [EscapeHTML], which escapes the apostrophe as well as the ampersand, the
// angle brackets and the double quote. That is what the Python this package
// replaces emitted, and it is deliberately not util.EscapeHTML, which leaves
// the apostrophe alone for the page emitters below it.
package shared
