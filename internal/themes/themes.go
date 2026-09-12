// Package themes is the theme registry: the stylesheets a built site can be
// painted with, and the metadata each one carries.
//
// A theme is its CSS file. The registry is therefore the listing of the
// embedded stylesheets rather than a second list kept in step with them, so
// every place that validates or enumerates a theme reads [List].
//
// # Framework themes
//
// A theme's companion JSON may declare a framework block, and then the theme
// is not a whole stylesheet: it is an overlay on top of a framework whose
// sheets ship in a dependency. tinymoon is the one such theme -- selfdoc
// consumes the framework rather than imitating it, so the palette, the reset
// and the faces are the framework's, and the file in this package carries only
// what is selfdoc's. The overlay still restates a good deal of component
// styling, because the emitters still produce selfdoc's own class surface
// rather than the framework's markup shapes; that restatement goes when the
// emitters migrate.
//
// Three consequences the rest of the build reads through this package:
//
//   - [CSS] returns the composed stylesheet -- the framework's sheets, in the
//     order its markup contract requires, then the overlay. The framework
//     bytes are shipped as-is; nothing here rewrites them.
//   - [Assets] names the non-CSS files that have to travel with the stylesheet,
//     and [CSSRel] says where the stylesheet is written relative to a site
//     root. The framework's @font-face rules address ../fonts/, so the
//     stylesheet goes in css/ with fonts/ beside it -- the layout inside the
//     framework's own asset tree, preserved.
//   - [Modules] is the ES modules a page under the theme imports: the closure
//     of the entry points the framework block declares, computed from the
//     framework's own sources. A declared list would be a second copy of a
//     fact the sources already state, and the breakage when it fell behind
//     would be a page importing a module the site does not carry.
package themes

import (
	"embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"sort"
	"strings"
)

// registry holds every theme's stylesheet and its companion metadata. The
// listing of the .css files in it is the registry of theme names.
//
//go:embed *.css *.json
var registry embed.FS

// DefaultCSSRel is where a plain theme's stylesheet is written, relative to a
// site root.
const DefaultCSSRel = "style.css"

// FrameworkCSSRel is where a framework theme's stylesheet is written. The
// directory is not decoration: the framework's font URLs are ../fonts/, so the
// sheet has to sit one level in with fonts/ as its sibling.
const FrameworkCSSRel = "css/style.css"

// ModulesDir is where a framework theme's ES modules are written, from the
// payload root.
const ModulesDir = "js"

// criticalMarker separates the CSS a page inlines into its head from the CSS
// it links. The build stage that performs the split owns the marker as its own
// constant; the composition below emits it because a framework composition
// declares itself entirely non-critical, and it has to say so in the bytes.
const criticalMarker = "/* --- NON-CRITICAL --- */"

// Metadata is everything a page renderer needs to know about a theme beyond
// its stylesheet: how the faces are loaded, what the accent colour is, which
// highlighting styles the code blocks use, and where the stylesheet itself is
// written.
//
// Name and CSSRel are computed rather than declared: every page renderer
// already carries the metadata, so carrying the theme's identity and the
// address of its stylesheet in the same value saves threading two more
// parameters through every wrapper.
type Metadata struct {
	// Name is the theme this metadata describes.
	Name string
	// FontsURL is the webfont stylesheet a page links, empty when the theme
	// ships its faces as files instead.
	FontsURL string
	// FontsPreconnect is the origins a page preconnects to for FontsURL.
	FontsPreconnect []string
	// AccentColor is the theme's accent, used for generated images and the
	// browser theme colour.
	AccentColor string
	// PygmentsLight and PygmentsDark name the highlighting styles for the
	// light and dark colour schemes.
	PygmentsLight string
	PygmentsDark  string
	// CSSRel is where this theme's stylesheet is written, from a site root.
	CSSRel string
	// Framework is the framework block the theme's companion JSON declares,
	// nil for a theme that is a whole stylesheet of its own. It is the block
	// as written, unvalidated: [FrameworkOf] is what refuses half a
	// declaration.
	Framework *Framework
}

// Framework is the framework block a theme declares: a package whose sheets
// the theme composes over, plus the asset directories and the ES module entry
// points that have to travel with the composed stylesheet.
type Framework struct {
	// Package names the framework whose assets are read.
	Package string
	// Sheets are the stylesheets to take from the package, in the order the
	// framework's markup contract requires.
	Sheets []string
	// Assets are the asset directories every file of which travels with the
	// stylesheet.
	Assets []string
	// Modules are the ES module entry points a page imports by name. Their
	// transitive imports are computed, not declared.
	Modules []string
}

// defaultMetadata is what a theme with no companion JSON file gets. The values
// are the ones historically hardcoded across the build and the page renderer.
var defaultMetadata = Metadata{
	FontsURL:        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap",
	FontsPreconnect: []string{"https://fonts.googleapis.com", "https://fonts.gstatic.com"},
	AccentColor:     "#0969da",
	PygmentsLight:   "default",
	PygmentsDark:    "monokai",
}

// List returns every theme name this build ships, sorted.
//
// A theme is its CSS file, so the listing of the embedded stylesheets is the
// registry -- there is no second list to keep in step with it.
func List() []string {
	entries, err := fs.ReadDir(registry, ".")
	if err != nil {
		// Unreachable: the directory is embedded above.
		panic(err)
	}
	var names []string
	for _, entry := range entries {
		if name, ok := strings.CutSuffix(entry.Name(), ".css"); ok {
			names = append(names, name)
		}
	}
	sort.Strings(names)
	return names
}

// Meta returns the metadata for the named theme: the contents of its companion
// {name}.json merged over the defaults, plus the computed name and stylesheet
// address.
//
// A theme with no companion JSON gets the defaults. An unknown theme is not an
// error here -- it gets the defaults too, the same way the Python surface did;
// [Overlay] and [CSS] are what refuse a name the registry does not carry.
func Meta(name string) (Metadata, error) {
	meta := defaultMetadata
	meta.FontsPreconnect = append([]string(nil), defaultMetadata.FontsPreconnect...)

	raw, err := registry.ReadFile(name + ".json")
	if err == nil {
		var declared map[string]json.RawMessage
		if err := json.Unmarshal(raw, &declared); err != nil {
			return Metadata{}, fmt.Errorf("theme %q has an unreadable %s.json: %w", name, name, err)
		}
		// Each key is merged only when the document declares it, and a
		// declared null overrides the default with nothing -- the theme that
		// ships its faces as files says so by declaring "fonts_url": null.
		if err := mergeString(declared, "fonts_url", &meta.FontsURL); err != nil {
			return Metadata{}, fmt.Errorf("theme %q: %w", name, err)
		}
		if err := mergeString(declared, "accent_color", &meta.AccentColor); err != nil {
			return Metadata{}, fmt.Errorf("theme %q: %w", name, err)
		}
		if err := mergeString(declared, "pygments_light", &meta.PygmentsLight); err != nil {
			return Metadata{}, fmt.Errorf("theme %q: %w", name, err)
		}
		if err := mergeString(declared, "pygments_dark", &meta.PygmentsDark); err != nil {
			return Metadata{}, fmt.Errorf("theme %q: %w", name, err)
		}
		if value, ok := declared["fonts_preconnect"]; ok {
			var urls []string
			if err := json.Unmarshal(value, &urls); err != nil {
				return Metadata{}, fmt.Errorf("theme %q declares fonts_preconnect that is not a list of strings: %w", name, err)
			}
			meta.FontsPreconnect = urls
		}
		block, err := parseFramework(name, declared["framework"])
		if err != nil {
			return Metadata{}, err
		}
		meta.Framework = block
	}

	meta.Name = name
	meta.CSSRel = DefaultCSSRel
	if meta.Framework != nil {
		meta.CSSRel = FrameworkCSSRel
	}
	return meta, nil
}

// mergeString assigns the named key's value to target when the document
// declares it. A declared null clears the target rather than keeping the
// default.
func mergeString(declared map[string]json.RawMessage, key string, target *string) error {
	value, ok := declared[key]
	if !ok {
		return nil
	}
	if string(value) == "null" {
		*target = ""
		return nil
	}
	var text string
	if err := json.Unmarshal(value, &text); err != nil {
		return fmt.Errorf("declares %s that is not a string: %w", key, err)
	}
	*target = text
	return nil
}

// parseFramework reads the framework block as written, without judging it.
// An absent, null or empty block is no framework at all; a non-empty one is
// returned whatever it declares, because [FrameworkOf] is the one place that
// refuses half a declaration.
func parseFramework(name string, raw json.RawMessage) (*Framework, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		// A framework key that is not an object -- null, false, a string --
		// carries no package and no sheets, so it is no framework.
		return nil, nil
	}
	if len(fields) == 0 {
		return nil, nil
	}
	var block struct {
		Package string   `json:"package"`
		Sheets  []string `json:"sheets"`
		Assets  []string `json:"assets"`
		Modules []string `json:"modules"`
	}
	if err := json.Unmarshal(raw, &block); err != nil {
		return nil, fmt.Errorf("theme %q declares a framework block that is not readable: %w", name, err)
	}
	return &Framework{
		Package: block.Package,
		Sheets:  block.Sheets,
		Assets:  block.Assets,
		Modules: block.Modules,
	}, nil
}

// Overlay returns the theme's own CSS file, without any framework sheets under
// it. An unknown theme is an error naming the registry.
func Overlay(name string) (string, error) {
	css, err := registry.ReadFile(name + ".css")
	if err != nil {
		available := strings.Join(List(), ", ")
		if available == "" {
			available = "none"
		}
		return "", fmt.Errorf("unknown theme %q; available themes: %s", name, available)
	}
	return string(css), nil
}

// CSS returns the stylesheet for the named theme.
//
// For a framework theme this is the composition: the framework's sheets
// followed by selfdoc's overlay. The whole composition sits below the
// critical-CSS marker, because the framework's @font-face rules are written
// relative to the stylesheet's own location and inlining them into a page at
// arbitrary depth would aim them at nothing.
func CSS(name string) (string, error) {
	overlay, err := Overlay(name)
	if err != nil {
		return "", err
	}
	framework, err := FrameworkSheetsCSS(name)
	if err != nil {
		return "", err
	}
	if framework == "" {
		return overlay, nil
	}
	return criticalMarker + "\n" + framework + "\n\n" + overlay, nil
}

// CSSRel returns where the named theme's stylesheet is written, from a site
// root.
func CSSRel(name string) (string, error) {
	block, err := FrameworkOf(name)
	if err != nil {
		return "", err
	}
	if block != nil {
		return FrameworkCSSRel, nil
	}
	return DefaultCSSRel, nil
}
