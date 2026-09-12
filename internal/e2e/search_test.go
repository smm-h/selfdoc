//go:build e2e

package e2e

import (
	"sync"
	"testing"

	"github.com/playwright-community/playwright-go"
)

// TestSearch drives the search overlay the way a reader drives it.
//
// Pagefind really ran over the fixture tree in the session fixture, so the
// index the overlay queries is the index a deploy would ship.
func TestSearch(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		t.Run("ctrl-k opens the overlay", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "docs")
			surface := surfaceOf(t, fixture)
			if count := visibleCount(t, page, surface.overlay); count != 0 {
				t.Fatalf("[%s] the overlay is already painted before anything opened it "+
					"(%d visible)", fixture.Theme, count)
			}
			openSearch(t, page, fixture)
			if count := visibleCount(t, page, surface.overlay); count != 1 {
				t.Errorf("[%s] the overlay opened but paints nothing (%d visible)",
					fixture.Theme, count)
			}
		})

		t.Run("the trigger opens the overlay", func(t *testing.T) {
			// The topbar's magnifier is a control, not decoration.
			page := newPage(t)
			open(t, page, fixture, "docs")
			surface := surfaceOf(t, fixture)
			if err := page.Click(".search-trigger, .search-bar-trigger"); err != nil {
				t.Fatalf("clicking the search trigger: %v", err)
			}
			if _, err := page.WaitForSelector(surface.input,
				playwright.PageWaitForSelectorOptions{Timeout: playwright.Float(15000)}); err != nil {
				t.Fatalf("[%s] the search input never appeared: %v", fixture.Theme, err)
			}
			awaitOverlay(t, page, surface)
			if count := visibleCount(t, page, surface.overlay); count != 1 {
				t.Errorf("[%s] the trigger opened %d overlays", fixture.Theme, count)
			}
		})

		t.Run("escape closes the overlay", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "docs")
			surface := openSearch(t, page, fixture)
			if err := page.Keyboard().Press("Escape"); err != nil {
				t.Fatalf("pressing Escape: %v", err)
			}
			if _, err := page.WaitForSelector(surface.overlay,
				playwright.PageWaitForSelectorOptions{
					State:   playwright.WaitForSelectorStateHidden,
					Timeout: playwright.Float(5000),
				}); err != nil {
				t.Errorf("[%s] the overlay stayed open after Escape: %v", fixture.Theme, err)
			}
		})

		// One page class per depth the index can be addressed from. The depth
		// is the whole point: the bundle path used to be computed at build
		// time from the page's own hop, and a dynamic import resolves that hop
		// against the BUNDLE's URL instead -- so search worked at exactly the
		// depths where the two mistakes cancelled and silently returned
		// nothing everywhere else, the front page and every project landing
		// page included.
		for _, label := range []string{"home", "docs", "docs-tables", "post", "standalone-archive"} {
			t.Run("a query against the real index returns a result from "+label, func(t *testing.T) {
				page := newPage(t)
				open(t, page, fixture, label)
				waitForNetworkIdle(t, page)
				var mu sync.Mutex
				var failures []string
				page.OnConsole(func(message playwright.ConsoleMessage) {
					if message.Type() == "error" {
						mu.Lock()
						failures = append(failures, message.Text())
						mu.Unlock()
					}
				})
				surface := openSearch(t, page, fixture)
				if err := page.Fill(surface.input, "fixture"); err != nil {
					t.Fatalf("typing into the search input: %v", err)
				}
				if _, err := page.WaitForSelector(surface.result,
					playwright.PageWaitForSelectorOptions{Timeout: playwright.Float(20000)}); err != nil {
					mu.Lock()
					logged := append([]string(nil), failures...)
					mu.Unlock()
					t.Fatalf("[%s] searching from %s returned nothing for a word the "+
						"fixture content certainly carries. Console: %v",
						fixture.Theme, label, first(logged, 3))
				}
				count, err := page.Locator(surface.result).Count()
				if err != nil {
					t.Fatalf("counting the results: %v", err)
				}
				if count < 1 {
					t.Errorf("[%s] searching from %s painted no result", fixture.Theme, label)
				}
				mu.Lock()
				logged := append([]string(nil), failures...)
				mu.Unlock()
				if len(logged) > 0 {
					t.Errorf("[%s] the search on %s logged errors: %v",
						fixture.Theme, label, first(logged, 3))
				}
			})
		}

		t.Run("the facets render", func(t *testing.T) {
			// The build declares filter facets; the widget has to offer them.
			//
			// Only the widget: the framework's palette is a ranked list with
			// no filter surface, so a framework theme's search offers no
			// facets and this is the one capability the two surfaces do not
			// share. The facet elements are still emitted and still indexed --
			// what changes is that nothing on the page exposes them as
			// controls.
			if isFrameworkTheme(t, fixture.Theme) {
				t.Skip("the framework's palette offers no filter controls")
			}
			page := newPage(t)
			open(t, page, fixture, "docs")
			waitForNetworkIdle(t, page)
			surface := openSearch(t, page, fixture)
			if err := page.Fill(surface.input, "fixture"); err != nil {
				t.Fatalf("typing into the search input: %v", err)
			}
			if _, err := page.WaitForSelector(surface.result,
				playwright.PageWaitForSelectorOptions{Timeout: playwright.Float(20000)}); err != nil {
				t.Fatalf("[%s] the search returned nothing to read facets beside: %v",
					fixture.Theme, err)
			}
			facets, err := page.Locator(
				".pagefind-ui__filter-panel, .pagefind-ui__drawer, .pagefind-ui__filter-group").Count()
			if err != nil {
				t.Fatalf("counting the filter controls: %v", err)
			}
			if facets < 1 {
				t.Errorf("[%s] the search UI rendered no filter controls, though the build "+
					"declares facets for them to read", fixture.Theme)
			}
		})

		t.Run("a framework theme ships no pagefind widget", func(t *testing.T) {
			// Nothing loads it, so the deploy does not carry it.
			if !isFrameworkTheme(t, fixture.Theme) {
				t.Skip("this theme mounts the widget")
			}
			page := newPage(t)
			site, _ := served(fixture, "docs")
			for _, asset := range []string{"pagefind-ui.css", "pagefind-ui.js"} {
				response, err := page.Request().Get(site.url("/pagefind/" + asset))
				if err != nil {
					t.Fatalf("asking for %s: %v", asset, err)
				}
				if response.Status() < 400 {
					t.Errorf("[%s] %s is still served, though no page references it",
						fixture.Theme, asset)
				}
			}
			// The query API the palette calls is a different file, and stays.
			response, err := page.Request().Get(site.url("/pagefind/pagefind.js"))
			if err != nil {
				t.Fatalf("asking for pagefind.js: %v", err)
			}
			if !response.Ok() {
				t.Errorf("[%s] pagefind.js answered %d, but the palette queries through it",
					fixture.Theme, response.Status())
			}
		})
	})
}

// first returns at most n of the values, for a failure message.
func first(values []string, n int) []string {
	if len(values) > n {
		return values[:n]
	}
	return values
}
