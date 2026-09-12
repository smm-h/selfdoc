// Package page builds the chrome a converted Markdown body is wrapped in.
//
// The body HTML itself comes from the html package; everything a reader sees
// around it is built here: the sidebar and its navigation tree, the topbar,
// the table of contents, the breadcrumbs, the version and locale pickers,
// the superseded-version notice, the share control, the page footer, the
// search surface, the Pagefind filter and metadata elements, and every SEO
// tag in the head including the JSON-LD documents.
//
// GenerateHTML is the entry point the build calls once per locale-and-version
// pass. It converts every page of one mount, collects the terms the pages
// declared, synthesizes the glossary page from them, and wraps each page in
// the full document -- returning a map keyed by each page's output key, so no
// caller has to staple the mount prefix on afterwards.
//
// # Ordered inputs
//
// The Python surface this replaces passed insertion-ordered dicts of
// Markdown sources, and three decisions read that order: which nav group
// title wins when two pages in one directory declare different ones, how
// two groups whose titles sort equal are ordered, and the order pages are
// converted in. A Go map has no order, so the sources arrive as a slice of
// SourceFile and the order is the caller's to state.
//
// # JSON-LD is emitted in Python's spelling
//
// The structured data is written with the separators and the key order
// Python's json.dumps produces -- ", " between items, ": " between a key and
// its value, and properties in the order the emitter built them. That is why
// identity.Entity is an ordered property list and why util.PythonJSON, which
// sorts keys and writes no spaces, is not what emits these documents.
package page
