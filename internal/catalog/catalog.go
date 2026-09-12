// Package catalog is selfdoc's directive catalogue: every built-in directive
// name and its status.
//
// The shipped ("core") catalogue is not a hand-maintained literal. It is built
// from the embedded directives.toml -- a declarative descriptor document
// governed by .strictspec/directive-descriptor.schema.toml and validated by the
// strictspec-generated validator in this package. The document is the single
// authority; this file is a thin loader.
//
// A malformed catalogue document (bad name grammar, unknown key, missing
// required field, duplicate name, absent format_version marker) is a hard
// error before any directive is dispatched. [Load] reports it as an error and
// [Core] panics, which is the Go counterpart of the Python surface's
// import-time crash: the document is compiled into the binary, so a panic here
// means the binary itself is malformed.
package catalog

import (
	_ "embed"
	"fmt"
	"sort"
	"strings"
	"sync"
)

// catalogueDocumentName is the document's name as the error messages spell it.
const catalogueDocumentName = "directives.toml"

//go:embed directives.toml
var catalogueDocument []byte

// DirectiveSpec is the metadata for a single built-in directive.
type DirectiveSpec struct {
	// Description is the one-line human description the directive reference
	// table renders.
	Description string
	// Category is "code" (dispatches to a language extractor by path) or
	// "content" (resolves language-agnostically).
	Category string
	// RequiredAttrs and OptionalAttrs are the directive's attribute contract,
	// in document order.
	RequiredAttrs []string
	OptionalAttrs []string
	// Example is a representative usage example.
	Example string
}

// SharedCodeAttrs are the attributes every code-category directive accepts
// regardless of name.
//
// The multi-language resolver reads "lang" to decide which extractor handles a
// path-dispatched directive, and gen emits it on every generated ref page.
// Each code directive's optional_attrs in directives.toml lists it explicitly;
// this is the invariant a test enforces, not a second declaration.
func SharedCodeAttrs() []string { return []string{"lang"} }

// CatalogDocumentError reports a catalogue document that failed strictspec
// validation: the built-in directive catalogue is malformed, so selfdoc cannot
// know what its own directives are.
type CatalogDocumentError struct {
	Message string
}

func (e *CatalogDocumentError) Error() string { return e.Message }

// Catalogue is a loaded, validated directive catalogue.
//
// It keeps the document's order, because the directive reference table renders
// in it, and answers a name lookup in constant time.
type Catalogue struct {
	order []string
	specs map[string]DirectiveSpec
}

// Names returns every catalogued directive name in document order.
func (c *Catalogue) Names() []string {
	out := make([]string, len(c.order))
	copy(out, c.order)
	return out
}

// Len returns how many directives the catalogue carries.
func (c *Catalogue) Len() int { return len(c.order) }

// Spec returns the named directive's metadata, reporting whether the
// catalogue carries it.
func (c *Catalogue) Spec(name string) (DirectiveSpec, bool) {
	spec, ok := c.specs[name]
	return spec, ok
}

// Has reports whether the catalogue carries name.
func (c *Catalogue) Has(name string) bool {
	_, ok := c.specs[name]
	return ok
}

// BuildCatalogue validates raw catalogue-document bytes and binds them into a
// [Catalogue].
//
// strictspec is the boundary validator: the document is checked against its
// schema by the generated validator, and only a wholly valid document is
// bound. Any diagnostic is a [CatalogDocumentError] -- never a silent partial
// catalogue.
func BuildCatalogue(raw []byte) (*Catalogue, error) {
	document, diags := ValidateBytes(raw, "toml")
	if len(diags) > 0 {
		var detail strings.Builder
		for _, d := range diags {
			fmt.Fprintf(&detail, "\n  %s: %s [%s]", d.Path, d.Message, d.Code)
		}
		return nil, &CatalogDocumentError{Message: fmt.Sprintf(
			"%s is not a valid directive catalogue:%s",
			catalogueDocumentName, detail.String())}
	}
	c := &Catalogue{
		order: make([]string, 0, len(document.Directives)),
		specs: make(map[string]DirectiveSpec, len(document.Directives)),
	}
	for _, d := range document.Directives {
		c.order = append(c.order, d.Name)
		c.specs[d.Name] = DirectiveSpec{
			Description:   d.Description,
			Category:      d.Category,
			RequiredAttrs: append([]string(nil), d.RequiredAttrs...),
			OptionalAttrs: append([]string(nil), d.OptionalAttrs...),
			Example:       d.Example,
		}
	}
	return c, nil
}

// Load reads, validates and binds the embedded catalogue document.
//
// This is the error-returning door. Production code reads [Core] instead,
// which loads once.
func Load() (*Catalogue, error) { return BuildCatalogue(catalogueDocument) }

var (
	coreOnce sync.Once
	core     *Catalogue
	coreErr  error
)

// Core returns the shipped catalogue, loading and validating the embedded
// document on first use.
//
// It panics when the document is malformed. That is not a judgement call: the
// document is embedded in the binary, so a diagnostic here means this build of
// selfdoc does not know what its own directives are, and every caller below
// would have to invent a behavior for a catalogue that cannot exist. Use
// [Load] where an error is wanted.
func Core() *Catalogue {
	coreOnce.Do(func() { core, coreErr = Load() })
	if coreErr != nil {
		panic(coreErr)
	}
	return core
}

// futureDirectives are the declared-but-unimplemented directive names.
//
// They are recognized so a document may name one without failing validation,
// and skipped by attribute enforcement because they carry no descriptor yet.
var futureDirectives = map[string]struct{}{
	// Tables
	"table-param":     {},
	"table-env":       {},
	"table-compare":   {},
	"table-error":     {},
	"table-shortcut":  {},
	"table-status":    {},
	"table-registry":  {},
	"table-migration": {},
	"table-timeline":  {},
	"table-perm":      {},
	"table-plan":      {},
	// Code
	"code-source":   {},
	"code-example":  {},
	"code-session":  {},
	"code-repl":     {},
	"code-config":   {},
	"code-diff":     {},
	"code-error":    {},
	"code-schema":   {},
	"code-template": {},
	"code-log":      {},
	"code-query":    {},
	"code-wire":     {},
	"code-build":    {},
	// Lists
	"list-toc":        {},
	"list-check":      {},
	"list-steps":      {},
	"list-faq":        {},
	"list-deps":       {},
	"list-breadcrumb": {},
	"list-related":    {},
	"list-errors":     {},
	"list-decisions":  {},
	"list-reqs":       {},
	"list-api":        {},
	"list-changelog":  {},
	// Callouts
	"callout-example":      {},
	"callout-deprecated":   {},
	"callout-security":     {},
	"callout-perf":         {},
	"callout-compat":       {},
	"callout-experimental": {},
	"callout-see-also":     {},
	"callout-breaking":     {},
	"callout-success":      {},
	"callout-quote":        {},
	// Prose
	"prose-summary":     {},
	"prose-caption":     {},
	"prose-rationale":   {},
	"prose-caveat":      {},
	"prose-migration":   {},
	"prose-changelog":   {},
	"prose-release":     {},
	"prose-prereq":      {},
	"prose-abstract":    {},
	"prose-deprecation": {},
	"prose-attribution": {},
	"prose-definition":  {},
	"prose-annotation":  {},
	"prose-example":     {},
}

// IsFutureDirective reports whether name is a declared-but-unimplemented
// directive.
func IsFutureDirective(name string) bool {
	_, ok := futureDirectives[name]
	return ok
}

// FutureDirectiveNames returns every declared-but-unimplemented directive
// name, sorted.
func FutureDirectiveNames() []string {
	out := make([]string, 0, len(futureDirectives))
	for name := range futureDirectives {
		out = append(out, name)
	}
	sort.Strings(out)
	return out
}

// AllBuiltinDirectives returns the set of every built-in directive name --
// the core catalogue plus the future names -- as a fresh set the caller may
// keep.
//
// This is the name set the directive parser validates against.
func AllBuiltinDirectives() map[string]struct{} {
	out := make(map[string]struct{}, Core().Len()+len(futureDirectives))
	for _, name := range Core().Names() {
		out[name] = struct{}{}
	}
	for name := range futureDirectives {
		out[name] = struct{}{}
	}
	return out
}

// AllBuiltinDirectiveNames returns every built-in directive name, sorted.
func AllBuiltinDirectiveNames() []string {
	set := AllBuiltinDirectives()
	out := make([]string, 0, len(set))
	for name := range set {
		out = append(out, name)
	}
	sort.Strings(out)
	return out
}

// IsBuiltinDirective reports whether name is a core or future built-in.
func IsBuiltinDirective(name string) bool {
	return Core().Has(name) || IsFutureDirective(name)
}

// IsValidDirective reports whether name is a recognized built-in or one of
// customNames. A nil customNames means the project declares no custom
// directives.
func IsValidDirective(name string, customNames map[string]struct{}) bool {
	if IsBuiltinDirective(name) {
		return true
	}
	if customNames != nil {
		if _, ok := customNames[name]; ok {
			return true
		}
	}
	return false
}

// DirectiveStatus returns "core", "future" or "unknown" for name.
//
// Only built-ins are judged; a custom directive is the caller's business and
// reads as unknown here.
func DirectiveStatus(name string) string {
	if Core().Has(name) {
		return "core"
	}
	if IsFutureDirective(name) {
		return "future"
	}
	return "unknown"
}

// DirectiveAttrError reports a directive that used an attribute it does not
// accept, or omitted one it requires.
//
// This is a hard error, distinct from a resolution failure, which is
// warning-level.
type DirectiveAttrError struct {
	Message string
}

func (e *DirectiveAttrError) Error() string { return e.Message }

// ValidateDirectiveAttrs enforces a directive's attribute contract against its
// catalogue spec.
//
// It returns a [DirectiveAttrError] when attrs carries an attribute the
// directive does not accept, or omits one it requires. Only core directives
// have a spec to enforce; custom and future directives are skipped, because
// they define their own attribute contracts.
//
// file and line name the directive's source position in the message.
func ValidateDirectiveAttrs(name string, attrs map[string]string, file string, line int) error {
	spec, ok := Core().Spec(name)
	if !ok {
		return nil
	}

	allowed := make(map[string]struct{}, len(spec.RequiredAttrs)+len(spec.OptionalAttrs))
	for _, a := range spec.RequiredAttrs {
		allowed[a] = struct{}{}
	}
	for _, a := range spec.OptionalAttrs {
		allowed[a] = struct{}{}
	}

	// The attribute order a map iteration gives is arbitrary, and the message
	// names one offending attribute, so the refusal is decided over a sorted
	// pass -- the same occurrence always reports the same attribute.
	present := make([]string, 0, len(attrs))
	for attr := range attrs {
		present = append(present, attr)
	}
	sort.Strings(present)

	for _, attr := range present {
		if _, ok := allowed[attr]; ok {
			continue
		}
		// An actionable migration note for the removed table-commands path
		// attribute.
		if name == "table-commands" && attr == "path" {
			return &DirectiveAttrError{Message: fmt.Sprintf(
				"%s:%d: directive 'table-commands' no longer takes "+
					"'path'; the schema is discovered automatically. Use "+
					`schema-dir="<dir>" only if discovery reports ambiguity.`,
				file, line)}
		}
		allowedDisplay := "(none)"
		if len(allowed) > 0 {
			sorted := make([]string, 0, len(allowed))
			for a := range allowed {
				sorted = append(sorted, a)
			}
			sort.Strings(sorted)
			allowedDisplay = strings.Join(sorted, ", ")
		}
		return &DirectiveAttrError{Message: fmt.Sprintf(
			"%s:%d: directive '%s' has unknown attribute "+
				"'%s'. Allowed attributes: %s.",
			file, line, name, attr, allowedDisplay)}
	}

	for _, req := range spec.RequiredAttrs {
		if _, ok := attrs[req]; !ok {
			return &DirectiveAttrError{Message: fmt.Sprintf(
				"%s:%d: directive '%s' is missing required "+
					"attribute '%s'. Required attributes: %s.",
				file, line, name, req, strings.Join(spec.RequiredAttrs, ", "))}
		}
	}

	return nil
}
