package extractors

// Base carries the behavior every language extractor shares: the directive
// dispatch table and the no-op answers to the optional protocol methods.
//
// A language package embeds it, builds it with NewBase, and overrides whichever
// of the optional methods its language can answer. Name comes from the
// language it was built with, so the unknown-directive message names the right
// extractor without the language package restating it.
type Base struct {
	language string
	handlers map[string]Handler
}

// NewBase builds the shared part of a language extractor from the language's
// registry name and its directive dispatch table.
//
// The handlers usually close over the extractor being constructed, so the
// normal shape is to allocate the extractor first and assign its Base second.
func NewBase(language string, handlers map[string]Handler) Base {
	return Base{language: language, handlers: handlers}
}

// Name is the language's registry name.
func (b Base) Name() string { return b.language }

// Extract dispatches a directive to the handler registered for it, passing the
// path and target attributes out as their own arguments because every handler
// reads them.
//
// A directive name with no handler renders an error marker naming both the
// directive and the language, since the same name can be valid for another
// language.
func (b Base) Extract(
	directiveName string,
	attrs map[string]string,
	body []string,
	sourcePaths []string,
	baseDir string,
) (string, error) {
	path := attrs["path"]
	var target *string
	if value, ok := attrs["target"]; ok {
		target = &value
	}

	handler, ok := b.handlers[directiveName]
	if !ok {
		return FormatError(
			"unknown directive '" + directiveName + "' for " + b.language + " extractor",
		), nil
	}
	return handler(path, target, body, sourcePaths, baseDir, attrs)
}

// FileExtensions reports that the language claims no file extensions.
func (b Base) FileExtensions() []string { return nil }

// PublicSymbols reports no symbols, for a language whose extractor cannot read
// them.
func (b Base) PublicSymbols(string) ([]string, error) { return nil, nil }

// ResolvePath resolves nothing, for a language whose extractor has no path
// convention.
func (b Base) ResolvePath(string, []string, string) string { return "" }

// SymbolDetails reports nothing, for a language whose extractor cannot read
// signatures.
func (b Base) SymbolDetails(string, string) (*SymbolDetails, error) { return nil, nil }

// ModuleDocstring reports no module documentation, for a language whose
// extractor cannot read it.
func (b Base) ModuleDocstring(string) (string, error) { return "", nil }
