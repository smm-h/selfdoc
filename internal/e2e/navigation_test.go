//go:build e2e

package e2e

import (
	"sort"
	"strconv"
	"strings"
	"testing"
)

// TestOnOriginNavigation stands for defect 5: absolute links that walked the
// reader off the site.
//
// A link written against the deployed base is right in the HTML and wrong in
// the browser -- it leaves the origin being served. The only way to see it is
// to resolve every href a reader can click.
func TestOnOriginNavigation(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		t.Run("every visible link stays on this origin", func(t *testing.T) {
			page := newPage(t)
			offenders := map[string][]string{}
			for _, label := range AllPages {
				site := open(t, page, fixture, label)
				hrefs := evalStrings(t, page, `() => Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const s = getComputedStyle(a);
                        if (s.display === 'none' || s.visibility === 'hidden') return false;
                        const box = a.getBoundingClientRect();
                        return box.width > 0 || box.height > 0;
                    })
                    .map(a => a.href)`)
				for _, href := range uniqueSorted(hrefs) {
					if strings.HasPrefix(href, "mailto:") ||
						strings.HasPrefix(href, "tel:") ||
						strings.HasPrefix(href, "javascript:") {
						continue
					}
					if allowedExternals[strings.TrimRight(strings.SplitN(href, "#", 2)[0], "/")] {
						continue
					}
					if !strings.HasPrefix(href, site.origin()) {
						offenders[label] = append(offenders[label], href)
					}
				}
			}
			if len(offenders) > 0 {
				declared := []string{}
				for url := range ExternalAllowlist {
					declared = append(declared, url)
				}
				sort.Strings(declared)
				t.Errorf("[%s] links leave the origin being served. The fixture declares "+
					"its off-origin addresses one by one (%s); everything else has to stay "+
					"local: %v", fixture.Theme, strings.Join(declared, ", "), offenders)
			}
		})

		t.Run("every on-origin link resolves to a page", func(t *testing.T) {
			// A same-origin link that answers 404 is a dead link a reader will hit.
			page := newPage(t)
			dead := map[string][]string{}
			for _, label := range AllPages {
				site := open(t, page, fixture, label)
				hrefs := evalStrings(t, page, `() => Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const s = getComputedStyle(a);
                        return s.display !== 'none' && s.visibility !== 'hidden';
                    })
                    .map(a => a.href)`)
				for _, href := range uniqueSorted(hrefs) {
					if !strings.HasPrefix(href, site.origin()) {
						continue
					}
					target := strings.SplitN(href, "#", 2)[0]
					response, err := page.Request().Head(target)
					if err != nil {
						t.Fatalf("[%s] asking for %s: %v", fixture.Theme, target, err)
					}
					if response.Status() >= 400 {
						dead[label] = append(dead[label],
							target+" -> "+strconv.Itoa(response.Status()))
					}
				}
			}
			if len(dead) > 0 {
				t.Errorf("[%s] dead same-origin links: %v", fixture.Theme, dead)
			}
		})
	})
}

// uniqueSorted returns the distinct values, sorted.
func uniqueSorted(values []string) []string {
	seen := map[string]bool{}
	out := []string{}
	for _, value := range values {
		if !seen[value] {
			seen[value] = true
			out = append(out, value)
		}
	}
	sort.Strings(out)
	return out
}
