package js

import (
	"io/fs"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

// pythonJSDir is where the Python package this port replaces keeps the same
// scripts. The byte-identity test below reads it and skips when it is gone,
// because the Python tree is deleted at the end of the port.
const pythonJSDir = "../../selfdoc_core/js"

func mustLoadT(t *testing.T, name string) string {
	t.Helper()
	source, err := Load(name)
	if err != nil {
		t.Fatalf("Load(%q): %v", name, err)
	}
	return source
}

// --- Loading ---

func TestLoadReadsEveryEmbeddedScript(t *testing.T) {
	entries, err := fs.ReadDir(scripts, ".")
	if err != nil {
		t.Fatalf("reading the script directory: %v", err)
	}
	if len(entries) == 0 {
		t.Fatal("no scripts are embedded")
	}
	for _, entry := range entries {
		name := strings.TrimSuffix(entry.Name(), ".js")
		if source := mustLoadT(t, name); strings.TrimSpace(source) == "" {
			t.Errorf("%s is empty", entry.Name())
		}
	}
}

func TestLoadRefusesAnUnknownScript(t *testing.T) {
	_, err := Load("nowhere")
	if err == nil {
		t.Fatal("an unknown script was accepted")
	}
	if !strings.Contains(err.Error(), "nowhere") {
		t.Errorf("error %q does not name the script", err)
	}
	// The name is used verbatim, so a name that already carries the extension
	// is a different script and is refused too.
	if _, err := Load("head.js"); err == nil {
		t.Error("Load(\"head.js\") was accepted; the name carries no extension")
	}
}

func TestTheHeadScriptAppliesTheStoredThemeBeforeTheFirstPaint(t *testing.T) {
	head := Head()
	if head != mustLoadT(t, "head") {
		t.Error("Head() is not head.js")
	}
	for _, want := range []string{"selfdoc-theme", "data-theme", "scrollBehavior"} {
		if !strings.Contains(head, want) {
			t.Errorf("the head script does not mention %q", want)
		}
	}
}

func TestTheAnalyticsScriptReadsItsIDFromItsOwnElement(t *testing.T) {
	ga := Analytics()
	if ga != mustLoadT(t, "ga") {
		t.Error("Analytics() is not ga.js")
	}
	for _, want := range []string{"dataLayer", "currentScript.dataset.gaId"} {
		if !strings.Contains(ga, want) {
			t.Errorf("the analytics script does not mention %q", want)
		}
	}
}

// --- What each script has to contain ---

func TestScrollspyIncludesScrollIntoView(t *testing.T) {
	if !strings.Contains(mustLoadT(t, "scrollspy"), "scrollIntoView") {
		t.Error("scrollspy does not scroll the active entry into view")
	}
}

func TestCodeTabsHasASyncingGuard(t *testing.T) {
	if !strings.Contains(mustLoadT(t, "code-tabs"), "syncing") {
		t.Error("code-tabs has no re-entrancy guard")
	}
}

func TestSidebarHandlesEscape(t *testing.T) {
	if !strings.Contains(mustLoadT(t, "sidebar"), "Escape") {
		t.Error("sidebar has no Escape handler")
	}
}

// --- The bundle ---

// alwaysAndLast is the block list of a page that triggers no probe.
var alwaysAndLast = []string{
	"theme-toggle", "sidebar", "nav-groups", "scroll-affordance",
	"reading-progress", "smooth-scroll",
}

func TestBodyScriptsOfAnEmptyPageIsTheAlwaysIncludedSet(t *testing.T) {
	got := BodyScripts(PageHTML{})
	if !slices.Equal(got, alwaysAndLast) {
		t.Errorf("blocks = %v, want %v", got, alwaysAndLast)
	}
}

func TestEachProbeIncludesItsOwnBlock(t *testing.T) {
	cases := []struct {
		name  string
		page  PageHTML
		block string
	}{
		{"a version picker in the chrome", PageHTML{Chrome: `<div class="sel version-picker">`}, "pickers"},
		{"a locale picker in the chrome", PageHTML{Chrome: `<div class="sel locale-picker">`}, "pickers"},
		{"a code block in the body", PageHTML{Body: "<pre>code</pre>"}, "copy-button"},
		{"a table of contents", PageHTML{TOC: `<nav class="toc"></nav>`}, "scrollspy"},
		{"a feedback widget in the footer", PageHTML{Footer: `<div class="feedback">`}, "feedback"},
		{"tabbed code in the body", PageHTML{Body: `<div class="code-tabs">`}, "code-tabs"},
		// A real runnable example is a <pre, which brings the copy button with
		// it; the marker alone is enough to show which probe owns the block.
		{"a runnable example", PageHTML{Body: `<div data-run="true">`}, "run-button"},
		{"a heading link", PageHTML{Body: `<a class="heading-link">`}, "heading-copy"},
		{"a table wrapper", PageHTML{Body: `<div class="table-wrap">`}, "sortable-tables"},
		{"an archive notice in the extras", PageHTML{Extras: `<div data-notice-key="v1">`}, "version-notice"},
		{"a share control in the extras", PageHTML{Extras: `<div class="share-address">`}, "share-address"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := BodyScripts(tc.page)
			if !slices.Contains(got, tc.block) {
				t.Fatalf("blocks = %v, missing %q", got, tc.block)
			}
			for _, name := range got {
				if name != tc.block && !slices.Contains(alwaysAndLast, name) {
					t.Errorf("blocks = %v, which carries the unrelated %q", got, name)
				}
			}
		})
	}
}

func TestAProbeReadsOnlyItsOwnFragment(t *testing.T) {
	// Every needle placed in the wrong fragment: the page renderer's split is
	// the whole reason the probes are per-fragment, and a probe reading the
	// wrong one would ship a handler for an element that is not there.
	misplaced := []PageHTML{
		{Body: `<div class="sel version-picker">`},
		{Chrome: "<pre>code</pre>"},
		{Body: `<div class="feedback">`},
		{Body: `<div data-notice-key="v1">`},
		{Body: `<div class="share-address">`},
		{Footer: `<div class="code-tabs">`},
		{Extras: `<pre data-run="true">`},
	}
	for _, page := range misplaced {
		got := BodyScripts(page)
		if !slices.Equal(got, alwaysAndLast) {
			t.Errorf("page %+v produced %v", page, got)
		}
	}
}

func TestTheBundleOrderIsTheDeclaredOrder(t *testing.T) {
	// Every probe triggered at once: the always-included blocks first, the
	// conditional ones in declaration order, and the smooth scroll restore
	// last, because it has to run after every block that may scroll.
	page := PageHTML{
		Body:   `<pre data-run="true">code</pre><div class="code-tabs"></div><a class="heading-link"></a><div class="table-wrap"></div>`,
		TOC:    `<nav class="toc"></nav>`,
		Footer: `<div class="feedback"></div>`,
		Extras: `<div data-notice-key="v1"></div><div class="share-address"></div>`,
		Chrome: `<div class="sel version-picker"></div>`,
	}
	want := []string{
		"theme-toggle", "sidebar", "nav-groups", "scroll-affordance",
		"reading-progress", "pickers", "copy-button", "scrollspy", "feedback",
		"code-tabs", "run-button", "heading-copy", "sortable-tables",
		"version-notice", "share-address", "smooth-scroll",
	}
	if got := BodyScripts(page); !slices.Equal(got, want) {
		t.Fatalf("blocks = %v, want %v", got, want)
	}
	// Every block a page carries is in the bundle whole, and the bundle is
	// their sources joined by newlines and nothing else.
	var sources []string
	for _, name := range want {
		sources = append(sources, mustLoadT(t, name))
	}
	if got := AssembleBody(page); got != strings.Join(sources, "\n") {
		t.Error("the bundle is not the blocks joined by newlines")
	}
}

func TestTheBundleCarriesEveryBlockOfAMixedPage(t *testing.T) {
	// No block may be swallowed by the block above it: every one of them
	// appears in the bundle in full.
	page := PageHTML{
		Body:   "<pre>code</pre>",
		Extras: `<div class="tm-notice tm-notice-warn"></div>`,
		Chrome: `<div class="sel version-picker">`,
	}
	bundle := AssembleBody(page)
	names := BodyScripts(page)
	if len(names) != 8 {
		// Five always, plus pickers and copy-button, plus the restore. The
		// extras here carry no data-notice-key, so no archive notice block.
		t.Fatalf("blocks = %v", names)
	}
	for _, name := range names {
		if !strings.Contains(bundle, mustLoadT(t, name)) {
			t.Errorf("the bundle does not carry %q in full", name)
		}
	}
	if strings.Contains(bundle, mustLoadT(t, "version-notice")) {
		t.Error("the bundle carries the archive notice block for a page with no notice")
	}
}

func TestTheBundleAlwaysEndsWithTheSmoothScrollRestore(t *testing.T) {
	for _, page := range []PageHTML{
		{},
		{Body: "<pre>code</pre>"},
		{TOC: "toc", Chrome: "version-picker"},
	} {
		names := BodyScripts(page)
		if names[len(names)-1] != smoothScroll {
			t.Errorf("blocks = %v, which does not end with %q", names, smoothScroll)
		}
		if !strings.HasSuffix(AssembleBody(page), mustLoadT(t, smoothScroll)) {
			t.Error("the bundle does not end with the smooth scroll restore")
		}
	}
}

// --- Nothing is embedded that no page can load ---

func TestEveryEmbeddedScriptIsReachable(t *testing.T) {
	reachable := map[string]bool{"head": true, "ga": true, smoothScroll: true}
	for _, name := range alwaysIncluded {
		reachable[name] = true
	}
	for _, block := range conditionals {
		reachable[block.script] = true
	}
	entries, err := fs.ReadDir(scripts, ".")
	if err != nil {
		t.Fatalf("reading the script directory: %v", err)
	}
	for _, entry := range entries {
		name := strings.TrimSuffix(entry.Name(), ".js")
		if !reachable[name] {
			t.Errorf("%s is embedded but no page ever loads it", entry.Name())
		}
		delete(reachable, name)
	}
	for name := range reachable {
		t.Errorf("%q is wired into the bundle but no such script is embedded", name)
	}
}

func TestNoBlockIsIncludedTwice(t *testing.T) {
	seen := map[string]bool{}
	for _, name := range append(append([]string(nil), alwaysIncluded...), smoothScroll) {
		if seen[name] {
			t.Errorf("%q is in the always-included set twice", name)
		}
		seen[name] = true
	}
	for _, block := range conditionals {
		if seen[block.script] {
			t.Errorf("%q is both always included and conditional", block.script)
		}
		seen[block.script] = true
	}
}

// --- The embedded scripts are the Python package's bytes ---

func TestEveryEmbeddedScriptIsThePythonSourceByteForByte(t *testing.T) {
	entries, err := os.ReadDir(pythonJSDir)
	if err != nil {
		t.Skipf("the Python js package is gone: %v", err)
	}
	python := map[string]bool{}
	for _, entry := range entries {
		if strings.HasSuffix(entry.Name(), ".js") {
			python[entry.Name()] = true
		}
	}
	embedded, err := fs.ReadDir(scripts, ".")
	if err != nil {
		t.Fatalf("reading the script directory: %v", err)
	}
	for _, entry := range embedded {
		name := entry.Name()
		want, err := os.ReadFile(filepath.Join(pythonJSDir, name))
		if err != nil {
			t.Errorf("%s is embedded but the Python package does not ship it: %v", name, err)
			continue
		}
		got, err := scripts.ReadFile(name)
		if err != nil {
			t.Fatalf("reading embedded %s: %v", name, err)
		}
		if string(got) != string(want) {
			t.Errorf("embedded %s differs from the Python source", name)
		}
		delete(python, name)
	}
	for name := range python {
		t.Errorf("the Python package ships %s, which is not embedded here", name)
	}
}
