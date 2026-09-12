//go:build e2e

package e2e

import (
	"strings"
	"testing"

	"github.com/playwright-community/playwright-go"
)

// TestGlossary stands for defect 6: a glossary term no page had ever defined.
//
// A term exists only because an author declared it, and its Source link has to
// land on that declaration. Both halves are browser facts: the fragment must
// resolve to an element that is really in the viewport, and the definition site
// must be something a reader can act on.
func TestGlossary(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		t.Run("the glossary lists exactly the declared terms", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "docs-glossary")
			terms := evalStrings(t, page,
				"() => Array.from(document.querySelectorAll('.glossary dt dfn'))"+
					".map(el => el.textContent.trim())")
			if got := strings.Join(sortedStrings(terms), ","); got != "Anchor,Archive,Manifest" {
				t.Errorf("[%s] the glossary lists %v; the fixture declares exactly three "+
					"terms and nothing may invent a fourth", fixture.Theme, terms)
			}
		})

		t.Run("each source link lands on the element that defines the term", func(t *testing.T) {
			// Click Source; the target must exist and be scrolled into view.
			page := newPage(t)
			open(t, page, fixture, "docs-glossary")
			count, err := page.Locator(".glossary dd a").Count()
			if err != nil {
				t.Fatalf("counting the Source links: %v", err)
			}
			if count != 3 {
				t.Fatalf("[%s] %d Source link(s) for three terms", fixture.Theme, count)
			}

			for index := 0; index < count; index++ {
				open(t, page, fixture, "docs-glossary")
				link := page.Locator(".glossary dd a").Nth(index)
				href, err := link.GetAttribute("href")
				if err != nil {
					t.Fatalf("reading Source link %d: %v", index, err)
				}
				if !strings.Contains(href, "#") {
					t.Errorf("[%s] Source link %d carries no fragment: %s",
						fixture.Theme, index, href)
					continue
				}
				if err := link.Click(); err != nil {
					t.Fatalf("clicking Source link %d: %v", index, err)
				}
				if err := page.WaitForLoadState(playwright.PageWaitForLoadStateOptions{
					State: playwright.LoadStateLoad,
				}); err != nil {
					t.Fatalf("waiting for Source link %d's page: %v", index, err)
				}
				fragment, _ := evalString(t, page, "() => location.hash.slice(1)")
				if fragment == "" {
					t.Errorf("[%s] Source link %d went to %s with no fragment",
						fixture.Theme, index, page.URL())
					continue
				}
				target := page.Locator("#" + fragment)
				targets, err := target.Count()
				if err != nil {
					t.Fatalf("counting #%s: %v", fragment, err)
				}
				if targets != 1 {
					t.Errorf("[%s] %s carries no element #%s -- the Source link names a "+
						"definition site that is not there", fixture.Theme, page.URL(), fragment)
					continue
				}
				box, err := target.BoundingBox()
				if err != nil {
					t.Fatalf("reading the box of #%s: %v", fragment, err)
				}
				if box == nil || box.Height <= 0 {
					t.Errorf("[%s] #%s on %s has no box", fixture.Theme, fragment, page.URL())
					continue
				}
				viewport := page.ViewportSize()
				if box.Y < -1 || box.Y >= float64(viewport.Height) {
					t.Errorf("[%s] #%s on %s sits at y=%v in a %dpx viewport -- the browser "+
						"did not scroll the definition into view",
						fixture.Theme, fragment, page.URL(), box.Y, viewport.Height)
				}
			}
		})

		t.Run("the definition site offers something to act on", func(t *testing.T) {
			// The term on its own page is an affordance, not inert text.
			page := newPage(t)
			open(t, page, fixture, "docs-glossary")
			if err := page.Locator(".glossary dd a").First().Click(); err != nil {
				t.Fatalf("clicking the first Source link: %v", err)
			}
			if err := page.WaitForLoadState(playwright.PageWaitForLoadStateOptions{
				State: playwright.LoadStateLoad,
			}); err != nil {
				t.Fatalf("waiting for the definition page: %v", err)
			}
			fragment, _ := evalString(t, page, "() => location.hash.slice(1)")
			reading := evalMap(t, page, `(id) => {
                const el = document.getElementById(id);
                if (!el) return null;
                const scope = el.closest('dt, p, li') || el;
                const link = scope.querySelector('a[href]') ||
                             (el.tagName === 'A' ? el : null);
                if (!link) return {found: false, html: scope.outerHTML.slice(0, 300)};
                return {found: true, href: link.getAttribute('href'),
                        cursor: getComputedStyle(link).cursor};
            }`, fragment)
			if reading == nil {
				t.Fatalf("[%s] #%s does not exist on %s", fixture.Theme, fragment, page.URL())
			}
			if !mapBool(reading, "found") {
				t.Errorf("[%s] the definition site for #%s on %s offers nothing to click: %s",
					fixture.Theme, fragment, page.URL(), mapString(reading, "html"))
			}
		})
	})
}
