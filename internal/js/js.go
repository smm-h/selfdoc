// Package js carries the browser scripts a built page ships and assembles the
// body bundle each page needs.
//
// The scripts are authored as .js files in this package and embedded, never
// written as string literals in Go: a script that lives in a Go source file
// gets no syntax checking, no editor support and no diff a reviewer can read.
//
// # What a page loads
//
// Two scripts sit in the head -- [Head], which applies the stored colour
// scheme before the first paint, and [Analytics], which is injected only when
// the project configures it. Everything else is one bundle at the end of the
// body, assembled by [AssembleBody].
//
// The bundle is not the whole directory. Five blocks are on every page; the
// rest are included only when the rendered HTML shows the element they drive,
// which the assembler decides by probing the fragments the page renderer
// already holds. A page with no code block ships no copy-button handler, and a
// page with no table of contents ships no scrollspy.
package js

import (
	"embed"
	"fmt"
	"strings"
)

// scripts holds every browser script this build ships.
//
//go:embed *.js
var scripts embed.FS

// Load returns the source of the named script, without its .js extension --
// Load("theme-toggle") reads theme-toggle.js. An unknown name is an error.
func Load(name string) (string, error) {
	source, err := scripts.ReadFile(name + ".js")
	if err != nil {
		return "", fmt.Errorf("no bundled script named %q", name)
	}
	return string(source), nil
}

// mustLoad returns the source of a script this package names itself. A missing
// one is a broken build rather than a runtime condition, because the name is a
// constant and the file is embedded beside it.
func mustLoad(name string) string {
	source, err := Load(name)
	if err != nil {
		// Unreachable: the file is embedded above.
		panic(err)
	}
	return source
}

// Head returns the script every page runs in its head, before the first
// paint: it applies the colour scheme the visitor last chose and switches
// scroll behaviour to instant so an initial in-page landing does not animate.
func Head() string {
	return mustLoad("head")
}

// Analytics returns the Google Analytics configuration script, which a page
// carries only when the project's feedback settings name a measurement id. It
// reads that id from its own script element's data-ga-id attribute.
func Analytics() string {
	return mustLoad("ga")
}

// PageHTML is the rendered page, in the fragments [AssembleBody] probes to
// decide which conditional blocks the page needs.
//
// The split is the page renderer's own: the article body, the table of
// contents, the footer, the template-level extras the wrapper renders around
// the body (the superseded-version notice and the share control), and the
// chrome outside the article (the topbar, where the two pickers live).
type PageHTML struct {
	// Body is the article body HTML.
	Body string
	// TOC is the table-of-contents HTML, empty when the page has none.
	TOC string
	// Footer is the page footer HTML.
	Footer string
	// Extras is the template-level HTML the article body does not carry.
	Extras string
	// Chrome is the page chrome outside the article.
	Chrome string
}

// alwaysIncluded is the blocks every page runs, in the order they are
// concatenated.
var alwaysIncluded = []string{
	"theme-toggle",
	"sidebar",
	"nav-groups",
	"scroll-affordance",
	"reading-progress",
}

// smoothScroll is always the last block: it restores the smooth scroll
// behaviour Head switched off, and has to run after every block that may
// scroll the page into position.
const smoothScroll = "smooth-scroll"

// conditional is a block included only when a probe finds its element in the
// rendered page. The order is the order of the assembled bundle.
type conditional struct {
	// script is the block's name, without the .js extension.
	script string
	// needle is the substring the probe looks for.
	needle string
	// fragment selects which fragment of the page the probe reads.
	fragment func(page PageHTML) string
	// alternative is a second substring in the same fragment that also
	// includes the block, empty when there is only one.
	alternative string
	// present includes the block whenever the fragment is non-empty, instead
	// of probing for a substring.
	present bool
}

func bodyOf(page PageHTML) string   { return page.Body }
func tocOf(page PageHTML) string    { return page.TOC }
func footerOf(page PageHTML) string { return page.Footer }
func extrasOf(page PageHTML) string { return page.Extras }
func chromeOf(page PageHTML) string { return page.Chrome }

// conditionals is every block that is not on every page, with the probe that
// includes it. It is the whole conditional surface: a script added to this
// package without an entry here is a script no page ever loads.
var conditionals = []conditional{
	{script: "pickers", needle: "version-picker", alternative: "locale-picker", fragment: chromeOf},
	{script: "copy-button", needle: "<pre", fragment: bodyOf},
	{script: "scrollspy", present: true, fragment: tocOf},
	{script: "feedback", needle: `class="feedback"`, fragment: footerOf},
	{script: "code-tabs", needle: `class="code-tabs"`, fragment: bodyOf},
	{script: "run-button", needle: `data-run="true"`, fragment: bodyOf},
	{script: "heading-copy", needle: `class="heading-link"`, fragment: bodyOf},
	{script: "sortable-tables", needle: `class="table-wrap"`, fragment: bodyOf},
	{script: "version-notice", needle: "data-notice-key=", fragment: extrasOf},
	{script: "share-address", needle: `class="share-address"`, fragment: extrasOf},
}

// includes reports whether this block's probe finds its element in page.
func (c conditional) includes(page PageHTML) bool {
	fragment := c.fragment(page)
	if c.present {
		return fragment != ""
	}
	if strings.Contains(fragment, c.needle) {
		return true
	}
	return c.alternative != "" && strings.Contains(fragment, c.alternative)
}

// BodyScripts returns the names of the blocks a page ships, in bundle order.
//
// It is what [AssembleBody] concatenates, exposed on its own because a build
// stage that reports or checks a page's payload wants the names rather than
// the bytes.
func BodyScripts(page PageHTML) []string {
	names := append([]string(nil), alwaysIncluded...)
	for _, block := range conditionals {
		if block.includes(page) {
			names = append(names, block.script)
		}
	}
	return append(names, smoothScroll)
}

// AssembleBody returns the body bundle for page: the always-included blocks,
// then every conditional block whose element the page carries, then the smooth
// scroll restore, joined by newlines and not yet minified.
func AssembleBody(page PageHTML) string {
	names := BodyScripts(page)
	sources := make([]string, 0, len(names))
	for _, name := range names {
		sources = append(sources, mustLoad(name))
	}
	return strings.Join(sources, "\n")
}
