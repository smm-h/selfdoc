package themes

import (
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"testing"
)

// pythonThemesDir is where the Python package this port replaces keeps the
// same assets. The byte-identity test below reads it and skips when it is
// gone, because the Python tree is deleted at the end of the port.
const pythonThemesDir = "../../selfdoc_core/themes"

// contractSheetOrder is the order the framework's markup contract requires:
// tokens before everything, base before the shapes, prose last so the reading
// scale wins over the app-scale docs family it extends.
var contractSheetOrder = []string{"tokens", "base", "shell", "primitives", "widgets", "prose"}

var commentRe = regexp.MustCompile(`(?s)/\*.*?\*/`)

// uncommented is css with its comments removed -- the rules, not the prose.
func uncommented(css string) string {
	return commentRe.ReplaceAllString(css, "")
}

// plainThemes is every registered theme that is a whole stylesheet of its own.
func plainThemes(t *testing.T) []string {
	t.Helper()
	var names []string
	for _, name := range List() {
		block, err := FrameworkOf(name)
		if err != nil {
			t.Fatalf("FrameworkOf(%q): %v", name, err)
		}
		if block == nil {
			names = append(names, name)
		}
	}
	if len(names) == 0 {
		t.Fatal("no plain theme left to compare against")
	}
	return names
}

func mustCSS(t *testing.T, name string) string {
	t.Helper()
	css, err := CSS(name)
	if err != nil {
		t.Fatalf("CSS(%q): %v", name, err)
	}
	return css
}

// --- The registry is the one list ---

func TestListIsEveryEmbeddedStylesheet(t *testing.T) {
	got := List()
	for _, want := range []string{"clean", "minimal", "tinymoon"} {
		if !slices.Contains(got, want) {
			t.Errorf("List() = %v, missing %q", got, want)
		}
	}
	for i := 1; i < len(got); i++ {
		if got[i-1] >= got[i] {
			t.Errorf("List() is not sorted: %v", got)
		}
	}
}

func TestEveryListedThemeLoads(t *testing.T) {
	for _, name := range List() {
		css := mustCSS(t, name)
		if strings.TrimSpace(css) == "" {
			t.Errorf("theme %q composes to nothing", name)
		}
	}
}

func TestAnUnknownThemeIsRefused(t *testing.T) {
	_, err := Overlay("nowhere")
	if err == nil {
		t.Fatal("Overlay(\"nowhere\") returned no error")
	}
	for _, want := range []string{"unknown theme", "nowhere", "clean, minimal, tinymoon"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error %q does not mention %q", err, want)
		}
	}
}

// --- The metadata ---

func TestMetadataDefaultsAreMergedUnderTheDeclaration(t *testing.T) {
	meta, err := Meta("minimal")
	if err != nil {
		t.Fatalf("Meta: %v", err)
	}
	if meta.AccentColor != "#0969da" {
		t.Errorf("accent = %q, want #0969da", meta.AccentColor)
	}
	if meta.PygmentsLight != "default" || meta.PygmentsDark != "monokai" {
		t.Errorf("styles = %q/%q", meta.PygmentsLight, meta.PygmentsDark)
	}
	if !strings.Contains(meta.FontsURL, "fonts.googleapis.com") {
		t.Errorf("fonts url = %q", meta.FontsURL)
	}
	if len(meta.FontsPreconnect) != 2 {
		t.Errorf("preconnect = %v", meta.FontsPreconnect)
	}
}

func TestMetadataOfAThemeWithNoCompanionJSONIsTheDefaults(t *testing.T) {
	meta, err := Meta("nowhere")
	if err != nil {
		t.Fatalf("Meta: %v", err)
	}
	if meta.AccentColor != defaultMetadata.AccentColor {
		t.Errorf("accent = %q, want the default", meta.AccentColor)
	}
	if meta.Name != "nowhere" || meta.CSSRel != DefaultCSSRel {
		t.Errorf("name/css_rel = %q/%q", meta.Name, meta.CSSRel)
	}
}

func TestTinymoonFetchesNoFontsFromTheNetwork(t *testing.T) {
	// The faces are files beside the stylesheet; a CDN URL here would be a
	// second source for them. A declared null clears the default.
	meta, err := Meta("tinymoon")
	if err != nil {
		t.Fatalf("Meta: %v", err)
	}
	if meta.FontsURL != "" {
		t.Errorf("fonts url = %q, want empty", meta.FontsURL)
	}
	if len(meta.FontsPreconnect) != 0 {
		t.Errorf("preconnect = %v, want empty", meta.FontsPreconnect)
	}
	if meta.AccentColor != "#2d6cf4" {
		t.Errorf("accent = %q", meta.AccentColor)
	}
	if meta.PygmentsLight != "xcode" || meta.PygmentsDark != "github-dark" {
		t.Errorf("styles = %q/%q", meta.PygmentsLight, meta.PygmentsDark)
	}
}

func TestTheMetadataCarriesTheStylesheetAddress(t *testing.T) {
	// Every page renderer already holds the metadata, so it holds this.
	for _, name := range List() {
		meta, err := Meta(name)
		if err != nil {
			t.Fatalf("Meta(%q): %v", name, err)
		}
		if meta.Name != name {
			t.Errorf("Meta(%q).Name = %q", name, meta.Name)
		}
		rel, err := CSSRel(name)
		if err != nil {
			t.Fatalf("CSSRel(%q): %v", name, err)
		}
		if meta.CSSRel != rel {
			t.Errorf("theme %q: metadata says %q, CSSRel says %q", name, meta.CSSRel, rel)
		}
	}
}

// --- Where the stylesheet goes ---

func TestAFrameworkThemeSitsBesideItsFonts(t *testing.T) {
	rel, err := CSSRel("tinymoon")
	if err != nil {
		t.Fatalf("CSSRel: %v", err)
	}
	if rel != FrameworkCSSRel {
		t.Errorf("CSSRel = %q, want %q", rel, FrameworkCSSRel)
	}
	if !strings.HasPrefix(FrameworkCSSRel, "css/") {
		t.Errorf("FrameworkCSSRel = %q, want it one directory in", FrameworkCSSRel)
	}
}

func TestAPlainThemeKeepsTheRootStylesheet(t *testing.T) {
	for _, name := range plainThemes(t) {
		rel, err := CSSRel(name)
		if err != nil {
			t.Fatalf("CSSRel(%q): %v", name, err)
		}
		if rel != DefaultCSSRel {
			t.Errorf("CSSRel(%q) = %q, want %q", name, rel, DefaultCSSRel)
		}
	}
}

// --- The composition ---

func TestTheFrameworkBytesAreShippedAsTheyAre(t *testing.T) {
	// Not a port of the sheet -- the sheet.
	assets, err := frameworkFS("tinymoon")
	if err != nil {
		t.Fatalf("frameworkFS: %v", err)
	}
	composed := mustCSS(t, "tinymoon")
	for _, sheet := range contractSheetOrder {
		source, err := fs.ReadFile(assets, "css/"+sheet+".css")
		if err != nil {
			t.Fatalf("reading %s.css: %v", sheet, err)
		}
		if !strings.Contains(composed, string(source)) {
			t.Errorf("the composition does not carry %s.css verbatim", sheet)
		}
	}
}

func TestTheSheetsAppearInTheDeclaredOrder(t *testing.T) {
	assets, err := frameworkFS("tinymoon")
	if err != nil {
		t.Fatalf("frameworkFS: %v", err)
	}
	composed, err := FrameworkSheetsCSS("tinymoon")
	if err != nil {
		t.Fatalf("FrameworkSheetsCSS: %v", err)
	}
	previous := -1
	for _, sheet := range contractSheetOrder {
		source, err := fs.ReadFile(assets, "css/"+sheet+".css")
		if err != nil {
			t.Fatalf("reading %s.css: %v", sheet, err)
		}
		at := strings.Index(composed, string(source))
		if at < 0 {
			t.Fatalf("%s.css is not in the composition", sheet)
		}
		if at < previous {
			t.Errorf("%s.css appears before the sheet declared ahead of it", sheet)
		}
		previous = at
	}
}

func TestTheSheetsCarryTheirBanners(t *testing.T) {
	composed, err := FrameworkSheetsCSS("tinymoon")
	if err != nil {
		t.Fatalf("FrameworkSheetsCSS: %v", err)
	}
	for _, sheet := range contractSheetOrder {
		banner := "/* --- tinymoon/" + sheet + ".css --- */\n"
		if !strings.Contains(composed, banner) {
			t.Errorf("no banner for %s.css", sheet)
		}
	}
}

func TestTheOverlayComesLast(t *testing.T) {
	// The overlay is an overlay: it has to be able to win.
	overlay, err := Overlay("tinymoon")
	if err != nil {
		t.Fatalf("Overlay: %v", err)
	}
	if !strings.HasSuffix(mustCSS(t, "tinymoon"), overlay) {
		t.Error("the composition does not end with the overlay")
	}
}

func TestNothingOfACompositionIsInlinedIntoThePageHead(t *testing.T) {
	// The framework addresses its faces at ../fonts/, which resolves against
	// the stylesheet. Inlined into a page's head, the same rule resolves
	// against the page's own directory and finds nothing, so the composition
	// declares itself entirely non-critical -- the marker is its first byte
	// and the build stage that splits on it extracts nothing.
	css := mustCSS(t, "tinymoon")
	if !strings.HasPrefix(css, criticalMarker+"\n") {
		t.Fatalf("the composition does not open with the non-critical marker")
	}
	if at := strings.Index(css, "@font-face"); at < strings.Index(css, criticalMarker) {
		t.Errorf("a @font-face rule sits above the marker, at %d", at)
	}
}

func TestAPlainThemeIsWholeAndUnmarked(t *testing.T) {
	for _, name := range plainThemes(t) {
		overlay, err := Overlay(name)
		if err != nil {
			t.Fatalf("Overlay(%q): %v", name, err)
		}
		if mustCSS(t, name) != overlay {
			t.Errorf("theme %q composes to something other than its own file", name)
		}
	}
}

func TestTinymoonServesItsFacesAsFiles(t *testing.T) {
	// The faces used to be 110 KB of base64 in every stylesheet. They are now
	// the framework's own woff2 files, shipped beside the stylesheet and
	// addressed relatively, so the bytes are cached once for the whole site.
	css := mustCSS(t, "tinymoon")
	if got := strings.Count(css, "@font-face {"); got != 4 {
		t.Errorf("@font-face count = %d, want 4", got)
	}
	for _, forbidden := range []string{"data:font/woff2;base64,", "fonts.googleapis.com"} {
		if strings.Contains(css, forbidden) {
			t.Errorf("the composition carries %q", forbidden)
		}
	}
	if !strings.Contains(css, `src: url("../fonts/`) {
		t.Error("no relative font URL in the composition")
	}
}

func TestTheOverlayCarriesNoFontBytes(t *testing.T) {
	overlay, err := Overlay("tinymoon")
	if err != nil {
		t.Fatalf("Overlay: %v", err)
	}
	rules := uncommented(overlay)
	for _, forbidden := range []string{"base64", "@font-face"} {
		if strings.Contains(rules, forbidden) {
			t.Errorf("the overlay carries %q", forbidden)
		}
	}
}

var rootBlockRe = regexp.MustCompile(`(?m)^:root\s*\{([^}]*)\}`)

func TestTheOverlayRestatesNoPalette(t *testing.T) {
	// The framework's tokens.css is the palette; a copy would drift. The
	// overlay's own :root is the bridge -- selfdoc's variable names pointed at
	// the framework's -- so every declaration in it is a var() reference and
	// none is a colour. Only the top-level bridge is read: the print sheet
	// forces ink on white inside @media print, which is paper, not palette.
	overlay, err := Overlay("tinymoon")
	if err != nil {
		t.Fatalf("Overlay: %v", err)
	}
	blocks := rootBlockRe.FindAllStringSubmatch(uncommented(overlay), -1)
	if len(blocks) == 0 {
		t.Fatal("the overlay declares no :root bridge")
	}
	for _, block := range blocks {
		for _, declaration := range strings.Split(block[1], ";") {
			name, value, found := strings.Cut(declaration, ":")
			if !found {
				continue
			}
			if !strings.HasPrefix(strings.TrimSpace(value), "var(") {
				t.Errorf("the bridge declares %s as a literal %q; it must reference a framework token",
					strings.TrimSpace(name), strings.TrimSpace(value))
			}
		}
	}
}

func TestTheOverlayIsAFractionOfWhatItReplaced(t *testing.T) {
	// The file was 183 KB. A regression to a restatement is visible.
	overlay, err := Overlay("tinymoon")
	if err != nil {
		t.Fatalf("Overlay: %v", err)
	}
	if len(overlay) >= 90000 {
		t.Errorf("the overlay is %d bytes; it is restating the framework again", len(overlay))
	}
}

// --- The embedded assets are the Python package's bytes ---

func TestEveryEmbeddedAssetIsThePythonSourceByteForByte(t *testing.T) {
	entries, err := os.ReadDir(pythonThemesDir)
	if err != nil {
		t.Skipf("the Python theme package is gone: %v", err)
	}
	python := map[string]bool{}
	for _, entry := range entries {
		name := entry.Name()
		if strings.HasSuffix(name, ".css") || strings.HasSuffix(name, ".json") {
			python[name] = true
		}
	}
	embedded, err := fs.ReadDir(registry, ".")
	if err != nil {
		t.Fatalf("reading the registry: %v", err)
	}
	for _, entry := range embedded {
		name := entry.Name()
		want, err := os.ReadFile(filepath.Join(pythonThemesDir, name))
		if err != nil {
			t.Errorf("%s is embedded but the Python package does not ship it: %v", name, err)
			continue
		}
		got, err := registry.ReadFile(name)
		if err != nil {
			t.Fatalf("reading embedded %s: %v", name, err)
		}
		if string(got) != string(want) {
			t.Errorf("embedded %s differs from the Python source", name)
		}
		delete(python, name)
	}
	for name := range python {
		t.Errorf("the Python package ships %s, which is not embedded here", name)
	}
}
