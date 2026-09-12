//go:build e2e

package e2e

import "testing"

// TestOneLastUpdated stands for defect 4: a page that rendered its "Last
// updated" element twice.
func TestOneLastUpdated(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		for _, label := range AllPages {
			t.Run("at most one on "+label, func(t *testing.T) {
				// No page paints two "Last updated" elements.
				page := newPage(t)
				open(t, page, fixture, label)
				painted := evalStrings(t, page, `() => Array.from(
                        document.querySelectorAll('.page-meta span, .cv-updated'))
                    .filter(el => /last updated/i.test(el.textContent || ''))
                    .filter(el => {
                        const s = getComputedStyle(el);
                        return s.display !== 'none' && s.visibility !== 'hidden';
                    })
                    .map(el => (el.textContent || '').trim())`)
				if len(painted) > 1 {
					t.Errorf("[%s] %s painted %d 'Last updated' elements: %v",
						fixture.Theme, label, len(painted), painted)
				}
			})
		}

		t.Run("a documentation page shows exactly one", func(t *testing.T) {
			// A page with a date shows it once -- not zero times, not twice.
			page := newPage(t)
			open(t, page, fixture, "docs")
			painted := evalInt(t, page, `() => Array.from(
                    document.querySelectorAll('.page-meta span'))
                .filter(el => /last updated/i.test(el.textContent || '')).length`)
			if painted != 1 {
				t.Errorf("[%s] a documentation page painted %d 'Last updated' "+
					"elements; exactly one is right", fixture.Theme, painted)
			}
		})
	})
}
