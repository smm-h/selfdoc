//go:build e2e

package e2e

import (
	"fmt"
	"strings"
	"sync"
	"testing"

	"github.com/playwright-community/playwright-go"
)

// responseRecord is one response the page received, as the capture reads it.
type responseRecord struct {
	url    string
	status int
}

// String renders one captured response for a failure message.
func (r responseRecord) String() string {
	return fmt.Sprintf("%s -> %d", r.url, r.status)
}

// captureFailedStylesheets records every stylesheet response that answered 400
// or worse.
func captureFailedStylesheets(page playwright.Page) func() []responseRecord {
	var mu sync.Mutex
	var failures []responseRecord
	page.OnResponse(func(response playwright.Response) {
		isSheet := response.Request().ResourceType() == "stylesheet" ||
			strings.HasSuffix(response.URL(), ".css")
		if response.Status() >= 400 && isSheet {
			mu.Lock()
			failures = append(failures, responseRecord{response.URL(), response.Status()})
			mu.Unlock()
		}
	})
	return func() []responseRecord {
		mu.Lock()
		defer mu.Unlock()
		return append([]responseRecord(nil), failures...)
	}
}

// TestStylesApplied stands for defect 3: a shared page served with no
// stylesheet at all.
//
// The page was valid HTML with a <link> in it; the link named an address the
// assembled site does not carry. Only a browser that fetched it knows.
func TestStylesApplied(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		for _, label := range AllPages {
			t.Run("no stylesheet "+label+" names fails to load", func(t *testing.T) {
				// Network capture: every stylesheet request must succeed.
				page := newPage(t)
				failures := captureFailedStylesheets(page)
				open(t, page, fixture, label)
				waitForNetworkIdle(t, page)

				declared := evalStrings(t, page, `() => Array.from(
                    document.querySelectorAll('link[rel~="stylesheet"]')
                ).map(l => l.href)`)
				if len(declared) == 0 {
					t.Errorf("[%s] %s declares no stylesheet at all", fixture.Theme, label)
				}
				if found := failures(); len(found) > 0 {
					t.Errorf("[%s] %s names stylesheet(s) that do not resolve: %v",
						fixture.Theme, label, found)
				}
			})

			t.Run("the computed body style of "+label+" is not the browser default", func(t *testing.T) {
				// A page whose stylesheet never applied looks exactly like the
				// opposite of this.
				page := newPage(t)
				open(t, page, fixture, label)
				waitForNetworkIdle(t, page)
				computed := evalMap(t, page, `() => {
                    const s = getComputedStyle(document.body);
                    return {background: s.backgroundColor, font: s.fontFamily};
                }`)
				// An unstyled Chromium body is transparent and set in Times.
				background := mapString(computed, "background")
				if background == "rgba(0, 0, 0, 0)" || background == "" {
					t.Errorf("[%s] %s has a transparent body background -- its stylesheet "+
						"did not apply: %v", fixture.Theme, label, computed)
				}
				if strings.Contains(mapString(computed, "font"), "Times") {
					t.Errorf("[%s] %s renders in the browser's default serif -- its "+
						"stylesheet did not apply: %v", fixture.Theme, label, computed)
				}
			})
		}

		t.Run("the shared pages are styled like the project pages", func(t *testing.T) {
			// Defect 3 exactly.
			//
			// The shared generator writes projects/index.html and
			// blog/index.html itself, so they miss whatever the per-project
			// graft is responsible for -- including, once, the stylesheet.
			page := newPage(t)
			readings := map[string]string{}
			distinct := map[string]bool{}
			for _, label := range []string{"home", "docs", "shared-projects", "shared-blog"} {
				open(t, page, fixture, label)
				waitForNetworkIdle(t, page)
				background, _ := evalString(t, page,
					"() => getComputedStyle(document.body).backgroundColor")
				readings[label] = background
				distinct[background] = true
			}
			if len(distinct) != 1 {
				t.Errorf("[%s] the shared pages do not share the site's body background: %v",
					fixture.Theme, readings)
			}
		})
	})
}

// TestTheFrameworkPayloadIsServed asserts a theme may ship someone else's
// sheets and faces.
//
// The tinymoon theme stopped imitating the framework and started consuming it:
// the stylesheet is the framework's own bytes, and its @font-face rules
// address ../fonts/ relative to wherever that stylesheet was written. That is
// a whole class of defect a string assertion cannot see -- the CSS is
// byte-perfect and the fonts 404, the page renders in a fallback face, and
// every unit test passes.
//
// Skipped for a theme that ships no payload; there is nothing to serve.
func TestTheFrameworkPayloadIsServed(t *testing.T) {
	forEachTheme(t, func(t *testing.T, fixture *Fixture) {
		if !isFrameworkTheme(t, fixture.Theme) {
			t.Skipf("%s ships no framework payload", fixture.Theme)
		}

		for _, label := range AllPages {
			t.Run("every font "+label+" asks for arrives", func(t *testing.T) {
				// Network capture on the font requests, on both served trees.
				page := newPage(t)
				var mu sync.Mutex
				var seen []responseRecord
				page.OnResponse(func(response playwright.Response) {
					if response.Request().ResourceType() == "font" ||
						strings.HasSuffix(response.URL(), ".woff2") {
						mu.Lock()
						seen = append(seen, responseRecord{response.URL(), response.Status()})
						mu.Unlock()
					}
				})
				open(t, page, fixture, label)
				waitForNetworkIdle(t, page)
				// A font is fetched only when something on the page needs that
				// face, so an empty list is not a failure -- a failed fetch is.
				mu.Lock()
				var failed []responseRecord
				for _, record := range seen {
					if record.status >= 400 {
						failed = append(failed, record)
					}
				}
				mu.Unlock()
				if len(failed) > 0 {
					t.Errorf("[%s] %s asked for fonts that do not resolve: %v",
						fixture.Theme, label, failed)
				}
			})

			t.Run("nothing on "+label+" is fetched from off-origin", func(t *testing.T) {
				// The framework vendors everything; a CDN request means it did not.
				page := newPage(t)
				var mu sync.Mutex
				var offsite []string
				page.OnRequest(func(request playwright.Request) {
					url := request.URL()
					local := strings.HasPrefix(url, "http://127.0.0.1") ||
						strings.HasPrefix(url, "http://localhost") ||
						strings.HasPrefix(url, "data:") ||
						strings.HasPrefix(url, "blob:")
					if !local {
						mu.Lock()
						offsite = append(offsite, url)
						mu.Unlock()
					}
				})
				open(t, page, fixture, label)
				waitForNetworkIdle(t, page)
				mu.Lock()
				found := append([]string(nil), offsite...)
				mu.Unlock()
				if len(found) > 0 {
					t.Errorf("[%s] %s fetched from off-origin: %v", fixture.Theme, label, found)
				}
			})
		}

		for _, label := range []string{"docs", "standalone-current"} {
			t.Run("the body of "+label+" is set in the framework face", func(t *testing.T) {
				// Not a fallback: the face the framework ships is the one painted.
				page := newPage(t)
				open(t, page, fixture, label)
				waitForNetworkIdle(t, page)
				loaded := evalStrings(t, page, `() => {
                    const out = [];
                    document.fonts.forEach(f => { if (f.status === 'loaded')
                        out.push(f.family); });
                    return out;
                }`)
				framework := false
				for _, family := range loaded {
					if strings.Contains(family, "Plex") {
						framework = true
					}
				}
				if !framework {
					t.Errorf("[%s] %s loaded no framework face; loaded=%v",
						fixture.Theme, label, sortedStrings(loaded))
				}
			})
		}

		for _, label := range []string{"docs", "docs-tables", "standalone-current"} {
			t.Run("a page taller than the viewport still scrolls on "+label, func(t *testing.T) {
				// The application frame is fixed, so the content column must move.
				//
				// Every theme states the framework's shell: #tm-app is pinned
				// to the viewport and #tm-content is the only scroller on the
				// page. Get that wrong -- the column not scrolling, or the
				// document scrolling instead of it -- and everything below the
				// fold is unreachable while the top of the page looks perfect
				// in a screenshot. .doc-body is the selectable region, so a
				// passage has to be copyable too.
				page := newPage(t)
				open(t, page, fixture, label)
				waitForNetworkIdle(t, page)
				setViewport(t, page, 1280, 500, 80)
				metrics := evalMap(t, page, `() => {
                    const el = document.getElementById('tm-content');
                    if (!el) return {missing: true};
                    el.style.scrollBehavior = 'auto';
                    el.scrollTop = 100000;
                    return {
                        scrollable: el.scrollHeight > el.clientHeight + 4,
                        moved: el.scrollTop > 0,
                        select: getComputedStyle(
                            document.querySelector('.doc-body')).userSelect,
                    };
                }`)
				if mapBool(metrics, "missing") {
					t.Fatalf("[%s] %s carries no #tm-content, so the page is not the "+
						"framework's shell at all", fixture.Theme, label)
				}
				if !mapBool(metrics, "scrollable") {
					t.Fatalf("[%s] %s is not taller than a 500px viewport; the fixture "+
						"cannot measure scrolling on it", fixture.Theme, label)
				}
				if !mapBool(metrics, "moved") {
					t.Errorf("[%s] %s does not scroll -- everything below the fold is "+
						"unreachable", fixture.Theme, label)
				}
				if selectable := mapString(metrics, "select"); selectable == "none" {
					t.Errorf("[%s] %s renders unselectable prose (user-select: %s)",
						fixture.Theme, label, selectable)
				}
			})
		}
	})
}
