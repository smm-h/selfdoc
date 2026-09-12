package themes

import (
	"fmt"
	"io/fs"
	"path"
	"regexp"
	"sort"
	"strings"

	"github.com/smm-h/tinymoon"
)

// Asset is one file that travels with a theme's stylesheet.
//
// The source is a path inside an [fs.FS] rather than a filesystem path,
// because the framework's assets are embedded in the framework's own module:
// there is no directory on disk to copy from. A build stage writes the asset
// by reading [Asset.Bytes] and handing them to the effects handle, so the
// write is declared like every other one.
type Asset struct {
	// FS is the filesystem the source is read from.
	FS fs.FS
	// Source is the asset's path within FS.
	Source string
	// Dest is where the asset is written, relative to a site root, always
	// slash-separated.
	Dest string
}

// Bytes reads the asset's content.
func (a Asset) Bytes() ([]byte, error) {
	data, err := fs.ReadFile(a.FS, a.Source)
	if err != nil {
		return nil, fmt.Errorf("reading theme asset %s: %w", a.Source, err)
	}
	return data, nil
}

// FrameworkOf returns the framework block the named theme declares, or nil for
// a theme that is a whole stylesheet of its own.
//
// Half a declaration is a broken theme rather than a theme with defaults: a
// block naming no package, or no sheets, is refused.
func FrameworkOf(name string) (*Framework, error) {
	meta, err := Meta(name)
	if err != nil {
		return nil, err
	}
	return validateFramework(name, meta.Framework)
}

// validateFramework refuses a framework block that names no package or no
// sheets. It takes the block rather than the theme name so a test can exercise
// the refusal without a theme that declares one.
func validateFramework(name string, block *Framework) (*Framework, error) {
	if block == nil {
		return nil, nil
	}
	if block.Package == "" || len(block.Sheets) == 0 {
		return nil, fmt.Errorf(
			"theme %q declares a framework block with no 'package' or no 'sheets'",
			name,
		)
	}
	return block, nil
}

// frameworkFS returns the asset tree the named framework package ships.
//
// The package is a hard dependency of this engine, so an unknown one is a
// programming error rather than a condition to route around.
func frameworkFS(pkg string) (fs.FS, error) {
	if pkg == "tinymoon" {
		return tinymoon.FS(), nil
	}
	return nil, fmt.Errorf(
		"unknown theme framework package %q; selfdoc knows how to locate the assets of: tinymoon",
		pkg,
	)
}

// FrameworkSheetsCSS returns the framework sheets a theme composes over,
// concatenated in the declared order, each under a banner naming its source.
//
// Empty for a theme that declares no framework. The bytes are the framework's
// own: they are read and joined, never rewritten, so the hash of the result
// pins the framework version that produced it.
func FrameworkSheetsCSS(name string) (string, error) {
	block, err := FrameworkOf(name)
	if err != nil {
		return "", err
	}
	return frameworkSheetsCSS(name, block)
}

func frameworkSheetsCSS(name string, block *Framework) (string, error) {
	if block == nil {
		return "", nil
	}
	assets, err := frameworkFS(block.Package)
	if err != nil {
		return "", err
	}
	var parts []string
	for _, sheet := range block.Sheets {
		rel := path.Join("css", sheet+".css")
		data, err := fs.ReadFile(assets, rel)
		if err != nil {
			return "", fmt.Errorf(
				"theme %q names the framework sheet %q, which %s does not ship at %s",
				name, sheet, block.Package, rel,
			)
		}
		parts = append(parts, fmt.Sprintf("/* --- %s/%s.css --- */\n%s", block.Package, sheet, data))
	}
	return strings.Join(parts, "\n\n"), nil
}

// jsImportRe matches every static-import form the framework's modules use. A
// specifier is always relative and always names a file: the framework has no
// bare specifiers, no import maps and no extensionless imports, so this covers
// the whole surface -- and a form it does not cover is refused by
// [checkImportsAreRelative] rather than shipping a module whose dependency is
// missing.
//
// The character class is Python's \w plus the path punctuation, spelled out
// because Go's \w is ASCII-only where Python's is Unicode-aware.
var jsImportRe = regexp.MustCompile(`(?:from|import)\s*\(?\s*["'](\./[\p{L}\p{N}_.\-/]+\.js)["']`)

// jsFromStatementRe and jsBareImportRe match the specifier of a static import
// or re-export statement at the start of a line -- where an ES module's static
// imports sit. They are deliberately broader than [jsImportRe]: they capture
// the specifier whatever its shape, so a shape the closure cannot follow can
// be refused instead of walked past.
//
// Between the keyword and `from` only import-clause characters are allowed, so
// `export const label = "read from disk";` is not mistaken for a re-export.
var (
	jsFromStatementRe = regexp.MustCompile(`(?m)^[ \t]*(?:import|export)[ \t][\p{L}\p{N}_$,{}*\s]*?\bfrom[ \t]*["']([^"'\n]*)["']`)
	jsBareImportRe    = regexp.MustCompile(`(?m)^[ \t]*import[ \t]*["']([^"'\n]*)["']`)
)

// relativeModuleRe is the one specifier shape the closure can follow.
var relativeModuleRe = regexp.MustCompile(`^\./[\p{L}\p{N}_.\-/]+\.js$`)

// Modules returns every framework module a page under this theme loads,
// sorted.
//
// The theme's framework block names entry points -- the modules the page's own
// script imports by name. Their transitive imports are computed here from the
// framework's own sources rather than declared, because a declared list is a
// second copy of a fact the sources already state, and the breakage when it
// falls behind is a page that imports a module the site does not carry.
//
// The framework ships far more than a documentation page uses (its whole
// module tree is an order of magnitude larger than this closure), so the
// closure is also what keeps the payload to what is really loaded.
//
// Empty for a theme that declares no framework, or one whose framework block
// names no modules.
func Modules(name string) ([]string, error) {
	block, err := FrameworkOf(name)
	if err != nil {
		return nil, err
	}
	return modules(name, block)
}

func modules(name string, block *Framework) ([]string, error) {
	if block == nil || len(block.Modules) == 0 {
		return nil, nil
	}
	assets, err := frameworkFS(block.Package)
	if err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	queue := append([]string(nil), block.Modules...)
	for len(queue) > 0 {
		module := queue[len(queue)-1]
		queue = queue[:len(queue)-1]
		if seen[module] {
			continue
		}
		rel := path.Join(ModulesDir, module)
		source, err := fs.ReadFile(assets, rel)
		if err != nil {
			return nil, fmt.Errorf(
				"theme %q reaches the framework module %q, which %s does not ship at %s",
				name, module, block.Package, rel,
			)
		}
		seen[module] = true
		if err := checkImportsAreRelative(name, module, block.Package, string(source)); err != nil {
			return nil, err
		}
		for _, match := range jsImportRe.FindAllStringSubmatch(string(source), -1) {
			queue = append(queue, strings.TrimPrefix(match[1], "./"))
		}
	}
	names := make([]string, 0, len(seen))
	for module := range seen {
		names = append(names, module)
	}
	sort.Strings(names)
	return names, nil
}

// checkImportsAreRelative refuses a module whose static imports the closure
// cannot follow.
//
// The closure follows relative specifiers naming a .js file, which is every
// specifier the framework uses. A bare specifier, an import-map entry or an
// extensionless one would be walked past silently and the page would then
// import a module the site does not carry, so it is a hard error naming the
// module and the specifier. Dynamic imports are outside the check: they are
// not statements and are resolved at runtime.
func checkImportsAreRelative(theme, module, pkg, source string) error {
	for _, re := range []*regexp.Regexp{jsFromStatementRe, jsBareImportRe} {
		for _, match := range re.FindAllStringSubmatch(source, -1) {
			if relativeModuleRe.MatchString(match[1]) {
				continue
			}
			return fmt.Errorf(
				"theme %q reaches the framework module %q, whose import %q is not a "+
					"relative .js specifier; selfdoc carries %s's modules as a relative "+
					"graph and cannot resolve anything else",
				theme, module, match[1], pkg,
			)
		}
	}
	return nil
}

// Assets returns the files that have to travel with a theme's stylesheet and
// are not the stylesheet, each with the site-relative address it is written
// at.
//
// One directory per kind the framework block names -- the @font-face rules are
// the only thing in the sheets that addresses anything outside them -- plus
// the ES modules a page imports, which are the closure of the block's declared
// entry points rather than the framework's whole module tree. Empty for a
// theme that declares no framework. Destinations keep the layout the framework
// uses, because the sheets and the modules address each other by relative URL.
func Assets(name string) ([]Asset, error) {
	block, err := FrameworkOf(name)
	if err != nil {
		return nil, err
	}
	return frameworkAssets(name, block)
}

func frameworkAssets(name string, block *Framework) ([]Asset, error) {
	if block == nil {
		return nil, nil
	}
	assets, err := frameworkFS(block.Package)
	if err != nil {
		return nil, err
	}
	closure, err := modules(name, block)
	if err != nil {
		return nil, err
	}
	var pairs []Asset
	for _, module := range closure {
		pairs = append(pairs, Asset{
			FS:     assets,
			Source: path.Join(ModulesDir, module),
			Dest:   ModulesDir + "/" + module,
		})
	}
	for _, kind := range block.Assets {
		entries, err := fs.ReadDir(assets, kind)
		if err != nil {
			return nil, fmt.Errorf(
				"theme %q names the framework asset directory %q, which %s does not ship at %s",
				name, kind, block.Package, kind,
			)
		}
		// fs.ReadDir already sorts by filename, which is the order the
		// Python surface produced with an explicit sorted().
		for _, entry := range entries {
			if entry.IsDir() {
				continue
			}
			pairs = append(pairs, Asset{
				FS:     assets,
				Source: path.Join(kind, entry.Name()),
				Dest:   kind + "/" + entry.Name(),
			})
		}
	}
	return pairs, nil
}
