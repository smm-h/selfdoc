package themes

import (
	"io/fs"
	"path"
	"regexp"
	"slices"
	"strings"
	"testing"
)

// --- The declaration ---

func TestTinymoonDeclaresTheFramework(t *testing.T) {
	block, err := FrameworkOf("tinymoon")
	if err != nil {
		t.Fatalf("FrameworkOf: %v", err)
	}
	if block == nil {
		t.Fatal("tinymoon declares no framework")
	}
	if block.Package != "tinymoon" {
		t.Errorf("package = %q", block.Package)
	}
}

func TestTheSheetsAreNamedInContractOrder(t *testing.T) {
	block, err := FrameworkOf("tinymoon")
	if err != nil {
		t.Fatalf("FrameworkOf: %v", err)
	}
	if !slices.Equal(block.Sheets, contractSheetOrder) {
		t.Errorf("sheets = %v, want %v", block.Sheets, contractSheetOrder)
	}
}

func TestEveryOtherThemeIsAWholeStylesheet(t *testing.T) {
	for _, name := range plainThemes(t) {
		block, err := FrameworkOf(name)
		if err != nil {
			t.Fatalf("FrameworkOf(%q): %v", name, err)
		}
		if block != nil {
			t.Errorf("theme %q declares a framework", name)
		}
	}
}

func TestAFrameworkBlockWithoutSheetsIsRefused(t *testing.T) {
	// Half a declaration is a broken theme, not a theme with defaults.
	cases := []struct {
		name  string
		block *Framework
	}{
		{"no sheets", &Framework{Package: "tinymoon"}},
		{"empty sheets", &Framework{Package: "tinymoon", Sheets: []string{}}},
		{"no package", &Framework{Sheets: []string{"tokens"}}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := validateFramework("tinymoon", tc.block)
			if err == nil {
				t.Fatal("the block was accepted")
			}
			if !strings.Contains(err.Error(), "'sheets'") {
				t.Errorf("error %q does not name the missing keys", err)
			}
		})
	}
}

func TestAnEmptyFrameworkBlockIsNoFramework(t *testing.T) {
	block, err := validateFramework("tinymoon", nil)
	if err != nil || block != nil {
		t.Fatalf("validateFramework(nil) = %v, %v", block, err)
	}
	for _, raw := range []string{``, `null`, `{}`, `false`, `"tinymoon"`} {
		parsed, err := parseFramework("t", []byte(raw))
		if err != nil {
			t.Errorf("parseFramework(%q): %v", raw, err)
		}
		if parsed != nil {
			t.Errorf("parseFramework(%q) = %+v, want no framework", raw, parsed)
		}
	}
}

func TestAnUnknownPackageIsRefused(t *testing.T) {
	block := &Framework{Package: "nowhere", Sheets: []string{"a"}}
	if _, err := frameworkSheetsCSS("tinymoon", block); err == nil {
		t.Fatal("an unknown package was accepted")
	} else if !strings.Contains(err.Error(), "nowhere") {
		t.Errorf("error %q does not name the package", err)
	}
	if _, err := modules("tinymoon", &Framework{
		Package: "nowhere", Sheets: []string{"a"}, Modules: []string{"x.js"},
	}); err == nil {
		t.Fatal("an unknown package was accepted by modules")
	}
}

func TestASheetTheFrameworkDoesNotShipIsRefused(t *testing.T) {
	block := &Framework{Package: "tinymoon", Sheets: []string{"nowhere"}}
	_, err := frameworkSheetsCSS("tinymoon", block)
	if err == nil {
		t.Fatal("a missing sheet was accepted")
	}
	for _, want := range []string{`"nowhere"`, "tinymoon", "css/nowhere.css"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error %q does not mention %q", err, want)
		}
	}
}

func TestAModuleTheFrameworkDoesNotShipIsRefused(t *testing.T) {
	block := &Framework{
		Package: "tinymoon",
		Sheets:  []string{"tokens"},
		Modules: []string{"nowhere.js"},
	}
	_, err := modules("tinymoon", block)
	if err == nil {
		t.Fatal("a missing module was accepted")
	}
	if !strings.Contains(err.Error(), "js/nowhere.js") {
		t.Errorf("error %q does not name the path", err)
	}
}

func TestAThemeWithNoFrameworkComposesAndShipsNothingExtra(t *testing.T) {
	for _, name := range plainThemes(t) {
		css, err := FrameworkSheetsCSS(name)
		if err != nil {
			t.Fatalf("FrameworkSheetsCSS(%q): %v", name, err)
		}
		if css != "" {
			t.Errorf("theme %q composes framework sheets", name)
		}
		mods, err := Modules(name)
		if err != nil {
			t.Fatalf("Modules(%q): %v", name, err)
		}
		if len(mods) != 0 {
			t.Errorf("theme %q ships modules: %v", name, mods)
		}
		assets, err := Assets(name)
		if err != nil {
			t.Fatalf("Assets(%q): %v", name, err)
		}
		if len(assets) != 0 {
			t.Errorf("theme %q ships assets beside its stylesheet: %v", name, assets)
		}
	}
}

func TestABlockNamingNoModulesShipsNoClosure(t *testing.T) {
	block := &Framework{Package: "tinymoon", Sheets: []string{"tokens"}}
	mods, err := modules("tinymoon", block)
	if err != nil {
		t.Fatalf("modules: %v", err)
	}
	if len(mods) != 0 {
		t.Errorf("modules = %v, want none", mods)
	}
}

// --- The module closure ---

func TestTheModulePayloadIsTheClosureOfTheEntryPoints(t *testing.T) {
	// Declared entries, plus everything they import, and nothing else.
	block, err := FrameworkOf("tinymoon")
	if err != nil {
		t.Fatalf("FrameworkOf: %v", err)
	}
	shipped, err := Modules("tinymoon")
	if err != nil {
		t.Fatalf("Modules: %v", err)
	}
	for _, entry := range block.Modules {
		if !slices.Contains(shipped, entry) {
			t.Errorf("the closure omits the declared entry point %q", entry)
		}
	}
	assets, err := frameworkFS(block.Package)
	if err != nil {
		t.Fatalf("frameworkFS: %v", err)
	}
	entries, err := fs.ReadDir(assets, ModulesDir)
	if err != nil {
		t.Fatalf("reading the module tree: %v", err)
	}
	whole := 0
	for _, entry := range entries {
		if strings.HasSuffix(entry.Name(), ".js") {
			whole++
		}
	}
	if len(shipped)*4 >= whole {
		t.Errorf("the closure is %d of %d modules; the payload is the whole tree again", len(shipped), whole)
	}
	// Every import inside the closure resolves within it, or a page loading
	// the entry point fetches a module the site does not carry.
	for _, name := range shipped {
		source, err := fs.ReadFile(assets, path.Join(ModulesDir, name))
		if err != nil {
			t.Fatalf("reading %s: %v", name, err)
		}
		for _, match := range jsImportRe.FindAllStringSubmatch(string(source), -1) {
			target := strings.TrimPrefix(match[1], "./")
			if !slices.Contains(shipped, target) {
				t.Errorf("%s imports %s, which the closure does not carry", name, target)
			}
		}
	}
}

func TestTheClosureIsSortedAndDeduplicated(t *testing.T) {
	shipped, err := Modules("tinymoon")
	if err != nil {
		t.Fatalf("Modules: %v", err)
	}
	if len(shipped) == 0 {
		t.Fatal("no modules")
	}
	if !slices.IsSorted(shipped) {
		t.Errorf("the closure is not sorted: %v", shipped)
	}
	for i := 1; i < len(shipped); i++ {
		if shipped[i-1] == shipped[i] {
			t.Errorf("the closure repeats %q", shipped[i])
		}
	}
}

func TestANonRelativeImportIsRefused(t *testing.T) {
	// The closure can only follow a relative .js specifier. Anything else
	// would be walked past and the page would import a module the site does
	// not carry, so it is a hard error rather than a silent omission.
	refused := []string{
		`import { el } from "tinymoon";`,
		`import { el } from "./dom";`,
		`import "tinymoon/dom.js";`,
		`export { el } from "tinymoon";`,
		`export * from "https://cdn.example/dom.js";`,
	}
	for _, source := range refused {
		if err := checkImportsAreRelative("tinymoon", "palette.js", "tinymoon", source); err == nil {
			t.Errorf("accepted %q", source)
		}
	}
	accepted := []string{
		`import { el } from "./dom.js";`,
		`import { icon as renderIcon } from "./icons.js";`,
		`import * as dom from "./sub/dom.js";`,
		`import "./side-effect.js";`,
		`export { el } from "./dom.js";`,
		"export const label = \"read from \\\"disk\\\"\";",
		`export const hint = "imported from elsewhere";`,
		`  const spec = "tinymoon";`,
		`const loaded = await import("./lazy.js");`,
	}
	for _, source := range accepted {
		if err := checkImportsAreRelative("tinymoon", "palette.js", "tinymoon", source); err != nil {
			t.Errorf("refused %q: %v", source, err)
		}
	}
}

func TestEveryClosureModulePassesTheRelativeImportCheck(t *testing.T) {
	// The premise of the check: the framework's own sources satisfy it, so it
	// fires on a change in the framework rather than on the framework as
	// shipped.
	if _, err := Modules("tinymoon"); err != nil {
		t.Fatalf("Modules: %v", err)
	}
}

// --- The assets that travel with the stylesheet ---

func TestTheFacesAreRealFiles(t *testing.T) {
	assets, err := Assets("tinymoon")
	if err != nil {
		t.Fatalf("Assets: %v", err)
	}
	fonts := 0
	for _, asset := range assets {
		if !strings.HasPrefix(asset.Dest, "fonts/") {
			continue
		}
		fonts++
		if !strings.HasSuffix(asset.Dest, ".woff2") {
			t.Errorf("font asset %q is not a woff2", asset.Dest)
		}
	}
	if fonts < 4 {
		t.Errorf("font count = %d, want at least 4", fonts)
	}
}

func TestOnlyTheDeclaredKindsTravel(t *testing.T) {
	// The declaration drives the payload, not a hardcoded list. fonts is
	// declared as a directory, because the @font-face rules reference every
	// file in it. The modules are declared as entry points instead and their
	// closure is computed, because a page imports one module and gets whatever
	// that module imports -- shipping the framework's whole module tree would
	// be an order of magnitude of dead weight on every deploy.
	block, err := FrameworkOf("tinymoon")
	if err != nil {
		t.Fatalf("FrameworkOf: %v", err)
	}
	assets, err := Assets("tinymoon")
	if err != nil {
		t.Fatalf("Assets: %v", err)
	}
	want := append(append([]string(nil), block.Assets...), ModulesDir)
	slices.Sort(want)
	var got []string
	for _, asset := range assets {
		kind, _, _ := strings.Cut(asset.Dest, "/")
		if !slices.Contains(got, kind) {
			got = append(got, kind)
		}
	}
	slices.Sort(got)
	if !slices.Equal(got, want) {
		t.Errorf("kinds = %v, want %v", got, want)
	}
}

func TestEveryAssetSourceExists(t *testing.T) {
	assets, err := Assets("tinymoon")
	if err != nil {
		t.Fatalf("Assets: %v", err)
	}
	if len(assets) == 0 {
		t.Fatal("no assets")
	}
	for _, asset := range assets {
		data, err := asset.Bytes()
		if err != nil {
			t.Errorf("%s: %v", asset.Source, err)
			continue
		}
		if len(data) == 0 {
			t.Errorf("%s is empty", asset.Source)
		}
	}
}

func TestTheModuleAssetsAreTheClosureAtTheirOwnAddresses(t *testing.T) {
	shipped, err := Modules("tinymoon")
	if err != nil {
		t.Fatalf("Modules: %v", err)
	}
	assets, err := Assets("tinymoon")
	if err != nil {
		t.Fatalf("Assets: %v", err)
	}
	var written []string
	for _, asset := range assets {
		if name, ok := strings.CutPrefix(asset.Dest, ModulesDir+"/"); ok {
			written = append(written, name)
			if asset.Source != ModulesDir+"/"+name {
				t.Errorf("module %q reads from %q", name, asset.Source)
			}
		}
	}
	if !slices.Equal(written, shipped) {
		t.Errorf("written modules = %v, want %v", written, shipped)
	}
}

func TestAnAssetDirectoryTheFrameworkDoesNotShipIsRefused(t *testing.T) {
	// Assets() resolves the directory from the block, so the refusal is
	// exercised through a block naming a directory tinymoon has no such thing
	// of.
	block := &Framework{
		Package: "tinymoon",
		Sheets:  []string{"tokens"},
		Assets:  []string{"nowhere"},
	}
	if _, err := frameworkAssets("tinymoon", block); err == nil {
		t.Fatal("a missing asset directory was accepted")
	} else if !strings.Contains(err.Error(), "nowhere") {
		t.Errorf("error %q does not name the directory", err)
	}
}

var relativeURLRe = regexp.MustCompile(`url\("(\.\./[^"]+)"\)`)

func TestTheFontURLsResolveFromTheStylesheetDirectory(t *testing.T) {
	// ../fonts/x.woff2 from css/style.css is fonts/x.woff2.
	assets, err := frameworkFS("tinymoon")
	if err != nil {
		t.Fatalf("frameworkFS: %v", err)
	}
	base, err := fs.ReadFile(assets, "css/base.css")
	if err != nil {
		t.Fatalf("reading base.css: %v", err)
	}
	urls := relativeURLRe.FindAllStringSubmatch(string(base), -1)
	if len(urls) == 0 {
		t.Fatal("the framework's base.css declares no relative font URLs")
	}
	pairs, err := Assets("tinymoon")
	if err != nil {
		t.Fatalf("Assets: %v", err)
	}
	var destinations []string
	for _, asset := range pairs {
		destinations = append(destinations, asset.Dest)
	}
	for _, match := range urls {
		resolved := path.Join(path.Dir(FrameworkCSSRel), match[1])
		if !slices.Contains(destinations, resolved) {
			t.Errorf("%s resolves to %s, which no theme asset provides", match[1], resolved)
		}
	}
}
