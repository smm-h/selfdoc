// Package python resolves selfdoc's directives against Python source.
//
// # Why python3 runs
//
// Every Python reference page selfdoc has ever produced was rendered from the
// stdlib ast module: ast.unparse decides how an annotation, a default value and
// a base class read, and the tree's child order decides what order the page
// lists symbols in. A re-implementation would have to reproduce both, forever,
// against a language whose syntax moves every release.
//
// So the tree is still read by Python. An embedded driver (driver.py) is run
// under python3 with the file's source on standard input, and prints one JSON
// document carrying what came out of the tree: the docstrings, the rendered
// signatures, the unparsed field types and defaults, the __all__ literal, the
// module-level re-export statements, the declarations' line spans, and the two
// syntactic predicates (dataclass, pydantic model). This package does
// everything a reader sees: which symbols are skipped, how the Markdown is
// assembled, how docstring sections are formatted, and which parameters the
// documentation covers.
//
// The driver runs as a declared read through the effects handle, so a --dry-run
// still renders pages. Its output is cached per file for the life of the
// extractor, because one page asks about the same module several times.
//
// A missing python3, a crashed driver or an unusable document is an error, not
// an empty answer: a Python project whose pages silently lost every symbol
// because the interpreter was absent is worse than a build that stops and says
// so. A file that cannot be read or does not parse is a different thing -- that
// is a property of the file, and it answers empty or renders an error marker,
// as it always has.
package python

import (
	"embed"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/smm-h/selfdoc/internal/effects"
	"github.com/smm-h/selfdoc/internal/extractors"
	"github.com/smm-h/selfdoc/internal/prose"
	"github.com/smm-h/selfdoc/internal/util"
)

//go:embed driver.py
var driverFS embed.FS

// driverSource is the program python3 is handed on its command line.
var driverSource = func() string {
	data, err := driverFS.ReadFile("driver.py")
	if err != nil {
		panic("python: the embedded driver is missing: " + err.Error())
	}
	return string(data)
}()

// driverTimeout bounds one driver run. Parsing one file is milliseconds of
// work, so a run that reaches this bound is a hung interpreter rather than a
// large file.
const driverTimeout = 30 * time.Second

// Extractor reads Python source through the embedded python3 driver.
type Extractor struct {
	extractors.Base

	handle *effects.Handle

	mu       sync.Mutex
	analyses map[string]*analysis
}

// New builds the Python extractor. The handle is what the driver runs through.
func New(handle *effects.Handle) extractors.Extractor {
	if handle == nil {
		handle = effects.Unbound()
	}
	extractor := &Extractor{handle: handle, analyses: map[string]*analysis{}}
	extractor.Base = extractors.NewBase("python", map[string]extractors.Handler{
		"ref":          extractor.handleModule,
		"code-test":    extractor.handleTest,
		"table-schema": extractor.handleSchema,
		"code-help":    extractor.handleCLI,
		"table-config": extractors.HandleTableConfig,
		"prose-desc":   extractor.handleProseDesc,
	})
	return extractor
}

func init() { extractors.Register("python", New) }

// Detect reports whether dir carries a Python project's marker files.
func (e *Extractor) Detect(dir string) bool {
	return extractors.IsFile(util.PathJoin(dir, "pyproject.toml")) ||
		extractors.IsFile(util.PathJoin(dir, "setup.py"))
}

// FileExtensions is the single extension Python owns.
func (e *Extractor) FileExtensions() []string { return []string{".py"} }

// ResolvePath resolves a dotted module path, a package path or a file path to
// a .py file.
func (e *Extractor) ResolvePath(pathArg string, sourcePaths []string, baseDir string) string {
	return resolveModulePath(pathArg, sourcePaths, baseDir)
}

// PublicSymbols lists the symbols a module exports.
//
// A module that defines __all__ as a literal list or tuple of strings is taken
// at its word -- those names ARE its public API, underscore-prefixed ones
// included. Otherwise the heuristic applies: top-level functions and classes
// whose name does not begin with an underscore.
func (e *Extractor) PublicSymbols(file string) ([]string, error) {
	parsed, err := e.analyze(file)
	if err != nil {
		return nil, err
	}
	if !parsed.usable() {
		return nil, nil
	}
	if parsed.Document.AllNames != nil {
		return parsed.Document.AllNames, nil
	}
	var symbols []string
	for _, declaration := range parsed.Document.Declarations {
		if strings.HasPrefix(declaration.Name, "_") {
			continue
		}
		symbols = append(symbols, declaration.Name)
	}
	return symbols, nil
}

// ModuleDocstring is a module's own docstring, with soft-wrapped prose joined.
func (e *Extractor) ModuleDocstring(path string) (string, error) {
	parsed, err := e.analyze(path)
	if err != nil {
		return "", err
	}
	if !parsed.usable() {
		return "", nil
	}
	return prose.JoinWrappedLines(parsed.Document.docstring()), nil
}

// SymbolDetails reports one symbol's parameters and return value.
//
// A dotted name selects a member of a class (MyClass.my_method); a plain name
// is looked for among the top-level functions and classes first, and then
// among each class's methods, in the order the file declares them.
func (e *Extractor) SymbolDetails(file, symbol string) (*extractors.SymbolDetails, error) {
	parsed, err := e.analyze(file)
	if err != nil {
		return nil, err
	}
	if !parsed.usable() {
		return nil, nil
	}
	declarations := parsed.Document.Declarations

	if typeName, memberName, dotted := cutLast(symbol, "."); dotted {
		for _, node := range declarations {
			if node.Kind != "class" || node.Name != typeName {
				continue
			}
			for _, member := range node.Members {
				switch {
				case member.Kind == "function" && member.Name == memberName:
					return buildSymbolDetails(member), nil
				case member.Kind == "class" && member.Name == memberName:
					return classSymbolDetails(member), nil
				}
			}
			return nil, nil
		}
		return nil, nil
	}

	for _, node := range declarations {
		if node.Kind == "function" {
			if node.Name == symbol {
				return buildSymbolDetails(node), nil
			}
			continue
		}
		if node.Name == symbol {
			return classSymbolDetails(node), nil
		}
		for _, member := range node.Members {
			if member.Kind == "function" && member.Name == symbol {
				return buildSymbolDetails(member), nil
			}
		}
	}

	return nil, nil
}

// cutLast splits s at the last occurrence of sep, the operation Python's
// str.rsplit(sep, 1) performs.
func cutLast(s, sep string) (before, after string, found bool) {
	index := strings.LastIndex(s, sep)
	if index < 0 {
		return s, "", false
	}
	return s[:index], s[index+len(sep):], true
}

// analysis is one file as this package sees it: the bytes it read and the
// document the driver printed for them.
type analysis struct {
	// Source is the file's text, empty when ReadError is set.
	Source string
	// ReadError is why the file could not be read, nil when it was.
	ReadError error
	// Document is what the driver printed, nil when ReadError is set.
	Document *driverDocument
}

// usable reports whether the file was read and parsed, which is the
// precondition for every question about its contents.
func (a *analysis) usable() bool {
	return a.ReadError == nil && a.Document != nil && a.Document.SyntaxError == nil
}

// analyze reads a file and parses it through the driver, caching the result.
//
// The cache is per extractor and keyed by the path as the caller spelled it.
// One reference page asks about the same module for its docstring, its symbol
// list and each symbol's details, and a fresh interpreter per question would
// dominate the build.
func (e *Extractor) analyze(filePath string) (*analysis, error) {
	e.mu.Lock()
	cached, ok := e.analyses[filePath]
	e.mu.Unlock()
	if ok {
		return cached, nil
	}

	data, readErr := os.ReadFile(filePath)
	if readErr != nil {
		result := &analysis{ReadError: readErr}
		e.remember(filePath, result)
		return result, nil
	}

	document, err := e.runDriver(filePath, string(data))
	if err != nil {
		return nil, err
	}
	result := &analysis{Source: string(data), Document: document}
	e.remember(filePath, result)
	return result, nil
}

func (e *Extractor) remember(filePath string, result *analysis) {
	e.mu.Lock()
	e.analyses[filePath] = result
	e.mu.Unlock()
}

// runDriver runs the embedded driver over source and decodes its document.
func (e *Extractor) runDriver(displayPath, source string) (*driverDocument, error) {
	result, err := e.handle.Run(
		[]string{"python3", "-c", driverSource, displayPath},
		effects.Read(),
		effects.CaptureOutput(),
		effects.Stdin([]byte(source)),
		effects.Timeout(driverTimeout),
	)
	if err != nil {
		return nil, fmt.Errorf("reading %s: running python3: %w", displayPath, err)
	}
	if result.ExitCode != 0 {
		return nil, fmt.Errorf(
			"reading %s: the embedded python3 driver exited %d: %s",
			displayPath, result.ExitCode, strings.TrimSpace(string(result.Stderr)),
		)
	}

	var document driverDocument
	if err := json.Unmarshal(result.Stdout, &document); err != nil {
		return nil, fmt.Errorf(
			"reading %s: the embedded python3 driver printed no usable document: %w",
			displayPath, err,
		)
	}
	return &document, nil
}

// driverDocument is what driver.py prints for one file.
type driverDocument struct {
	// SyntaxError is Python's own rendering of the parse failure, nil when the
	// file parsed.
	SyntaxError *string `json:"syntax_error"`
	// Docstring is the module docstring, nil when the module has none.
	Docstring *string `json:"docstring"`
	// AllNames is the module's __all__ when it is a literal list or tuple of
	// strings. It is nil both when there is no __all__ and when there is one
	// that is not such a literal -- the two cases the heuristic covers alike.
	AllNames []string `json:"all_names"`
	// Declarations are the module's top-level functions and classes, in source
	// order.
	Declarations []declaration `json:"declarations"`
	// Reexports are the module-level re-export statements and constants, in
	// source order, including the ones nested one level inside a top-level try
	// or if.
	Reexports []reexport `json:"reexports"`
	// CLIConstants are the module-level HELP and USAGE string constants.
	CLIConstants []cliConstant `json:"cli_constants"`
}

// docstring is the module docstring, empty when there is none.
func (d *driverDocument) docstring() string {
	if d.Docstring == nil {
		return ""
	}
	return *d.Docstring
}

// declaration is one function or class the driver read out of the tree.
type declaration struct {
	// Kind is "function" or "class".
	Kind string `json:"kind"`
	// Name is the declared name.
	Name string `json:"name"`
	// IsAsync reports an "async def", which the rendered signature spells out.
	IsAsync bool `json:"is_async"`
	// Doc is the declaration's own docstring, nil when it has none.
	Doc *string `json:"doc"`
	// Signature is the parenthesized parameter list and return annotation, as
	// ast.unparse renders their parts. Functions only.
	Signature string `json:"signature"`
	// ClassSignature is the "class Name(Base):" line. Classes only.
	ClassSignature string `json:"class_signature"`
	// Lineno and EndLineno are the declaration's inclusive one-based line span,
	// which is what a code-test directive slices out of the source.
	Lineno    int `json:"lineno"`
	EndLineno int `json:"end_lineno"`
	// IsDataclass and IsPydantic are the two syntactic predicates that decide
	// whether a docstring-less class renders a field table. Classes only.
	IsDataclass bool `json:"is_dataclass"`
	IsPydantic  bool `json:"is_pydantic"`
	// Fields are the class's annotated assignments. Classes only.
	Fields []field `json:"fields"`
	// Members are the class's own functions and classes, in source order.
	// Classes only.
	Members []declaration `json:"members"`
	// Params are the parameters a symbol-details report names. Functions only.
	Params []driverParam `json:"params"`
	// ReturnType is the declared return annotation, nil when there is none.
	// Functions only.
	ReturnType *string `json:"return_type"`
}

// documented is the declaration's docstring, empty when it has none. An empty
// docstring and an absent one are the same thing to every caller here, which
// is why this collapses them.
func (d *declaration) documented() string {
	if d.Doc == nil {
		return ""
	}
	return *d.Doc
}

// field is one annotated assignment in a class body.
type field struct {
	// Name is the field name.
	Name string `json:"name"`
	// Type is the unparsed annotation.
	Type string `json:"type"`
	// Default is the unparsed default value, empty when the field has none.
	Default string `json:"default"`
	// Lineno is the field's one-based line, which is where an inline comment
	// documenting it would be.
	Lineno int `json:"lineno"`
}

// reexport is one module-level re-export or constant, with the source line that
// declares it.
type reexport struct {
	Name string `json:"name"`
	Stub string `json:"stub"`
}

// cliConstant is one module-level HELP or USAGE string.
type cliConstant struct {
	Name  string `json:"name"`
	Value string `json:"value"`
}

// driverParam is one parameter as the driver read it, before this package
// decides whether the documentation covers it.
type driverParam struct {
	// Name carries the variadic or keyword prefix the signature writes.
	Name string `json:"name"`
	// Type is the unparsed annotation, nil when the parameter has none.
	Type *string `json:"type"`
}

// buildSymbolDetails reports a function's parameters and return value, marking
// each against what its own docstring documents.
func buildSymbolDetails(node declaration) *extractors.SymbolDetails {
	sections := extractors.ParseDocstringSections(node.documented())

	documentedNames := map[string]bool{}
	for _, param := range sections.Params {
		documentedNames[param.Name] = true
	}

	params := make([]extractors.SymbolParam, 0, len(node.Params))
	for _, param := range node.Params {
		bare := strings.TrimLeft(param.Name, "*")
		params = append(params, extractors.SymbolParam{
			Name:       param.Name,
			Type:       param.Type,
			Documented: documentedNames[bare] || documentedNames[param.Name],
		})
	}

	return &extractors.SymbolDetails{
		Params:           params,
		ReturnType:       node.ReturnType,
		ReturnDocumented: sections.Returns != nil,
	}
}

// classSymbolDetails reports a class's constructor as the class's own
// parameters. A class with no __init__ takes none, and there is nothing about
// its return value left to document.
func classSymbolDetails(node declaration) *extractors.SymbolDetails {
	for _, member := range node.Members {
		if member.Kind == "function" && !member.IsAsync && member.Name == "__init__" {
			return buildSymbolDetails(member)
		}
	}
	return &extractors.SymbolDetails{ReturnDocumented: true}
}

// resolveModulePath resolves a module argument to a .py file.
//
// A dotted path is tried as a module and then as a package under each declared
// source path and then under the base directory; a path already ending in .py
// is tried as a file last.
func resolveModulePath(arg string, sourcePaths []string, baseDir string) string {
	dottedAsPath := strings.ReplaceAll(arg, ".", "/") + ".py"
	dottedAsPackage := strings.ReplaceAll(arg, ".", "/") + "/__init__.py"

	var candidates []string
	for _, sourcePath := range sourcePaths {
		candidates = append(candidates,
			util.PathJoin(baseDir, sourcePath, dottedAsPath),
			util.PathJoin(baseDir, sourcePath, dottedAsPackage),
		)
	}
	candidates = append(candidates,
		util.PathJoin(baseDir, dottedAsPath),
		util.PathJoin(baseDir, dottedAsPackage),
	)

	if strings.HasSuffix(arg, ".py") {
		candidates = append(candidates, util.PathJoin(baseDir, arg))
		for _, sourcePath := range sourcePaths {
			candidates = append(candidates, util.PathJoin(baseDir, sourcePath, arg))
		}
	}

	for _, candidate := range candidates {
		if extractors.IsFile(candidate) {
			return candidate
		}
	}

	return ""
}
