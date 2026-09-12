//go:build e2e

package e2e

import (
	"testing"

	"github.com/playwright-community/playwright-go"
)

// TestThemeToggle asserts light and dark are what the browser paints, not what
// localStorage says.
func TestThemeToggle(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		t.Run("toggling changes the painted background", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "docs")
			toggle := page.Locator(".theme-toggle").First()
			if err := toggle.WaitFor(playwright.LocatorWaitForOptions{
				State: playwright.WaitForSelectorStateVisible,
			}); err != nil {
				t.Fatalf("[%s] the theme toggle never became visible: %v", fixture.Theme, err)
			}

			seen := map[string]string{}
			for i := 0; i < 3; i++ {
				state, _ := evalString(t, page,
					"() => document.querySelector('.theme-toggle')"+
						".getAttribute('data-state')")
				settleAnimations(t, page)
				background, _ := evalString(t, page,
					"() => getComputedStyle(document.body).backgroundColor")
				seen[state] = background
				if err := toggle.Click(); err != nil {
					t.Fatalf("clicking the theme toggle: %v", err)
				}
				page.WaitForTimeout(80)
			}

			states := sortedStrings(keysOf(seen))
			if len(states) != 3 || states[0] != "dark" || states[1] != "light" || states[2] != "system" {
				t.Fatalf("[%s] the toggle cycled through %v", fixture.Theme, states)
			}
			if seen["light"] == seen["dark"] {
				t.Errorf("[%s] light and dark paint the same body background: %v",
					fixture.Theme, seen)
			}
		})

		t.Run("the choice survives a reload", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "docs")
			eval(t, page, "() => localStorage.setItem('selfdoc-theme', 'dark')")
			open(t, page, fixture, "docs")
			settleAnimations(t, page)
			attribute, _ := evalString(t, page,
				"() => document.documentElement.getAttribute('data-theme')")
			if attribute != "dark" {
				t.Errorf("[%s] a stored dark choice did not survive a reload (data-theme=%q)",
					fixture.Theme, attribute)
			}
		})

		t.Run("the resting state follows an emulated dark preference", func(t *testing.T) {
			// With no stored choice, a dark preference must reach the page.
			//
			// tinymoon is a dark theme, so its resting state under a dark
			// preference has to be dark; the other two are asserted for the
			// weaker property that nothing pins data-theme behind the reader's
			// back.
			page := newPageWith(t, playwright.BrowserNewContextOptions{
				Viewport:    &playwright.Size{Width: 1280, Height: 900},
				ColorScheme: playwright.ColorSchemeDark,
			})
			gotoPath(t, page, fixture.Assembly, AssemblyPages["docs"], "docs")
			settleAnimations(t, page)
			reading := evalMap(t, page, `() => {
                const s = getComputedStyle(document.body);
                const rgb = s.backgroundColor.match(/\d+/g).map(Number);
                return {
                    background: s.backgroundColor,
                    luminance: (0.299*rgb[0] + 0.587*rgb[1] + 0.114*rgb[2]) / 255,
                    attr: document.documentElement.getAttribute('data-theme'),
                };
            }`)
			if reading["attr"] != nil {
				t.Errorf("[%s] the page pinned data-theme=%v with no stored choice; the "+
					"resting state must follow the reader's preference",
					fixture.Theme, reading["attr"])
			}
			if fixture.Theme == "tinymoon" {
				if luminance := mapFloat(t, reading, "luminance"); luminance >= 0.5 {
					t.Errorf("[%s] with a dark preference emulated, tinymoon rests light: %v",
						fixture.Theme, reading)
				}
			}
		})
	})
}

// keysOf returns a map's keys.
func keysOf(values map[string]string) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	return keys
}
