//go:build e2e

package e2e

import "testing"

// tocReading is what one width painted of the two table-of-contents variants.
type tocReading struct {
	width   int
	desktop int
	mobile  int
}

// TestTableOfContents stands for defect 2: a table of contents visible only
// inside a band of viewport widths.
//
// The desktop aside and the mobile disclosure are the same feature at two
// widths. Suppressing only one of them left a table of contents that appeared
// below 1280px and nowhere else, which no unit test could see: both elements
// were in the HTML either way.
func TestTableOfContents(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		for _, label := range TOCPages {
			t.Run("exactly one variant is visible at every width on "+label, func(t *testing.T) {
				// Wide or narrow, one variant shows -- never both, never neither.
				page := newPage(t)
				open(t, page, fixture, label)
				var seen []tocReading
				for _, width := range Widths {
					setViewport(t, page, width, 900, 60)
					seen = append(seen, tocReading{
						width:   width,
						desktop: visibleCount(t, page, "nav.docs-toc"),
						mobile:  visibleCount(t, page, "details.mobile-toc"),
					})
				}
				var missing, doubled []int
				for _, reading := range seen {
					if reading.desktop+reading.mobile == 0 {
						missing = append(missing, reading.width)
					}
					if reading.desktop > 0 && reading.mobile > 0 {
						doubled = append(doubled, reading.width)
					}
				}
				if len(missing) > 0 {
					t.Errorf("[%s] %s showed no table of contents at %v -- the readings "+
						"were %v", fixture.Theme, label, missing, seen)
				}
				if len(doubled) > 0 {
					t.Errorf("[%s] %s showed both the desktop aside and the mobile "+
						"disclosure at %v -- the readings were %v",
						fixture.Theme, label, doubled, seen)
				}
			})

			t.Run("the aside is the wide variant and the disclosure the narrow one on "+label, func(t *testing.T) {
				page := newPage(t)
				open(t, page, fixture, label)
				setViewport(t, page, 1920, 900, 60)
				if count := visibleCount(t, page, "nav.docs-toc"); count != 1 {
					t.Errorf("[%s] %s has no desktop table of contents at 1920px (%d visible)",
						fixture.Theme, label, count)
				}
				setViewport(t, page, 700, 900, 60)
				if count := visibleCount(t, page, "nav.docs-toc"); count != 0 {
					t.Errorf("[%s] %s still shows the desktop aside at 700px (%d visible)",
						fixture.Theme, label, count)
				}
				if count := visibleCount(t, page, "details.mobile-toc"); count != 1 {
					t.Errorf("[%s] %s has no mobile table of contents at 700px (%d visible)",
						fixture.Theme, label, count)
				}
			})
		}

		t.Run("a post has no table of contents at any width", func(t *testing.T) {
			// A post carries neither variant at any width -- the whole of defect 2.
			page := newPage(t)
			open(t, page, fixture, "post")
			var offenders []tocReading
			for _, width := range Widths {
				setViewport(t, page, width, 900, 60)
				desktop := visibleCount(t, page, "nav.docs-toc")
				mobile := visibleCount(t, page, "details.mobile-toc")
				if desktop > 0 || mobile > 0 {
					offenders = append(offenders, tocReading{width, desktop, mobile})
				}
			}
			if len(offenders) > 0 {
				t.Errorf("[%s] a post rendered a table of contents at %v",
					fixture.Theme, offenders)
			}
		})

		t.Run("a post carries no toc element in the dom at all", func(t *testing.T) {
			// Not merely hidden: a post's HTML has no table-of-contents
			// element. Hiding one variant with CSS at one breakpoint is
			// exactly how the band-limited table of contents came about.
			page := newPage(t)
			open(t, page, fixture, "post")
			present := evalInt(t, page,
				"() => document.querySelectorAll('nav.docs-toc, details.mobile-toc').length")
			if present != 0 {
				t.Errorf("[%s] a post carries %d table-of-contents element(s) in its DOM",
					fixture.Theme, present)
			}
		})
	})
}
