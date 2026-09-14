// Package build is the build pipeline: it walks a project's docs templates,
// resolves their directives, wraps each page in its chrome, and writes a
// whole static site under the configured output directory.
//
// [Build] is the entry point. It loops locales outside versions, builds each
// combination -- the current version from the working tree, every superseded
// one from a git tag extracted into the version cache -- and then writes the
// files that belong to the site rather than to a page: the stylesheet, the
// social cards, the sitemaps, llms.txt, the Atom feed, the favicon,
// robots.txt, the redirect stubs, the search index and the compressed
// companions.
//
// [BuildSingle] is one locale-and-version pass, and the only thing in the
// package that a caller can run without producing a site: it returns
// everything it built instead of writing it, which is what makes the
// in-memory render path possible.
//
// # Every write and every subprocess is declared
//
// Nothing here touches os/exec or the filesystem's mutating calls directly.
// Each function that writes or spawns takes an [effects.Handle] and goes
// through it, so a --dry-run records the whole build instead of performing it.
// Reads are not effects and use the standard library.
//
// # Ordering is sorted, not walk order
//
// The Python this replaces carried insertion-ordered dicts of pages, in the
// arbitrary order os.walk yielded them. A Go map has no order, so every page
// collection here is a slice sorted by the page's docs-relative path, and the
// three decisions that read the order -- which nav group title wins when two
// pages in one directory declare different ones, how two groups whose titles
// sort equal are ordered, and which page is converted first -- are therefore
// decided by path rather than by directory listing.
package build
