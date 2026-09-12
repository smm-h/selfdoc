package themes

import (
	"regexp"
	"strings"
	"testing"
)

// Structural checks on how the themes present a table.
//
// A table is emitted inside .table-wrap, which sets overflow-x: auto and
// therefore becomes the table's scroll container. A sticky thead offset from
// the top of that container is offset from the top of the table, not from the
// topbar -- so the header row slides down over the first body rows and
// overlaps them. The offset only ever made sense when the viewport was the
// scrollport, which it never is here.
//
// The unit is the composed stylesheet, not the theme file. A theme that
// declares a framework ships as an overlay on someone else's sheets, and the
// sticky header is one of the things it stops restating -- reading the overlay
// alone would report the rule as missing when what happened is that the
// framework now carries it.
//
// The checks are registry-driven: a theme added without these rules is a theme
// whose sticky header overlaps its own first rows, and the suite says so
// without anybody remembering to extend a list.

// theadRuleRe matches the sticky thead rule body in either spelling: the whole
// row group or the header cells inside it. A framework theme states it the
// second way, and both make the header stick.
var theadRuleRe = regexp.MustCompile(`(?m)(?:^|[,\s])(?:\.tm-table\s+)?thead(?:\s+th)?\s*\{([^}]*)\}`)

func theadRules(css string) []string {
	var bodies []string
	for _, match := range theadRuleRe.FindAllStringSubmatch(css, -1) {
		bodies = append(bodies, match[1])
	}
	return bodies
}

var (
	stickyTopZeroRe  = regexp.MustCompile(`top:\s*0;`)
	stickyTopPixelRe = regexp.MustCompile(`top:\s*\d+px`)
	tableWrapRe      = regexp.MustCompile(`\.table-wrap\s*\{([^}]*)\}`)
	pinnedAfterRe    = regexp.MustCompile(`\.table-wrap\.has-overflow\s+(?:th|td):first-child::after`)
	pinnedBeforeRe   = regexp.MustCompile(`\.table-wrap\.has-overflow\s+th:first-child::before`)
	emptyParagraphRe = regexp.MustCompile(`p:empty\s*\{([^}]*)\}`)
)

// eachTheme runs check against every registered theme's composed stylesheet.
func eachTheme(t *testing.T, check func(t *testing.T, css string)) {
	t.Helper()
	for _, name := range List() {
		t.Run(name, func(t *testing.T) {
			check(t, mustCSS(t, name))
		})
	}
}

func TestTheThemeHasOneStickyTheadRule(t *testing.T) {
	eachTheme(t, func(t *testing.T, css string) {
		if got := theadRules(css); len(got) != 1 {
			t.Errorf("thead rule count = %d, want 1", len(got))
		}
	})
}

func TestTheStickyHeaderIsFlushWithItsScrollport(t *testing.T) {
	// top is 0: the scrollport is the wrapper, not the viewport.
	eachTheme(t, func(t *testing.T, css string) {
		rules := theadRules(css)
		if len(rules) == 0 {
			t.Fatal("no thead rule")
		}
		if !strings.Contains(rules[0], "position: sticky") {
			t.Errorf("the thead rule is not sticky: %s", rules[0])
		}
		if !stickyTopZeroRe.MatchString(rules[0]) {
			t.Errorf("the thead rule does not sit at top: 0: %s", rules[0])
		}
	})
}

func TestNoTopbarCompensationIsLeftInTheTheadRule(t *testing.T) {
	// A pixel offset here is the viewport-topbar assumption returning.
	eachTheme(t, func(t *testing.T, css string) {
		rules := theadRules(css)
		if len(rules) == 0 {
			t.Fatal("no thead rule")
		}
		if stickyTopPixelRe.MatchString(rules[0]) {
			t.Errorf("the thead rule carries a pixel offset: %s", rules[0])
		}
	})
}

func TestTheWrapperIsTheScrollport(t *testing.T) {
	// The premise of the rule above: .table-wrap scrolls.
	eachTheme(t, func(t *testing.T, css string) {
		match := tableWrapRe.FindStringSubmatch(css)
		if match == nil {
			t.Fatal("no .table-wrap rule")
		}
		if !strings.Contains(match[1], "overflow-x: auto") {
			t.Errorf(".table-wrap does not scroll: %s", match[1])
		}
	})
}

func TestThePinnedColumnEdgeKeepsOffTheSortCaret(t *testing.T) {
	// The pinned column's edge hairline and the sort caret are both ::after.
	// Every markdown table header cell is emitted with aria-sort="none", and a
	// theme paints the sort indicator on th[aria-sort]::after. An element has
	// one ::after, so a pinned-column rule that also claims ::after on
	// th:first-child does not sit behind the caret -- it IS the caret's box,
	// restyled into a 4px full-height bar. The first column's indicator
	// disappears while every other column keeps one. The edge belongs on
	// ::before, which nothing else claims.
	eachTheme(t, func(t *testing.T, css string) {
		if pinnedAfterRe.MatchString(css) {
			t.Error("the pinned-column edge claims the header cell's ::after")
		}
		if !pinnedBeforeRe.MatchString(css) {
			t.Error("the pinned-column edge is not painted on ::before")
		}
	})
}

func TestTheThemeHidesEmptyParagraphs(t *testing.T) {
	// A directive's block element leaves empty paragraphs around it:
	// <p><div class="callout">...</div></p> parses as an empty paragraph, the
	// div, and another empty paragraph. Both carry the paragraph margin and
	// space out content that is not there.
	eachTheme(t, func(t *testing.T, css string) {
		match := emptyParagraphRe.FindStringSubmatch(css)
		if match == nil {
			t.Fatal("no p:empty rule")
		}
		if !strings.Contains(match[1], "display: none") {
			t.Errorf("p:empty is not hidden: %s", match[1])
		}
	})
}

var (
	tableCodeNeutralisedRe = regexp.MustCompile(`\.tm-table\s+(?:th|td)\s+code:not\(\[class\]\)[^{]*\{([^}]*)\}`)
	proseChipRe            = regexp.MustCompile(`\.doc-body\s+p\s+code:not\(\[class\]\)\s*\{([^}]*)\}`)
	borderZeroRe           = regexp.MustCompile(`border:\s*0`)
	paddingZeroRe          = regexp.MustCompile(`padding:\s*0`)
)

func TestTheOverlayStripsTheCodeChipInsideATable(t *testing.T) {
	// Data tables are mostly code spans; chips make them unreadable.
	// tinymoon's prose.css boxes every unclassed code -- background, border,
	// padding -- which reads well in a sentence and terribly in a grid where
	// every cell is one. The overlay neutralises the box inside .tm-table
	// only, so prose keeps its chip.
	css := mustCSS(t, "tinymoon")
	matches := tableCodeNeutralisedRe.FindAllStringSubmatch(css, -1)
	if len(matches) == 0 {
		t.Fatal("no rule neutralising a table cell's code chip")
	}
	var bodies []string
	for _, match := range matches {
		bodies = append(bodies, match[1])
	}
	joined := strings.Join(bodies, "\n")
	if !strings.Contains(joined, "background: none") {
		t.Errorf("the chip keeps its background: %s", joined)
	}
	if !borderZeroRe.MatchString(joined) {
		t.Errorf("the chip keeps its border: %s", joined)
	}
	if !paddingZeroRe.MatchString(joined) {
		t.Errorf("the chip keeps its padding: %s", joined)
	}
}

func TestProseKeepsItsChip(t *testing.T) {
	// The neutralisation is scoped; a paragraph's chip is untouched.
	css := mustCSS(t, "tinymoon")
	match := proseChipRe.FindStringSubmatch(css)
	if match == nil {
		t.Fatal("the framework's prose chip rule is gone entirely")
	}
	if !strings.Contains(match[1], "background: var(--surface-2)") {
		t.Errorf("the prose chip lost its background: %s", match[1])
	}
}
