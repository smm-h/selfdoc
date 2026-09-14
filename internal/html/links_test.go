package html

import (
	"regexp"
	"strings"
	"testing"
)

// An internal ".md" link must resolve under directory addressing.
//
// A page written as "guide.md" is emitted as "guide/index.html", so the
// page that writes a link sits one directory deeper than its source did.
// Every link a docs page writes therefore has to be re-expressed against
// the EMITTED page's directory, not against the source file's.
//
// The fixtures below are the link shapes the Python suite exercised
// end-to-end through a whole build: a sibling, a sibling with an anchor, a
// same-page anchor, the root index, a subdirectory page, a page one level
// up and a page two levels up. Here they are asserted directly against the
// rewriter, which is where the rule is.

var hrefRE = regexp.MustCompile(`href="([^"]*)"`)

func hrefsIn(html string) []string {
	var out []string
	for _, m := range hrefRE.FindAllStringSubmatch(html, -1) {
		out = append(out, m[1])
	}
	return out
}

func hasHref(hrefs []string, want string) bool {
	for _, h := range hrefs {
		if h == want {
			return true
		}
	}
	return false
}

func assertHrefs(t *testing.T, mdPath, body string, legacy bool, want, unwanted []string) {
	t.Helper()
	hrefs := hrefsIn(RewriteInternalLinks(body, mdPath, legacy))
	for _, w := range want {
		if !hasHref(hrefs, w) {
			t.Errorf("on %s: no href %q; got %v", mdPath, w, hrefs)
		}
	}
	for _, u := range unwanted {
		if hasHref(hrefs, u) {
			t.Errorf("on %s: unexpected href %q; got %v", mdPath, u, hrefs)
		}
	}
}

// "checks.md" written on "guide.md" is "../checks/", not "checks/".
//
// "guide.md" is emitted at "guide/index.html", so the bare "checks/" an
// earlier rewriter produced resolved to "guide/checks/" and named nothing.
func TestASiblingLinkHopsOutOfThePagesOwnDirectory(t *testing.T) {
	assertHrefs(t, "guide.md", `<a href="checks.md">checks</a>`, false,
		[]string{"../checks/"}, []string{"checks/"})
}

func TestASiblingAnchorLinkIsRewrittenToo(t *testing.T) {
	// "checks.md#detail" is an address like any other, fragment kept.
	assertHrefs(t, "guide.md", `<a href="checks.md#detail">detail</a>`, false,
		[]string{"../checks/#detail"}, []string{"checks.md#detail"})
}

func TestASamePageAnchorIsLeftAlone(t *testing.T) {
	assertHrefs(t, "guide.md", `<a href="#section-two">below</a>`, false,
		[]string{"#section-two"}, nil)
}

func TestTheRootIndexIsReachedFromAPageOneLevelDown(t *testing.T) {
	assertHrefs(t, "guide.md", `<a href="index.md">index</a>`, false,
		[]string{"../index.html"}, nil)
}

func TestTheRootPageLinksItsChildrenWithoutAHop(t *testing.T) {
	// "index.md" is emitted at the mount root, so its links climb nothing.
	body := `<a href="guide.md">g</a><a href="guide.md#section-two">s</a>` +
		`<a href="reference/api.md">a</a>`
	assertHrefs(t, "index.md", body, false,
		[]string{"guide/", "guide/#section-two", "reference/api/"}, nil)
}

func TestASubdirectoryPageLinksUpAndDown(t *testing.T) {
	assertHrefs(t, "reference/api.md",
		`<a href="../guide.md">g</a><a href="deep/notes.md">n</a>`, false,
		[]string{"../../guide/", "../deep/notes/"}, nil)

	// "notes.md" is emitted at reference/deep/notes/, so its source-level
	// sibling-of-the-parent hop gains one level on the way out.
	assertHrefs(t, "reference/deep/notes.md",
		`<a href="../api.md">a</a><a href="../../index.md">i</a>`, false,
		[]string{"../../api/", "../../../index.html"}, nil)
}

func TestAPageLinkingItselfAddressesItsOwnDirectory(t *testing.T) {
	assertHrefs(t, "guide.md", `<a href="guide.md">self</a>`, false,
		[]string{"./"}, nil)
}

func TestAnOffsiteReferenceIsNeverRewritten(t *testing.T) {
	body := `<a href="https://x.example/a.md">x</a><a href="/abs.md">abs</a>` +
		`<a href="mailto:a@b.c">m</a><a href="//cdn.example/x.md">c</a>` +
		`<a href="tel:+1">t</a><a href="">e</a>`
	assertHrefs(t, "guide.md", body, false,
		[]string{"https://x.example/a.md", "/abs.md", "mailto:a@b.c",
			"//cdn.example/x.md", "tel:+1", ""}, nil)
}

func TestAReferenceEscapingTheDocsTreeIsLeftAsWritten(t *testing.T) {
	// It names something outside the tree, which is not this build's page
	// to address.
	assertHrefs(t, "guide.md", `<a href="../../../outside.md">out</a>`, false,
		[]string{"../../../outside.md"}, nil)
}

func TestOnlyHrefAndSrcValuesAreRewritten(t *testing.T) {
	// A ".md" path written anywhere else in the body is displayed text --
	// a code sample, a filename in prose -- and rewriting it would corrupt
	// what the page says.
	body := `<p>See checks.md and <code>[x](thing.md)</code>.</p>` +
		`<img src="pic.md" alt="guide.md">`
	got := RewriteInternalLinks(body, "index.md", false)
	mustContain(t, got, "See checks.md and", "[x](thing.md)", `alt="guide.md"`)
	mustContain(t, got, `src="pic/"`)
}

// An archive build's source came out of an immutable git tag and can carry
// links written before this addressing existed, so there they are mapped
// at render time. A build of the working tree never gets that tolerance:
// source under edit must name pages the way the build emits them.
func TestAnArchiveBuildMapsLegacyHTMLLinks(t *testing.T) {
	body := `<a href="checks.html">c</a><a href="checks.html#detail">d</a>` +
		`<a href="index.html">i</a><a href="reference/deep/notes.html">n</a>`
	assertHrefs(t, "guide.md", body, true,
		[]string{"../checks/", "../checks/#detail", "../index.html",
			"../reference/deep/notes/"}, nil)
}

func TestTheWorkingTreeGetsNoLegacyTolerance(t *testing.T) {
	assertHrefs(t, "guide.md", `<a href="checks.html">c</a>`, false,
		[]string{"checks.html"}, []string{"../checks/"})
}

func TestPathHopChoosesTheRootTheTargetBelongsTo(t *testing.T) {
	// A post is a site citizen, served from the site root; a docs page is
	// served from its project's mount, and under a mount those are two
	// different roots.
	if got := PathHop("blog/hello/index.html", "../", "../../"); got != "../../" {
		t.Errorf("a site-level target took the mount hop: %q", got)
	}
	if got := PathHop("guide/index.html", "../", "../../"); got != "../" {
		t.Errorf("a mount target took the site hop: %q", got)
	}
}

func TestPathHelpersRoundTrip(t *testing.T) {
	for _, md := range []string{"index.md", "guide.md", "api/endpoints.md", "a/b/c.md"} {
		if got := HTMLToMdPath(MdToHTMLPath(md)); got != md {
			t.Errorf("%q became %q", md, got)
		}
	}
	if got := HTMLPathToURL(MdToHTMLPath("index.md")); got != "index.html" {
		t.Errorf("the root page's URL is %q", got)
	}
	if got := HTMLPathToURL(MdToHTMLPath("guide.md")); got != "guide/" {
		t.Errorf("a page's URL is %q", got)
	}
}

func TestSplitKeepDelimitersKeepsEveryByte(t *testing.T) {
	// The cross-page term walk depends on the split covering the input
	// exactly once, tags included.
	in := `<p>text <code>x</code> more</p>`
	if got := strings.Join(splitKeepDelimiters(htmlTagSplitRE, in), ""); got != in {
		t.Errorf("the split lost or added bytes: %q", got)
	}
}

// --- What a page's source would emit ---

// TestSourceRefsSpellsAReferenceTheWayTheBuildEmitsIt asserts the derived set
// carries the authored reference in its emitted form, which is the only form
// a built page's href is ever written as.
func TestSourceRefsSpellsAReferenceTheWayTheBuildEmitsIt(t *testing.T) {
	refs := SourceRefs("# Guide\n\nSee the [Guide](missing.md).\n", "guide.md")
	if !refs["../missing/"] {
		t.Fatalf("refs = %v, want the emitted href \"../missing/\"", refs)
	}
	if refs["missing.md"] {
		t.Error("the authored spelling is not what a built page carries")
	}
}

func TestSourceRefsReadsEveryShapeASourceAddressesWith(t *testing.T) {
	source := "# Page\n\n" +
		"[Inline](guide.md)\n" +
		"![Logo](assets/logo.png)\n" +
		"[Titled](api.md \"The API\")\n" +
		"[Fragment](api.md#detail)\n" +
		"<a href=\"raw.md\">Raw</a>\n" +
		"[def]: notes.md\n" +
		"[Away](https://example.com/x)\n" +
		"[Here](#section)\n"
	refs := SourceRefs(source, "index.md")
	for _, want := range []string{
		"guide/", "assets/logo.png", "api/", "api/#detail", "raw/",
		"notes/", "https://example.com/x", "#section",
	} {
		if !refs[want] {
			t.Errorf("refs = %v, missing %q", refs, want)
		}
	}
}

func TestEmittedRefLeavesWhatThisBuildDoesNotAddressAlone(t *testing.T) {
	for _, ref := range []string{
		"https://example.com/", "#section", "/absolute/", "mailto:a@b.c",
		"assets/logo.png", "../../outside.md", "",
	} {
		if got := EmittedRef("guide.md", ref, false); got != ref {
			t.Errorf("EmittedRef(%q) = %q, want it unchanged", ref, got)
		}
	}
}
