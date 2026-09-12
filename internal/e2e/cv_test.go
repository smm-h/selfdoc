//go:build e2e

package e2e

import (
	"testing"

	"github.com/playwright-community/playwright-go"
)

// TestCV asserts the CV page: a portrait that decodes, and a header laid out as
// a row.
func TestCV(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		t.Run("the photo renders", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "cv")
			if err := page.Locator(".cv-photo img").First().WaitFor(
				playwright.LocatorWaitForOptions{
					State: playwright.WaitForSelectorStateVisible,
				}); err != nil {
				t.Fatalf("[%s] the CV portrait never became visible: %v", fixture.Theme, err)
			}
			natural := evalMap(t, page, `() => {
                const img = document.querySelector('.cv-photo img');
                return {w: img.naturalWidth, h: img.naturalHeight,
                        src: img.currentSrc || img.src, complete: img.complete};
            }`)
			if !mapBool(natural, "complete") ||
				mapFloat(t, natural, "w") <= 0 || mapFloat(t, natural, "h") <= 0 {
				t.Errorf("[%s] the CV portrait did not decode: %v", fixture.Theme, natural)
			}
		})

		t.Run("the header block puts the photo beside the identity", func(t *testing.T) {
			// At desktop width the portrait and the identity share a row.
			page := newPage(t)
			open(t, page, fixture, "cv")
			setViewport(t, page, 1280, 900, 60)
			photo, err := page.Locator(".cv-photo").First().BoundingBox()
			if err != nil {
				t.Fatalf("reading the portrait's box: %v", err)
			}
			identity, err := page.Locator(".cv-identity").First().BoundingBox()
			if err != nil {
				t.Fatalf("reading the identity's box: %v", err)
			}
			if photo == nil || identity == nil {
				t.Fatalf("[%s] the CV header is missing a half: photo=%v identity=%v",
					fixture.Theme, photo, identity)
			}
			overlap := min(photo.Y+photo.Height, identity.Y+identity.Height) -
				max(photo.Y, identity.Y)
			if overlap <= 0 {
				t.Errorf("[%s] the CV photo and identity are stacked rather than in a row: "+
					"photo=%v identity=%v", fixture.Theme, photo, identity)
			}
			if identity.X < photo.X+photo.Width-1 {
				t.Errorf("[%s] the identity block is not beside the portrait: photo=%v "+
					"identity=%v", fixture.Theme, photo, identity)
			}
		})

		t.Run("the cv renders every declared section", func(t *testing.T) {
			page := newPage(t)
			open(t, page, fixture, "cv")
			headings := evalStrings(t, page,
				"() => Array.from(document.querySelectorAll('main h2'))"+
					".map(h => h.textContent.replace('#', '').trim())")
			for _, section := range []string{
				"Skills", "Projects", "Hobbies & interests", "Education",
				"Work experience", "Languages", "Contact information",
			} {
				if !contains(headings, section) {
					t.Errorf("[%s] the CV page has no %q section: %v",
						fixture.Theme, section, headings)
				}
			}
		})
	})
}

// contains reports whether values holds wanted.
func contains(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}
