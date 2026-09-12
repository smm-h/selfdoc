package html

import (
	"regexp"
	"strings"
	"testing"
)

// idAttrsIn returns every element id present in html.
func idAttrsIn(html string) map[string]bool {
	out := map[string]bool{}
	for _, m := range anyIDAttrRE.FindAllStringSubmatch(html, -1) {
		out[m[1]] = true
	}
	return out
}

func mustContain(t *testing.T, html string, wants ...string) {
	t.Helper()
	for _, want := range wants {
		if !strings.Contains(html, want) {
			t.Errorf("missing %q in:\n%s", want, html)
		}
	}
}

func mustNotContain(t *testing.T, html string, unwanted ...string) {
	t.Helper()
	for _, bad := range unwanted {
		if strings.Contains(html, bad) {
			t.Errorf("unexpected %q in:\n%s", bad, html)
		}
	}
}

// The heading text these two documents repeat, and the fenced "#" line
// that must not become an anchor, are the fixtures the Python suite used
// for the same properties.
const (
	duplicateHeadings = "# Guide\n\nIntro text.\n\n## Setup\n\nFirst setup section.\n\n## Setup\n\nSecond setup section.\n"
	codeFenceBody     = "```python\n# not a heading\nvalue = 1\n```\n\n## Real Heading\n\nBody.\n"
	codeFenceHash     = "# Guide\n\nIntro text.\n\n" + codeFenceBody
)

func TestRepeatedHeadingTextGetsDistinctAnchors(t *testing.T) {
	ids := idAttrsIn(MdToHTML(duplicateHeadings, nil, nil))
	for _, want := range []string{"setup", "setup-1"} {
		if !ids[want] {
			t.Errorf("no heading carries id %q; ids were %v", want, ids)
		}
	}
	var setupIDs []string
	for id := range ids {
		if strings.HasPrefix(id, "setup") {
			setupIDs = append(setupIDs, id)
		}
	}
	if len(setupIDs) != 2 {
		t.Errorf("got %d setup ids (%v), want 2", len(setupIDs), setupIDs)
	}
}

func TestTripledHeadingTextCountsUp(t *testing.T) {
	ids := idAttrsIn(MdToHTML("## Usage\n\n## Usage\n\n## Usage\n", nil, nil))
	for _, want := range []string{"usage", "usage-1", "usage-2"} {
		if !ids[want] {
			t.Errorf("no heading carries id %q; ids were %v", want, ids)
		}
	}
}

func TestAHashLineInsideAFenceIsCodeNotAHeading(t *testing.T) {
	ids := idAttrsIn(MdToHTML(codeFenceHash, nil, nil))
	if ids["not-a-heading"] {
		t.Error(`the fenced "# not a heading" line became an anchor`)
	}
	if !ids["real-heading"] {
		t.Error("the real heading after the fence has no id")
	}
}

func TestHeadingAnchorCarriesAReadableAriaLabel(t *testing.T) {
	mustContain(t, MdToHTML("## parse_directives", nil, nil),
		`aria-label="Link to section: parse directives"`)
	mustContain(t, MdToHTML("## Hello <code>World</code>", nil, nil),
		`aria-label="Link to section: Hello World"`)
}

func TestSlugifiedHeadingIDs(t *testing.T) {
	for _, c := range []struct{ md, wantID string }{
		{"## Deploiement\n", "deploiement"},
		{"## Déploiement\n", "deploiement"},
		{"## 设置\n", "设置"},
	} {
		if !idAttrsIn(MdToHTML(c.md, nil, nil))[c.wantID] {
			t.Errorf("%q produced no id %q", c.md, c.wantID)
		}
	}
}

// The first H1 is the page title, emitted by the page chrome rather than
// by the body renderer, so the body carries no <h1> at all.
func TestTheFirstH1IsConsumedAsTheTitle(t *testing.T) {
	body := MdToHTML("# My Page Title\n\nSome content.\n", nil, nil)
	mustNotContain(t, body, "<h1")
	mustContain(t, body, "Some content.")
}

// CommonMark lets a code span be delimited by any run of backticks, closed
// by a run of the same length: "“x“" is one span, not two empty ones.
// The longer form is what a writer reaches for when the code itself
// contains a backtick, and it is also the form RST-trained writers use by
// habit, so it turns up throughout doc comments.
func TestASpanOfAnyDelimiterLengthIsOneCodeElement(t *testing.T) {
	for _, ticks := range []string{"`", "``", "```"} {
		html := MdToHTML("Reap the "+ticks+"returncode"+ticks+" here.", nil, nil)
		if n := strings.Count(html, "<code>"); n != 1 {
			t.Errorf("%q delimiter produced %d code elements:\n%s", ticks, n, html)
		}
		mustContain(t, html, "<code>returncode</code>")
	}
}

func TestADoubleTickSpanLeavesNoEmptyCodeElements(t *testing.T) {
	// The exact defect the shared scanner fixed: two empty pairs with the
	// text loose between them.
	mustNotContain(t, MdToHTML("Reap the ``returncode`` here.", nil, nil), "<code></code>")
}

func TestADoubleTickSpanCanHoldABacktick(t *testing.T) {
	// Which is the reason the longer delimiter exists at all.
	mustContain(t, MdToHTML("Write ``a ` b`` for that.", nil, nil), "<code>a ` b</code>")
}

func TestOneSpaceEachSideIsStripped(t *testing.T) {
	// CommonMark's rule for spanning a literal backtick at an edge.
	mustContain(t, MdToHTML("Write `` ` `` for that.", nil, nil), "<code>`</code>")
}

func TestInteriorSpacesAreKept(t *testing.T) {
	mustContain(t, MdToHTML("Write ``a  b`` for that.", nil, nil), "<code>a  b</code>")
}

func TestCodeSpanContentIsEscapedAndNotFormatted(t *testing.T) {
	html := MdToHTML("Look at ``<b>**x**</b>`` here.", nil, nil)
	mustContain(t, html, "<code>&lt;b&gt;**x**&lt;/b&gt;</code>")
	mustNotContain(t, html, "<strong>")
}

func TestProseAroundASpanIsStillFormatted(t *testing.T) {
	html := MdToHTML("A **bold** word, ``code``, and [a link](https://example.com).", nil, nil)
	mustContain(t, html,
		"<strong>bold</strong>", "<code>code</code>",
		`<a href="https://example.com">a link</a>`)
}

func TestAnUnclosedBacktickRunIsLiteralText(t *testing.T) {
	// Nothing closes it, so there is no span -- and no stray element.
	mustNotContain(t, MdToHTML("A stray `` tick.", nil, nil), "<code>")
}

func TestInlineStatMarkup(t *testing.T) {
	for _, c := range []struct{ md, want string }{
		{"Uptime is ==99.9%== guaranteed.", `<data value="99.9%">99.9%</data>`},
		{"There are ==42== modules.", `<data value="42">42</data>`},
		{"It runs ==1.5x faster== than before.", `<data value="1.5x faster">1.5x faster</data>`},
	} {
		mustContain(t, MdToHTML(c.md, nil, nil), c.want)
	}
	for _, md := range []string{
		"Set a = b in the config.",
		"Check if x == y in the code.",
		"```\n==42==\n```",
	} {
		mustNotContain(t, MdToHTML(md, nil, nil), "<data")
	}
}

func TestTheFirstImageIsTheHighPriorityCandidate(t *testing.T) {
	result := MdToHTML("![one](a.png)\n\n![two](b.png)\n\n![three](c.png)", nil, nil)
	if n := strings.Count(result, `loading="lazy"`); n != 2 {
		t.Errorf(`got %d lazy images, want 2`, n)
	}
	if n := strings.Count(result, `fetchpriority="high"`); n != 1 {
		t.Errorf(`got %d high-priority images, want 1`, n)
	}
	if n := strings.Count(result, `loading="eager"`); n != 1 {
		t.Errorf(`got %d eager images, want 1`, n)
	}
}

func TestASingleImageStillGetsFetchPriority(t *testing.T) {
	result := MdToHTML("# Title\n\n![logo](logo.png)", nil, nil)
	mustContain(t, result, `fetchpriority="high"`, `loading="eager"`)
	mustNotContain(t, result, `loading="lazy"`)
}

func TestAPageWithNoImagesCarriesNoPriorityAttributes(t *testing.T) {
	mustNotContain(t, MdToHTML("# Title\n\nJust text.", nil, nil),
		"fetchpriority", `loading="eager"`, `loading="lazy"`)
}

// Two consecutive fenced blocks with language labels become one tabbed
// interface, in the ARIA shape the pattern requires.
const twoCodeBlocks = "```python\nprint('hi')\n```\n```go\nfmt.Println()\n```\n"

func TestConsecutiveCodeBlocksBecomeATablist(t *testing.T) {
	result := MdToHTML(twoCodeBlocks, nil, nil)
	mustContain(t, result,
		`role="tablist"`, `role="tab"`, `role="tabpanel"`,
		`aria-selected="true"`, `aria-selected="false"`,
		`aria-controls="panel-python"`, `aria-controls="panel-go"`,
		`id="panel-python"`, `id="panel-go"`,
		`id="tab-python"`, `id="tab-go"`,
		`aria-labelledby="tab-python"`, `aria-labelledby="tab-go"`,
	)
}

func TestASingleCodeBlockIsNotTabbed(t *testing.T) {
	mustNotContain(t, MdToHTML("```python\nprint('hi')\n```\n", nil, nil), "code-tabs")
}

func TestDefinitionListsRenderAGlossaryBlock(t *testing.T) {
	result := MdToHTML(
		"Term One\n: Definition of term one\n\nTerm Two\n: Definition of term two\n", nil, nil)
	mustContain(t, result,
		`<div class="glossary">`, "<dl>",
		`<dt><dfn id="term-term-one">Term One</dfn></dt>`,
		"<dd>Definition of term one</dd>",
		`<dt><dfn id="term-term-two">Term Two</dfn></dt>`,
		"<dd>Definition of term two</dd>",
	)
}

func TestADefinitionListTermMayCarrySeveralDefinitions(t *testing.T) {
	result := MdToHTML("Term One\n: First definition\n: Second definition\n", nil, nil)
	mustContain(t, result,
		`<dt><dfn id="term-term-one">Term One</dfn></dt>`,
		"<dd>First definition</dd>", "<dd>Second definition</dd>")
	if n := strings.Count(result, "<dt>"); n != 1 {
		t.Errorf("got %d terms, want 1", n)
	}
	if n := strings.Count(result, "<dd>"); n != 2 {
		t.Errorf("got %d definitions, want 2", n)
	}
}

func TestParagraphsBesideADefinitionListStayParagraphs(t *testing.T) {
	result := MdToHTML(
		"This is a regular paragraph.\n\nTerm\n: Definition\n\nAnother regular paragraph.\n",
		nil, nil)
	mustContain(t, result,
		"<p>This is a regular paragraph.</p>",
		"<p>Another regular paragraph.</p>",
		`<dt><dfn id="term-term">Term</dfn></dt>`,
		"<dd>Definition</dd>")
}

func TestThematicBreaks(t *testing.T) {
	mustContain(t, MdToHTML("---", nil, nil), "<hr>")
	result := MdToHTML("Above the break.\n\n---\n\nBelow the break.\n", nil, nil)
	mustContain(t, result, "<p>Above the break.</p>", "<hr>", "<p>Below the break.</p>")
}

// A table is emitted inside .table-wrap, which is the element the theme
// makes the scroll container -- so the wrapper's presence is what a sticky
// header rule depends on.
func TestARenderedTableSitsInsideTheWrapper(t *testing.T) {
	html := MdToHTML("| Name | Value |\n| --- | --- |\n| alpha | 1 |\n", nil, nil)
	mustContain(t, html, `<div class="table-wrap">`, "<thead>")
}

func TestATableTakesItsCaptionFromThePrecedingHeading(t *testing.T) {
	html := MdToHTML(
		"# Home\n\n## Data Summary\n\n| Name | Value |\n| ---- | ----- |\n| A | 1 |\n| B | 2 |\n",
		nil, nil)
	mustContain(t, html, `<caption class="sr-only">Data Summary</caption>`)
}

func TestAnExplicitStepsClassIsKeptWhenTheHeuristicIsOff(t *testing.T) {
	md := "## Getting Started\n\n" +
		`<ol class="steps">` + "\n<li>Do this</li>\n<li>Do that</li>\n</ol>\n"
	// The class was in the source HTML, not added by the heuristic, so
	// opting out of the heuristic must not remove it.
	mustContain(t, MdToHTML(md, map[string]any{"auto_steps": false}, nil), `class="steps"`)
}

func TestAnOrderedListAfterAStepHeadingGetsTheStepsClass(t *testing.T) {
	mustContain(t, MdToHTML("## Step one\n\n1. Do this\n2. Do that\n", nil, nil),
		`<ol class="steps">`)
	// An unrelated heading leaves the list alone.
	mustNotContain(t, MdToHTML("## Overview\n\n1. Do this\n", nil, nil), `class="steps"`)
	// And so does opting out per page.
	mustNotContain(t,
		MdToHTML("## Step one\n\n1. Do this\n", map[string]any{"auto_steps": false}, nil),
		`class="steps"`)
}

// The CV directive emits its header block as one line of HTML so the
// converter passes it through whole, and leaves every section as a
// Markdown heading so the sections keep their anchors and reach the table
// of contents.
const cvBody = `<div class="cv-header"><div class="cv-photo">` +
	`<img src="pic.jpg" alt="Profile picture"></div><div class="cv-identity">` +
	`<h2 class="cv-name">Ada Lovelace</h2><div class="cv-subtitle">` +
	`<span>Analyst</span><span>London</span></div></div></div>` +
	"\n\nA summary.\n\n## Skills\n\n- **Languages:** Go\n\n## Education\n\n### BSc\n"

func TestTheCVHeaderCrossesTheConverterIntact(t *testing.T) {
	html := MdToHTML(cvBody, nil, nil)
	mustContain(t, html,
		`<div class="cv-header">`,
		`<img src="pic.jpg" alt="Profile picture"`,
		`<h2 class="cv-name">Ada Lovelace</h2>`,
		"<span>Analyst</span>")
}

func TestTheCVSectionsStillBecomeHeadingsWithAnchors(t *testing.T) {
	html := MdToHTML(cvBody, nil, nil)
	mustContain(t, html, `<h2 id="skills">`, `<h2 id="education">`)
}

// A diff fence emits no "+" or "-" character: the framework draws the
// marker as generated content in a gutter, so a copied selection is the
// code without the diff column.
func TestDiffLinesCarryTheirClassesAndNotTheirMarkers(t *testing.T) {
	html := MdToHTML("```diff\n+added\n-removed\n same\n```\n", nil, nil)
	mustContain(t, html,
		`<span class="tm-code-line tm-code-add">added</span>`,
		`<span class="tm-code-line tm-code-del">removed</span>`)
}

func TestAnnotationMarkersBecomeBadges(t *testing.T) {
	html := MdToHTML("```\nvalue = 1  # [1]\n```\n[1]: the note\n", nil, nil)
	mustContain(t, html, `<span class="code-annotation" data-note="the note" tabindex="0">1</span>`)
	mustNotContain(t, html, "# [1]")
}

var codeLineRE = regexp.MustCompile(`<span class="tm-code-line">`)

func TestLineNumbersWrapEveryLineAndResetTheCounter(t *testing.T) {
	html := MdToHTML("```text lines=5\nalpha\nbeta\n```\n", nil, nil)
	mustContain(t, html, "tm-code-numbered", `data-line-start="5"`,
		"counter-reset:tm-code-line 4")
	if n := len(codeLineRE.FindAllString(html, -1)); n != 2 {
		t.Errorf("got %d wrapped lines, want 2", n)
	}
}

func TestAdmonitionsRenderAsCallouts(t *testing.T) {
	for _, c := range []struct{ marker, kind, role string }{
		{"NOTE", "note", "note"},
		{"TIP", "tip", "note"},
		{"IMPORTANT", "info", "note"},
		{"WARNING", "warn", "note"},
		{"CAUTION", "danger", "alert"},
	} {
		html := MdToHTML("> [!"+c.marker+"]\n> Body text.\n", nil, nil)
		mustContain(t, html,
			`<div class="tm-callout tm-callout-`+c.kind+`" role="`+c.role+`">`,
			"<p>Body text.</p>")
	}
	// An unrecognized marker is a plain blockquote, marker text and all.
	mustContain(t, MdToHTML("> [!BOGUS]\n> body\n", nil, nil), "<blockquote><p>")
}

func TestAdmonitionTypesAreTheCalloutKeys(t *testing.T) {
	want := []string{"CAUTION", "IMPORTANT", "NOTE", "TIP", "WARNING"}
	got := AdmonitionTypes()
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Errorf("got %v, want %v", got, want)
	}
	for _, name := range got {
		if _, ok := CalloutKindFor(name); !ok {
			t.Errorf("%s is an admonition type with no callout kind", name)
		}
	}
}

func TestTableAlignmentMarkersBecomeStyles(t *testing.T) {
	html := ParseTable([]string{"| a | b | c |", "| :-- | :-: | --: |", "| 1 | 2 | 3 |"})
	mustContain(t, html,
		`<th class="sortable" role="columnheader" aria-sort="none" style="text-align: left">`,
		`style="text-align: center"`, `style="text-align: right"`,
		"<tfoot></tfoot>")
}

func TestAnEscapedPipeIsALiteralPipeInACell(t *testing.T) {
	html := ParseTable([]string{`| a \| b | c |`, "| --- | --- |", "| x | y |"})
	mustContain(t, html, "a | b")
}
