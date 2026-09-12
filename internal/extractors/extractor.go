package extractors

// Extractor is the protocol every language extractor implements.
//
// The methods split into three groups. Name and Detect identify the language.
// Extract resolves one directive into Markdown. The rest answer the discovery
// questions the coverage, quality and staleness measurements ask.
//
// Three methods return an error where the Python protocol they replace returned
// an empty result: the Python extractor answers them by running an embedded
// driver under python3, and a missing interpreter or a crashed driver is a
// broken installation, not a file with no symbols in it. A file that cannot be
// read, or whose contents do not parse, still answers empty -- that is a
// property of the file and every extractor reports it that way.
type Extractor interface {
	// Name is the language's registry name, as selfdoc.json spells it.
	Name() string

	// Detect reports whether dir looks like a project in this language,
	// by the presence of the language's own marker files.
	Detect(dir string) bool

	// ResolvePath resolves a directive's path argument to a filesystem path,
	// trying each of sourcePaths as a prefix and then baseDir directly.
	// It returns the empty string when nothing resolves.
	ResolvePath(pathArg string, sourcePaths []string, baseDir string) string

	// Extract resolves one directive into the Markdown that replaces it.
	//
	// A directive that cannot be resolved -- a missing file, a syntax error, an
	// unknown directive name -- returns an error marker as its Markdown and a
	// nil error, so one bad directive degrades one region of one page instead of
	// failing the build. The error return is for a broken toolchain.
	Extract(directiveName string, attrs map[string]string, body []string, sourcePaths []string, baseDir string) (string, error)

	// FileExtensions lists the file extensions this language owns, each with
	// its leading dot.
	FileExtensions() []string

	// PublicSymbols lists the symbols file exports, in source order.
	PublicSymbols(file string) ([]string, error)

	// SymbolDetails reports what file says about symbol's parameters and return
	// value. It returns nil when the symbol is not in the file. A dotted name
	// selects a member of a type ("Pipeline.Execute").
	SymbolDetails(file, symbol string) (*SymbolDetails, error)

	// ModuleDocstring is the module- or package-level documentation at path,
	// with soft-wrapped prose joined so a wrapped first sentence reads as one.
	ModuleDocstring(path string) (string, error)
}

// Handler resolves one directive for one language. It is the value type of an
// extractor's dispatch table.
//
// target is nil when the directive declared no target attribute, which is a
// different question from an empty target: a code-test directive with no target
// renders the whole file, while an empty one looks for a symbol with no name.
//
// The error return is for a broken toolchain, never for an unresolvable
// directive -- see Extractor.Extract.
type Handler func(
	path string,
	target *string,
	body []string,
	sourcePaths []string,
	baseDir string,
	attrs map[string]string,
) (string, error)

// SymbolDetails is what an extractor reads out of source about one symbol's
// parameters and return value, together with whether the symbol's own
// documentation covers them. The quality measurement scores a symbol from it.
type SymbolDetails struct {
	// Params are the symbol's parameters in declaration order, with a
	// receiver, self and cls already dropped.
	Params []SymbolParam
	// ReturnType is the declared return type, nil when the symbol declares
	// none.
	ReturnType *string
	// ReturnDocumented reports whether the documentation says what the symbol
	// returns.
	ReturnDocumented bool
}

// SymbolParam is one parameter of a symbol, as SymbolDetails reports it.
type SymbolParam struct {
	// Name is the parameter name, carrying its variadic or keyword prefix
	// ("*args", "**kwargs") where the language writes one.
	Name string
	// Type is the declared type, nil when the parameter declares none.
	Type *string
	// Documented reports whether the symbol's documentation names this
	// parameter.
	Documented bool
}
