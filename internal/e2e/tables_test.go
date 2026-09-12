//go:build e2e

package e2e

import (
	"fmt"
	"strings"
	"testing"

	"github.com/playwright-community/playwright-go"
)

// TableWidth is the width the table assertions run at. The fixture table
// overflows its wrapper here in every theme -- the fixture guard asserts
// exactly that, so none of these can pass by having nothing to scroll.
const TableWidth = 700

// tablePage opens the table-heavy page at the width the table assertions run
// at and returns its scrolling wrapper.
func tablePage(t *testing.T, page playwright.Page, fixture *Fixture) playwright.Locator {
	t.Helper()
	open(t, page, fixture, "docs-tables")
	setViewport(t, page, TableWidth, 900, 80)
	// The narrow viewport sends the sidebar drawer off-canvas as a CSS
	// transition, and a geometry reading taken mid-flight is a reading of a
	// layout no reader ever sees: the drawer is still half over the content
	// column. Every assertion here is about the layout at rest.
	settleAnimations(t, page)
	wrap := page.Locator(".table-wrap").First()
	if err := wrap.WaitFor(playwright.LocatorWaitForOptions{
		State: playwright.WaitForSelectorStateVisible,
	}); err != nil {
		t.Fatalf("[%s] the table wrapper never became visible: %v", fixture.Theme, err)
	}
	return wrap
}

// TestStickyTables stands for defect 1: a sticky thead that overlapped the
// first data row.
//
// The header sticks against the table's own scrolling box (.table-wrap) rather
// than against the viewport -- the offset it used to carry was a topbar's
// height, which pushed it down over the first body rows. The only way to see
// that is to scroll the box and the page and measure what the browser painted.
func TestStickyTables(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		t.Run("the header never covers the first row", func(t *testing.T) {
			page := newPage(t)
			wrap := tablePage(t, page, fixture)
			head := page.Locator(".table-wrap thead tr").First()
			firstRow := page.Locator(".table-wrap tbody tr").First()

			var overlaps []string
			for _, boxTop := range []int{0, 60, 200, 600} {
				for _, pageTop := range []int{0, 120, 400, 900} {
					if _, err := wrap.Evaluate("(el, t) => { el.scrollTop = t; }", boxTop); err != nil {
						t.Fatalf("scrolling the table box: %v", err)
					}
					scrollPageTo(t, page, pageTop)
					headBox, err := head.BoundingBox()
					if err != nil {
						t.Fatalf("reading the header box: %v", err)
					}
					rowBox, err := firstRow.BoundingBox()
					if err != nil {
						t.Fatalf("reading the first row's box: %v", err)
					}
					if boxesIntersect(headBox, rowBox, 0.5) {
						overlaps = append(overlaps, fmt.Sprintf(
							"(box=%d, page=%d) head=%v row=%v", boxTop, pageTop, headBox, rowBox))
					}
				}
			}
			if len(overlaps) > 0 {
				t.Errorf("[%s] the sticky table header overlapped the first data row at "+
					"(box, page) scroll offsets: %s", fixture.Theme, strings.Join(overlaps, "; "))
			}
		})

		t.Run("the header cells stay over their columns when scrolled sideways", func(t *testing.T) {
			// A header that does not travel with its column is unreadable.
			page := newPage(t)
			wrap := tablePage(t, page, fixture)
			value, err := wrap.Evaluate(`(el) => {
                const col = 4;
                const head = el.querySelector(
                    `+"`thead tr th:nth-child(${col})`"+`);
                const cell = el.querySelector(
                    `+"`tbody tr td:nth-child(${col})`"+`);
                el.scrollLeft = 0;
                const before = head.getBoundingClientRect().x
                             - cell.getBoundingClientRect().x;
                el.scrollLeft = Math.floor(
                    (el.scrollWidth - el.clientWidth) / 2);
                const after = head.getBoundingClientRect().x
                            - cell.getBoundingClientRect().x;
                return {before, after, scrolled: el.scrollLeft};
            }`, nil)
			if err != nil {
				t.Fatalf("measuring the header drift: %v", err)
			}
			drift := value.(map[string]any)
			if delta := mapFloat(t, drift, "after") - mapFloat(t, drift, "before"); delta > 1 || delta < -1 {
				t.Errorf("[%s] a header cell drifted %v away from the column it labels "+
					"when the table scrolled sideways", fixture.Theme, drift)
			}
		})

		t.Run("the pinned first column stays on top when scrolled sideways", func(t *testing.T) {
			// A sticky first column is SUPPOSED to have the rest of the row
			// slide under it; that is the feature. What must not happen is the
			// row painting over the pinned cell, which is the same defect as
			// the sticky header overlap read along the other axis. So the
			// assertion is on paint order at the cell's own centre, not on
			// geometry.
			page := newPage(t)
			wrap := tablePage(t, page, fixture)
			if _, err := wrap.Evaluate("(el) => { el.scrollLeft = el.scrollWidth; }", nil); err != nil {
				t.Fatalf("scrolling the table fully sideways: %v", err)
			}
			page.WaitForTimeout(80)
			topmost := evalMap(t, page, `() => {
                const cell = document.querySelector(
                    '.table-wrap tbody tr td:first-child');
                const box = cell.getBoundingClientRect();
                const hit = document.elementFromPoint(
                    box.x + box.width / 2, box.y + box.height / 2);
                return {
                    inside: !!hit && (hit === cell || cell.contains(hit)),
                    hit: hit ? hit.className || hit.tagName : null,
                    detail: hit ? hit.outerHTML.slice(0, 160) : null,
                    where: JSON.stringify(box),
                };
            }`)
			if !mapBool(topmost, "inside") {
				t.Errorf("[%s] with the table scrolled fully sideways, the element painted "+
					"at the centre of the first column's cell (%s) is %q -- another column "+
					"is covering it: %s", fixture.Theme, mapString(topmost, "where"),
					mapString(topmost, "hit"), mapString(topmost, "detail"))
			}
		})

		t.Run("the pinned header keeps the sort indicator every column has", func(t *testing.T) {
			// One ::after per element, and the pinned edge was taking it.
			//
			// Every header cell is emitted with aria-sort, and the sort
			// indicator is painted on th[aria-sort]::after. The pinned
			// column's scroll-edge hairline claimed the same pseudo-element on
			// th:first-child, so the first column silently lost its indicator
			// -- invisible to CSS string assertions, and visible in a
			// screenshot as one header that is missing what every other header
			// has. The reading is comparative on purpose: it is theme-agnostic
			// and it outlives any restyling of the indicator itself.
			page := newPage(t)
			wrap := tablePage(t, page, fixture)
			value, err := wrap.Evaluate(`(el) => {
                const heads = el.querySelectorAll('thead tr th');
                const first = heads[0], other = heads[1];
                // The unsorted state is the one the server emits; a theme may
                // paint nothing for it, so read a sorted one, which every
                // theme indicates.
                for (const th of [first, other])
                    th.setAttribute('aria-sort', 'ascending');
                const read = (th) => {
                    const s = getComputedStyle(th, '::after');
                    return {
                        content: s.content,
                        width: s.width,
                        height: s.height,
                        position: s.position,
                        borderBottom: s.borderBottomWidth + ' '
                                    + s.borderBottomColor,
                        background: s.backgroundColor,
                    };
                };
                return {first: read(first), other: read(other)};
            }`, nil)
			if err != nil {
				t.Fatalf("reading the header pseudo-elements: %v", err)
			}
			reading := value.(map[string]any)
			first := fmt.Sprintf("%v", reading["first"])
			other := fmt.Sprintf("%v", reading["other"])
			if first != other {
				t.Errorf("[%s] the pinned first column's header paints a different ::after "+
					"than its neighbour, so its sort indicator is gone: first=%s other=%s",
					fixture.Theme, first, other)
			}
		})
	})
}

// TestTableCellsAreNotChips asserts a data table whose every cell is a bordered
// code chip is noise.
//
// The framework's prose sheet boxes an unclassed "code" -- background, border,
// padding -- which is right in a sentence and wrong in a grid where every cell
// is one. The theme overlay neutralises the box inside .tm-table and nowhere
// else, so the two assertions here are a pair: the cell is plain, the paragraph
// still has its chip.
//
// Skipped for a theme that ships no framework payload: the chip those themes
// paint is their own decision, not the overlay's to undo.
func TestTableCellsAreNotChips(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		if !isFrameworkTheme(t, fixture.Theme) {
			t.Skipf("%s ships no framework payload", fixture.Theme)
		}

		t.Run("a code span in a cell paints no box", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "docs-tables")
			reading := evalMap(t, page, `() => {
                const code = document.querySelector(
                    '.table-wrap tbody td code');
                const s = getComputedStyle(code);
                return {
                    border: s.borderTopWidth,
                    background: s.backgroundColor,
                    padding: s.paddingTop + ' ' + s.paddingLeft,
                    family: s.fontFamily,
                };
            }`)
			if mapString(reading, "border") != "0px" {
				t.Errorf("[%s] a table cell's code span still draws a border: %v",
					fixture.Theme, reading)
			}
			background := mapString(reading, "background")
			if background != "rgba(0, 0, 0, 0)" && background != "transparent" {
				t.Errorf("[%s] a table cell's code span still fills a background: %v",
					fixture.Theme, reading)
			}
			if mapString(reading, "padding") != "0px 0px" {
				t.Errorf("[%s] a table cell's code span still pads its box: %v",
					fixture.Theme, reading)
			}
			if !strings.Contains(strings.ToLower(mapString(reading, "family")), "mono") {
				t.Errorf("[%s] a table cell's code span lost its monospace face along "+
					"with the box: %v", fixture.Theme, reading)
			}
		})

		t.Run("a code span in prose keeps its box", func(t *testing.T) {
			// The other half: the fix is scoped to the table, not global.
			page := newPage(t)
			open(t, page, fixture, "docs-tables")
			reading := evalMap(t, page, `() => {
                const code = document.querySelector('.doc-body p code');
                if (!code) return {missing: true};
                const s = getComputedStyle(code);
                return {
                    border: s.borderTopWidth,
                    background: s.backgroundColor,
                };
            }`)
			if mapBool(reading, "missing") {
				t.Fatalf("[%s] the fixture page has no prose code span to read, so the "+
					"scoping cannot be measured", fixture.Theme)
			}
			if mapString(reading, "border") == "0px" {
				t.Errorf("[%s] prose lost its code chip too: %v", fixture.Theme, reading)
			}
		})
	})
}
