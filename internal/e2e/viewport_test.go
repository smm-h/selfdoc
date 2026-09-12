//go:build e2e

package e2e

import (
	"fmt"
	"sort"
	"strings"
	"testing"
)

// layoutElements are the major layout elements the band guard reads.
var layoutElements = map[string]string{
	"topbar":         "#tm-topbar",
	"sidebar":        "#tm-sidebar",
	"desktop-toc":    "nav.docs-toc",
	"mobile-toc":     "details.mobile-toc",
	"footer":         ".site-footer, footer.page-footer",
	"search-trigger": ".search-trigger",
}

// TestViewportMonotonicity is defect 2, generalized: an element visible only
// inside a middle band.
//
// For each page class, the set of visible major layout elements must be a
// monotone function of viewport width -- the run of widths at which an element
// is visible has to touch one end of the sweep and have no gaps in it. An
// element that appears, disappears and reappears, or that is visible only in
// the middle, is two breakpoints disagreeing.
func TestViewportMonotonicity(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		for _, label := range AllPages {
			t.Run("visibility is monotone in viewport width on "+label, func(t *testing.T) {
				page := newPage(t)
				open(t, page, fixture, label)
				readings := map[int]map[string]bool{}
				for _, width := range Widths {
					setViewport(t, page, width, 900, 60)
					row := map[string]bool{}
					for name, selector := range layoutElements {
						row[name] = visibleCount(t, page, selector) > 0
					}
					readings[width] = row
				}

				var bands []string
				for _, name := range sortedStrings(keysOfBool(layoutElements)) {
					series := make([]bool, len(Widths))
					for index, width := range Widths {
						series[index] = readings[width][name]
					}
					firstTrue, lastTrue := -1, -1
					for index, value := range series {
						if value {
							if firstTrue < 0 {
								firstTrue = index
							}
							lastTrue = index
						}
					}
					if firstTrue < 0 {
						continue
					}
					interior := firstTrue > 0 && lastTrue < len(series)-1
					gaps := false
					for _, value := range series[firstTrue : lastTrue+1] {
						if !value {
							gaps = true
						}
					}
					if interior || gaps {
						bands = append(bands, fmt.Sprintf("%s=%s", name, describeSeries(series)))
					}
				}
				if len(bands) > 0 {
					t.Errorf("[%s] %s: element(s) visible only inside a band of viewport "+
						"widths, never at either end -- the signature of two breakpoints "+
						"that disagree: %s", fixture.Theme, label, strings.Join(bands, " "))
				}
			})

			t.Run("nothing on "+label+" overflows the viewport horizontally", func(t *testing.T) {
				// A page that scrolls sideways at any width is a layout defect.
				page := newPage(t)
				open(t, page, fixture, label)
				offenders := map[int]int{}
				for _, width := range Widths {
					setViewport(t, page, width, 900, 60)
					overflow := evalInt(t, page,
						"() => document.documentElement.scrollWidth - "+
							"document.documentElement.clientWidth")
					if overflow > 1 {
						offenders[width] = overflow
					}
				}
				if len(offenders) > 0 {
					t.Errorf("[%s] %s overflows horizontally by %v px",
						fixture.Theme, label, offenders)
				}
			})
		}
	})
}

// describeSeries renders one element's visibility across the swept widths.
func describeSeries(series []bool) string {
	parts := make([]string, 0, len(series))
	for index, value := range series {
		parts = append(parts, fmt.Sprintf("%d:%t", Widths[index], value))
	}
	return "{" + strings.Join(parts, " ") + "}"
}

// keysOfBool returns a selector map's element names.
func keysOfBool(values map[string]string) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
