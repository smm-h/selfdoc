//go:build e2e

package e2e

import (
	"sort"
	"strings"
	"testing"

	"github.com/playwright-community/playwright-go"
)

// TestVersionUI asserts the archive notice, its dismissal, the picker, and the
// unversioned case.
//
// Asserted against the standalone site, because that is the tree that carries
// an archive: an assembly build takes the latest version, so an assembled
// subtree publishes the current version and nothing else.
func TestVersionUI(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		t.Run("the archive page shows the superseded notice", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "standalone-archive")
			notice := page.Locator(".tm-notice")
			count, err := notice.Count()
			if err != nil {
				t.Fatalf("counting the notices: %v", err)
			}
			if count != 1 {
				t.Fatalf("[%s] an archive page carries %d superseded notices",
					fixture.Theme, count)
			}
			visible, err := notice.First().IsVisible()
			if err != nil {
				t.Fatalf("reading the notice's visibility: %v", err)
			}
			if !visible {
				t.Fatalf("[%s] the superseded notice is in the DOM but is not painted",
					fixture.Theme)
			}
			text, err := notice.First().InnerText()
			if err != nil {
				t.Fatalf("reading the notice: %v", err)
			}
			if !strings.Contains(text, "0.1.0") {
				t.Errorf("[%s] the superseded notice does not name the version it is on: %q",
					fixture.Theme, text)
			}
		})

		t.Run("the current version shows no notice", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "standalone-current")
			count, err := page.Locator(".tm-notice").Count()
			if err != nil {
				t.Fatalf("counting the notices: %v", err)
			}
			if count != 0 {
				t.Errorf("[%s] the current version claims to be superseded", fixture.Theme)
			}
		})

		t.Run("dismissing the notice persists across a reload", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "standalone-archive")
			eval(t, page, "() => localStorage.clear()")
			open(t, page, fixture, "standalone-archive")
			notice := page.Locator(".tm-notice")
			if visible, err := notice.First().IsVisible(); err != nil || !visible {
				t.Fatalf("[%s] the notice is not painted before Dismiss (err=%v)",
					fixture.Theme, err)
			}
			if err := page.Locator(".tm-notice-dismiss").First().Click(); err != nil {
				t.Fatalf("clicking Dismiss: %v", err)
			}
			if visible, err := notice.First().IsVisible(); err != nil || visible {
				t.Errorf("[%s] the notice stayed visible after Dismiss (err=%v)",
					fixture.Theme, err)
			}

			open(t, page, fixture, "standalone-archive")
			if visible, err := page.Locator(".tm-notice").First().IsVisible(); err != nil || visible {
				t.Errorf("[%s] the dismissal did not survive a reload (err=%v)",
					fixture.Theme, err)
			}
		})

		t.Run("the notice links back to the current version", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "standalone-archive")
			eval(t, page, "() => localStorage.clear()")
			open(t, page, fixture, "standalone-archive")
			if err := page.Locator(".tm-notice a").First().Click(); err != nil {
				t.Fatalf("clicking the notice's link: %v", err)
			}
			if err := page.WaitForLoadState(playwright.PageWaitForLoadStateOptions{
				State: playwright.LoadStateLoad,
			}); err != nil {
				t.Fatalf("waiting for the linked page: %v", err)
			}
			count, err := page.Locator(".tm-notice").Count()
			if err != nil {
				t.Fatalf("counting the notices: %v", err)
			}
			if count != 0 {
				t.Errorf("[%s] the notice's link went to %s, which also claims to be "+
					"superseded", fixture.Theme, page.URL())
			}
		})

		t.Run("every version the picker offers resolves", func(t *testing.T) {
			page := newPage(t)
			site := open(t, page, fixture, "standalone-current")
			pickers, err := page.Locator(".version-picker").Count()
			if err != nil {
				t.Fatalf("counting the pickers: %v", err)
			}
			if pickers != 1 {
				t.Fatalf("[%s] a versioned page has %d version pickers", fixture.Theme, pickers)
			}
			raw := eval(t, page, `() => Array.from(
                document.querySelectorAll('.version-picker .sel-opt')
            ).map(o => ({value: o.dataset.value, href: o.dataset.href}))`)
			options, ok := raw.([]any)
			if !ok {
				t.Fatalf("[%s] the picker answered %#v", fixture.Theme, raw)
			}
			var values []string
			for _, item := range options {
				option := item.(map[string]any)
				values = append(values, mapString(option, "value"))
			}
			sort.Strings(values)
			if strings.Join(values, ",") != "0.1.0,0.2.0" {
				t.Fatalf("[%s] the picker offers %v", fixture.Theme, options)
			}
			for _, item := range options {
				option := item.(map[string]any)
				resolved, _ := evalString(t, page,
					"(href) => new URL(href, location.href).href", mapString(option, "href"))
				if !strings.HasPrefix(resolved, site.origin()) {
					t.Errorf("[%s] the picker sends v%s off the origin, to %s",
						fixture.Theme, mapString(option, "value"), resolved)
					continue
				}
				response, err := page.Request().Head(resolved)
				if err != nil {
					t.Fatalf("asking for %s: %v", resolved, err)
				}
				if response.Status() >= 400 {
					t.Errorf("[%s] the picker offers v%s at %s, which answers %d",
						fixture.Theme, mapString(option, "value"), resolved, response.Status())
				}
			}
		})

		t.Run("an unversioned project shows no version ui", func(t *testing.T) {
			// Version chrome must not leak onto a project that declares none.
			page := newPage(t)
			open(t, page, fixture, "docs-unversioned")
			readings := map[string]int{}
			for name, selector := range map[string]string{
				"badge": ".version-badge", "picker": ".version-picker", "notice": ".tm-notice",
			} {
				count, err := page.Locator(selector).Count()
				if err != nil {
					t.Fatalf("counting %s: %v", selector, err)
				}
				readings[name] = count
			}
			if readings["badge"] != 0 || readings["picker"] != 0 || readings["notice"] != 0 {
				t.Errorf("[%s] an unversioned project's page carries version chrome: %v",
					fixture.Theme, readings)
			}
		})

		t.Run("an assembled page offers no picker it cannot honour", func(t *testing.T) {
			// The assembly publishes one version, so it must offer no other.
			//
			// A picker on an assembled page would name v/<older>/ addresses
			// the assembled site does not serve -- dead links by construction.
			page := newPage(t)
			open(t, page, fixture, "docs")
			pickers, err := page.Locator(".version-picker").Count()
			if err != nil {
				t.Fatalf("counting the pickers: %v", err)
			}
			if pickers != 0 {
				t.Errorf("[%s] the assembled page offers a version picker, but the "+
					"assembly publishes only the current version", fixture.Theme)
			}
			badges, err := page.Locator(".version-badge").Count()
			if err != nil {
				t.Fatalf("counting the badges: %v", err)
			}
			if badges != 1 {
				t.Errorf("[%s] the assembled page of a versioned project carries %d "+
					"version badges", fixture.Theme, badges)
			}
		})
	})
}
