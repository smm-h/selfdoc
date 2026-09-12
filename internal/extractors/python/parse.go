package python

// Reading one Python file's syntax tree.
//
// This is what the embedded python3 driver used to print: the module
// docstring, __all__, the top-level functions and classes in source order with
// their signatures and line spans, the class fields, the module-level
// re-export statements, and the two syntactic predicates (dataclass, pydantic
// model). It is built here from a tree-sitter parse instead, so documenting
// Python needs no interpreter.
//
// The shape follows CPython's ast, not the grammar's: a decorated definition is
// the definition, an annotated assignment is one statement kind, and only the
// direct children of a module or a class body count as its declarations. Where
// the two disagree, ast wins -- the pages were written against it.

import (
	"fmt"
	"strings"
	"sync"

	"github.com/odvcencio/gotreesitter"
	"github.com/odvcencio/gotreesitter/grammars"
)

// pythonGrammar is the loaded Python grammar. Loading decodes the embedded
// table blob, so it happens once for the life of the process.
var pythonGrammar = sync.OnceValue(grammars.PythonLanguage)

// skipNames are the parameters a symbol-details report drops from the
// positional groups.
var skipNames = map[string]bool{"self": true, "cls": true}

// parseDocument reads one file's tree and reports what the reference pages ask
// of it. displayPath names the file in a syntax-error message, the way the
// interpreter's own message named it.
//
// A file that does not parse answers a document carrying nothing but the
// error: that is a property of the file, and every caller renders a marker for
// it. A parser that cannot run at all is an error instead.
func parseDocument(displayPath string, source []byte) (*document, error) {
	parser := gotreesitter.NewParser(pythonGrammar())
	tree, err := parser.Parse(source)
	if err != nil {
		return nil, fmt.Errorf("reading %s: parsing Python: %w", displayPath, err)
	}
	root := tree.RootNode()
	if root == nil {
		return nil, fmt.Errorf("reading %s: the Python parser produced no tree", displayPath)
	}

	r := &reader{lang: pythonGrammar(), source: source}

	if root.HasErrorOrMissing() {
		message := fmt.Sprintf("invalid syntax (%s, line %d)", displayPath, r.firstErrorLine(root))
		return &document{SyntaxError: &message}, nil
	}

	statements := r.statements(root)
	doc := &document{
		Docstring:    r.blockDocstring(statements),
		AllNames:     r.allLiteralNames(statements),
		Declarations: r.declarations(statements),
		Reexports:    r.reexportStubs(statements),
		CLIConstants: r.cliConstants(statements),
	}
	return doc, nil
}

// FirstSyntaxErrorLine reports whether source fails to parse, and the one-based
// line the first failure sits on.
//
// It is the syntax question on its own, for a caller that wants nothing else
// out of the file -- the documentation-example check, which asks it of a fenced
// code block rather than of a module.
//
// Indentation is not a failure here. The grammar admits a fragment lifted out
// of a function, an unexpected indent, a dedent matching no outer level and a
// block that was never indented at all, where CPython raises IndentationError
// for each. The example check exempted those anyway, so the exemption is now
// structural rather than a case it has to recognize.
func FirstSyntaxErrorLine(source []byte) (line int, failed bool, err error) {
	parser := gotreesitter.NewParser(pythonGrammar())
	tree, parseErr := parser.Parse(source)
	if parseErr != nil {
		return 0, false, fmt.Errorf("parsing Python: %w", parseErr)
	}
	root := tree.RootNode()
	if root == nil {
		return 0, false, fmt.Errorf("the Python parser produced no tree")
	}
	if !root.HasErrorOrMissing() {
		return 0, false, nil
	}
	r := &reader{lang: pythonGrammar(), source: source}
	return r.firstErrorLine(root), true, nil
}

// firstErrorLine is the one-based line of the first error or missing node,
// which is the closest this parser comes to the line the interpreter named.
func (r *reader) firstErrorLine(root *gotreesitter.Node) int {
	var found *gotreesitter.Node
	var walk func(n *gotreesitter.Node)
	walk = func(n *gotreesitter.Node) {
		if found != nil {
			return
		}
		if n.IsError() || n.IsMissing() {
			found = n
			return
		}
		if !n.HasErrorOrMissing() {
			return
		}
		for i := 0; i < n.ChildCount(); i++ {
			walk(n.Child(i))
		}
	}
	walk(root)
	if found == nil {
		return 1
	}
	return int(found.StartPoint().Row) + 1
}

// statements are a module's or a block's statements in source order, with the
// comments dropped and the grammar's expression-statement wrapper removed.
func (r *reader) statements(block *gotreesitter.Node) []*gotreesitter.Node {
	if block == nil {
		return nil
	}
	var kept []*gotreesitter.Node
	for _, child := range r.named(block) {
		if r.kind(child) == "expression_statement" {
			inner := r.named(child)
			if len(inner) == 1 {
				kept = append(kept, inner[0])
				continue
			}
			kept = append(kept, inner...)
			continue
		}
		kept = append(kept, child)
	}
	return kept
}

// definitionOf unwraps a decorated definition, which ast carries as the
// definition itself with its decorators hanging off it.
func (r *reader) definitionOf(n *gotreesitter.Node) *gotreesitter.Node {
	if r.kind(n) == "decorated_definition" {
		if inner := r.field(n, "definition"); inner != nil {
			return inner
		}
	}
	return n
}

// decoratorsOf are the decorator expressions attached to a definition.
func (r *reader) decoratorsOf(n *gotreesitter.Node) []*gotreesitter.Node {
	parent := n.Parent()
	if parent == nil || r.kind(parent) != "decorated_definition" {
		return nil
	}
	var expressions []*gotreesitter.Node
	for _, child := range r.named(parent) {
		if r.kind(child) != "decorator" {
			continue
		}
		if inner := r.named(child); len(inner) > 0 {
			expressions = append(expressions, inner[0])
		}
	}
	return expressions
}

// blockDocstring is ast.get_docstring for a body: the first statement when it
// is a plain string constant, cleaned the way inspect.cleandoc cleans it.
func (r *reader) blockDocstring(statements []*gotreesitter.Node) *string {
	if len(statements) == 0 {
		return nil
	}
	first := statements[0]
	if !r.isStringConstant(first) {
		return nil
	}
	cleaned := cleanDoc(r.stringConstantValue(first))
	return &cleaned
}

// declarations are the functions and classes a body declares, in source order.
func (r *reader) declarations(statements []*gotreesitter.Node) []declaration {
	var declared []declaration
	for _, statement := range statements {
		if node, ok := r.declaration(statement); ok {
			declared = append(declared, node)
		}
	}
	return declared
}

// declaration renders one function or class statement.
func (r *reader) declaration(statement *gotreesitter.Node) (declaration, bool) {
	node := r.definitionOf(statement)
	switch r.kind(node) {
	case "function_definition":
		body := r.statements(r.field(node, "body"))
		return declaration{
			Kind:       "function",
			Name:       r.text(r.field(node, "name")),
			IsAsync:    strings.HasPrefix(r.text(node), "async"),
			Doc:        r.blockDocstring(body),
			Signature:  r.buildSignature(node),
			Lineno:     lineOf(node),
			EndLineno:  r.endLineOf(node),
			Params:     r.detailsParams(node),
			ReturnType: r.returnAnnotation(node),
		}, true

	case "class_definition":
		body := r.statements(r.field(node, "body"))
		return declaration{
			Kind:           "class",
			Name:           r.text(r.field(node, "name")),
			Doc:            r.blockDocstring(body),
			ClassSignature: r.classSignature(node),
			Lineno:         lineOf(node),
			EndLineno:      r.endLineOf(node),
			IsDataclass:    r.isDataclass(node),
			IsPydantic:     r.isPydanticModel(node),
			Fields:         r.annotatedFields(body),
			Members:        r.declarations(body),
		}, true
	}
	return declaration{}, false
}

// lineOf is a node's one-based first line.
func lineOf(n *gotreesitter.Node) int { return int(n.StartPoint().Row) + 1 }

// endLineOf is a node's one-based last line, ignoring the comments trailing
// it. The grammar attaches a comment that follows the last statement of a
// block to the block; ast has no node for a comment at all, so a declaration
// that ends with commented-out code ends at its last statement.
func (r *reader) endLineOf(n *gotreesitter.Node) int {
	for i := n.ChildCount() - 1; i >= 0; i-- {
		child := n.Child(i)
		if isTrivia(r.kind(child)) {
			continue
		}
		return r.endLineOf(child)
	}
	return int(n.EndPoint().Row) + 1
}

// annotation renders a node's type field, empty when it carries none.
func (r *reader) annotation(n *gotreesitter.Node) string {
	typed := r.field(n, "type")
	if typed == nil {
		return ""
	}
	return r.unparse(typed)
}

// returnAnnotation is a function's declared return type, nil when it declares
// none.
func (r *reader) returnAnnotation(fn *gotreesitter.Node) *string {
	returns := r.field(fn, "return_type")
	if returns == nil {
		return nil
	}
	rendered := r.unparse(returns)
	if rendered == "" {
		return nil
	}
	return &rendered
}

// buildSignature builds the parenthesized signature the reference pages print.
//
// The parameters are written in the order the tree carries them, which is the
// order ast writes them in too: the positional group, the positional-only
// marker, the variadic or the bare star, the keyword-only group, and the
// keyword catch-all.
func (r *reader) buildSignature(fn *gotreesitter.Node) string {
	signature := "(" + strings.Join(r.renderParams(r.field(fn, "parameters")), ", ") + ")"
	if returns := r.returnAnnotation(fn); returns != nil {
		signature += " -> " + *returns
	}
	return signature
}

// renderParams renders each parameter of a parameter list.
func (r *reader) renderParams(params *gotreesitter.Node) []string {
	if params == nil {
		return nil
	}
	var rendered []string
	for _, param := range r.named(params) {
		rendered = append(rendered, r.renderParam(param))
	}
	return rendered
}

// renderParam renders one parameter: its name with any variadic prefix, its
// annotation, and its default -- the default with no spaces around the equals
// sign, which is what the pages have always shown.
func (r *reader) renderParam(param *gotreesitter.Node) string {
	switch r.kind(param) {
	case "positional_separator":
		return "/"
	case "keyword_separator":
		return "*"
	case "list_splat_pattern":
		return "*" + r.text(r.splatValue(param))
	case "dictionary_splat_pattern":
		return "**" + r.text(r.splatValue(param))
	case "typed_parameter":
		name := ""
		if inner := r.namedParamTarget(param); inner != nil {
			name = r.renderParam(inner)
		}
		if annotation := r.annotation(param); annotation != "" {
			return name + ": " + annotation
		}
		return name
	case "default_parameter", "typed_default_parameter":
		part := r.text(r.field(param, "name"))
		if annotation := r.annotation(param); annotation != "" {
			part += ": " + annotation
		}
		if value := r.field(param, "value"); value != nil {
			part += "=" + r.unparse(value)
		}
		return part
	default:
		return r.text(param)
	}
}

// namedParamTarget is the name a typed parameter annotates, which may itself
// carry a variadic prefix.
func (r *reader) namedParamTarget(param *gotreesitter.Node) *gotreesitter.Node {
	for _, child := range r.named(param) {
		switch r.kind(child) {
		case "identifier", "list_splat_pattern", "dictionary_splat_pattern", "tuple_pattern":
			return child
		}
	}
	return nil
}

// paramName is a parameter's declared name with its variadic prefix, and
// whether it is one of the variadic forms.
func (r *reader) paramName(param *gotreesitter.Node) (name string, prefix string) {
	switch r.kind(param) {
	case "identifier":
		return r.text(param), ""
	case "list_splat_pattern":
		return r.text(r.splatValue(param)), "*"
	case "dictionary_splat_pattern":
		return r.text(r.splatValue(param)), "**"
	case "default_parameter", "typed_default_parameter":
		return r.text(r.field(param, "name")), ""
	case "typed_parameter":
		if inner := r.namedParamTarget(param); inner != nil {
			return r.paramName(inner)
		}
	}
	return r.text(param), ""
}

// detailsParams are the parameters a symbol-details report names, in
// declaration order.
//
// self and cls are dropped from the positional groups only -- a keyword-only
// parameter that happens to be spelled self is still a parameter -- and the
// variadic and keyword catch-alls carry the prefix the signature writes.
func (r *reader) detailsParams(fn *gotreesitter.Node) []paramInfo {
	params := r.field(fn, "parameters")
	if params == nil {
		return nil
	}
	var reported []paramInfo
	keywordOnly := false
	for _, param := range r.named(params) {
		kind := r.kind(param)
		if kind == "positional_separator" {
			continue
		}
		if kind == "keyword_separator" {
			keywordOnly = true
			continue
		}
		name, prefix := r.paramName(param)
		if prefix == "*" {
			// Everything after a variadic is keyword-only.
			keywordOnly = true
		}
		if prefix == "" && !keywordOnly && skipNames[name] {
			continue
		}
		var annotation *string
		if rendered := r.annotation(param); rendered != "" {
			annotation = &rendered
		}
		reported = append(reported, paramInfo{Name: prefix + name, Type: annotation})
	}
	return reported
}

// classSignature builds the "class Name(Base1, Base2):" line.
func (r *reader) classSignature(node *gotreesitter.Node) string {
	name := r.text(r.field(node, "name"))
	// The bases come first and the keywords after, whatever order they were
	// written in: they are two lists on the class node, and a star-arg written
	// after a keyword moves ahead of it.
	var bases, keywords []string
	if superclasses := r.field(node, "superclasses"); superclasses != nil {
		for _, base := range r.named(superclasses) {
			switch r.kind(base) {
			case "keyword_argument":
				keywords = append(keywords,
					r.text(r.field(base, "name"))+"="+r.unparse(r.field(base, "value")))
			case "dictionary_splat":
				keywords = append(keywords, "**"+r.unparse(r.splatValue(base)))
			default:
				bases = append(bases, r.unparse(base))
			}
		}
	}
	bases = append(bases, keywords...)
	if len(bases) == 0 {
		return "class " + name + ":"
	}
	return "class " + name + "(" + strings.Join(bases, ", ") + "):"
}

// isDataclass reports whether a class carries a @dataclass decorator: the bare
// name, a call to it, or a call to dataclasses.dataclass.
func (r *reader) isDataclass(node *gotreesitter.Node) bool {
	for _, decorator := range r.decoratorsOf(node) {
		if r.kind(decorator) == "identifier" && r.text(decorator) == "dataclass" {
			return true
		}
		if r.kind(decorator) != "call" {
			// A bare dotted decorator (@dataclasses.dataclass) is deliberately
			// not recognized: the predicate reads a plain name, or a call --
			// including a dotted one -- and nothing else.
			continue
		}
		function := r.field(decorator, "function")
		if function == nil {
			continue
		}
		switch r.kind(function) {
		case "identifier":
			if r.text(function) == "dataclass" {
				return true
			}
		case "attribute":
			object := r.field(function, "object")
			attribute := r.field(function, "attribute")
			if object != nil && attribute != nil &&
				r.text(attribute) == "dataclass" &&
				r.kind(object) == "identifier" && r.text(object) == "dataclasses" {
				return true
			}
		}
	}
	return false
}

// isPydanticModel reports whether a class looks like a pydantic BaseModel
// subclass.
//
// A base-class name check covers pydantic.BaseModel, aliased imports and plain
// BaseModel. A nested class Config or a model_config assignment is the
// secondary signal, which config-bearing models carry even when the base class
// is the project's own intermediate base. This is a single-hop syntactic
// check, not a resolved method resolution order.
func (r *reader) isPydanticModel(node *gotreesitter.Node) bool {
	if superclasses := r.field(node, "superclasses"); superclasses != nil {
		for _, base := range r.named(superclasses) {
			switch r.kind(base) {
			case "identifier":
				if r.text(base) == "BaseModel" {
					return true
				}
			case "attribute":
				if attribute := r.field(base, "attribute"); attribute != nil &&
					r.text(attribute) == "BaseModel" {
					return true
				}
			}
		}
	}

	for _, statement := range r.statements(r.field(node, "body")) {
		inner := r.definitionOf(statement)
		if r.kind(inner) == "class_definition" && r.text(r.field(inner, "name")) == "Config" {
			return true
		}
		if r.kind(statement) != "assignment" || r.field(statement, "type") != nil {
			continue
		}
		for _, target := range r.assignmentTargets(statement) {
			if r.kind(target) == "identifier" && r.text(target) == "model_config" {
				return true
			}
		}
	}
	return false
}

// annotatedFields are the annotated assignments a class body declares, with
// the line each sits on.
func (r *reader) annotatedFields(statements []*gotreesitter.Node) []field {
	var fields []field
	for _, statement := range statements {
		if r.kind(statement) != "assignment" || r.field(statement, "type") == nil {
			continue
		}
		target := r.field(statement, "left")
		if target == nil || r.kind(target) != "identifier" {
			continue
		}
		value := ""
		if right := r.field(statement, "right"); right != nil {
			value = r.unparse(right)
		}
		fields = append(fields, field{
			Name:    r.text(target),
			Type:    r.annotation(statement),
			Default: value,
			Lineno:  lineOf(statement),
		})
	}
	return fields
}

// assignmentTargets are the names an assignment binds. A chained assignment is
// one statement with several targets to ast, and a right-nested chain of
// assignments to the grammar.
func (r *reader) assignmentTargets(statement *gotreesitter.Node) []*gotreesitter.Node {
	var targets []*gotreesitter.Node
	current := statement
	for current != nil && r.kind(current) == "assignment" {
		if left := r.field(current, "left"); left != nil {
			targets = append(targets, left)
		}
		right := r.field(current, "right")
		if right == nil || r.kind(right) != "assignment" {
			break
		}
		current = right
	}
	return targets
}

// assignmentValue is the value a (possibly chained) assignment binds.
func (r *reader) assignmentValue(statement *gotreesitter.Node) *gotreesitter.Node {
	current := statement
	for {
		right := r.field(current, "right")
		if right == nil {
			return nil
		}
		if r.kind(right) != "assignment" {
			return right
		}
		current = right
	}
}

// allLiteralNames is the module's __all__ when it is a literal list or tuple
// of string constants.
//
// nil covers both "no __all__" and "an __all__ that is not such a literal";
// the caller falls back to a heuristic either way. An empty but literal
// __all__ is a declaration that the module exports nothing, and answers an
// empty list rather than nil.
func (r *reader) allLiteralNames(statements []*gotreesitter.Node) []string {
	for _, statement := range statements {
		if r.kind(statement) != "assignment" || r.field(statement, "type") != nil {
			continue
		}
		named := false
		for _, target := range r.assignmentTargets(statement) {
			if r.kind(target) == "identifier" && r.text(target) == "__all__" {
				named = true
			}
		}
		if !named {
			continue
		}
		value := r.assignmentValue(statement)
		if value == nil {
			continue
		}
		switch r.kind(value) {
		case "list", "tuple", "expression_list":
			// The bare comma-separated form is a tuple to ast too.
		default:
			continue
		}
		names := []string{}
		for _, element := range r.named(value) {
			if !r.isStringConstant(element) {
				return nil
			}
			names = append(names, r.stringConstantValue(element))
		}
		return names
	}
	return nil
}

// reexportCandidates are the module-level import-from and assignment
// statements, including the ones nested one level inside a top-level try or
// if.
//
// That covers the "try: from ._impl import X except ImportError:" fallback and
// the "if TYPE_CHECKING:" guard. Deeper nesting is not descended into -- and
// an elif's body is deeper, because ast carries an elif as an if nested inside
// the outer one's else.
func (r *reader) reexportCandidates(statements []*gotreesitter.Node) []*gotreesitter.Node {
	var candidates []*gotreesitter.Node
	admit := func(statement *gotreesitter.Node) {
		switch r.kind(statement) {
		case "import_from_statement", "future_import_statement", "assignment":
			candidates = append(candidates, statement)
		}
	}
	for _, statement := range statements {
		switch r.kind(statement) {
		case "import_from_statement", "future_import_statement", "assignment":
			candidates = append(candidates, statement)
		case "try_statement":
			for _, child := range r.named(statement) {
				if r.kind(child) == "block" {
					for _, nested := range r.statements(child) {
						admit(nested)
					}
					continue
				}
				for _, block := range r.named(child) {
					if r.kind(block) == "block" {
						for _, nested := range r.statements(block) {
							admit(nested)
						}
					}
				}
			}
		case "if_statement":
			for _, nested := range r.statements(r.field(statement, "consequence")) {
				admit(nested)
			}
			hasElif := false
			for _, child := range r.named(statement) {
				if r.kind(child) == "elif_clause" {
					hasElif = true
				}
			}
			if hasElif {
				continue
			}
			for _, child := range r.named(statement) {
				if r.kind(child) != "else_clause" {
					continue
				}
				for _, block := range r.named(child) {
					if r.kind(block) == "block" {
						for _, nested := range r.statements(block) {
							admit(nested)
						}
					}
				}
			}
		}
	}
	return candidates
}

// reexportStubs are the (name, source line) pairs for the module-level
// re-exports and constants.
//
// A star import is skipped: it is unresolvable, and its names would not appear
// in a literal __all__ extraction anyway.
func (r *reader) reexportStubs(statements []*gotreesitter.Node) []reexport {
	var stubs []reexport
	for _, statement := range r.reexportCandidates(statements) {
		if kind := r.kind(statement); kind == "import_from_statement" ||
			kind == "future_import_statement" {
			prefix := "from " + r.importModuleName(statement) + " import "
			for _, imported := range r.fieldAll(statement, "name") {
				if r.kind(imported) == "wildcard_import" {
					continue
				}
				name, spelled := r.importedName(imported)
				stubs = append(stubs, reexport{Name: name, Stub: prefix + spelled})
			}
			continue
		}
		stub := r.assignmentStub(statement)
		for _, target := range r.assignmentTargets(statement) {
			if r.kind(target) != "identifier" {
				continue
			}
			stubs = append(stubs, reexport{Name: r.text(target), Stub: stub})
		}
	}
	return stubs
}

// importModuleName is the dotted module an import-from names, with its leading
// dots. The future import carries its module as a keyword rather than a named
// child, and ast reads it as the ordinary module name it spells.
func (r *reader) importModuleName(statement *gotreesitter.Node) string {
	if r.kind(statement) == "future_import_statement" {
		return "__future__"
	}
	module := r.field(statement, "module_name")
	if module == nil {
		return ""
	}
	if r.kind(module) != "relative_import" {
		return r.text(module)
	}
	name := ""
	for _, child := range r.named(module) {
		switch r.kind(child) {
		case "import_prefix":
			name += r.text(child)
		default:
			name += r.text(child)
		}
	}
	return name
}

// importedName is what one imported alias binds, and how the import line
// spells it.
func (r *reader) importedName(imported *gotreesitter.Node) (name, spelled string) {
	if r.kind(imported) != "aliased_import" {
		text := r.text(imported)
		return text, text
	}
	original := r.text(r.field(imported, "name"))
	alias := r.text(r.field(imported, "alias"))
	return alias, original + " as " + alias
}

// assignmentStub renders an assignment the way ast.unparse renders the
// statement: every target, then the value -- or the annotated form when the
// statement carries a type.
func (r *reader) assignmentStub(statement *gotreesitter.Node) string {
	if r.field(statement, "type") != nil {
		stub := r.expr(r.field(statement, "left"), precTest) + ": " + r.annotation(statement)
		if value := r.field(statement, "right"); value != nil {
			stub += " = " + r.unparse(value)
		}
		return stub
	}
	var parts []string
	for _, target := range r.assignmentTargets(statement) {
		parts = append(parts, r.expr(target, precTuple))
	}
	value := r.assignmentValue(statement)
	return strings.Join(parts, " = ") + " = " + r.unparse(value)
}

// cliConstants are the module-level HELP and USAGE string constants, in source
// order.
func (r *reader) cliConstants(statements []*gotreesitter.Node) []cliConstant {
	var constants []cliConstant
	for _, statement := range statements {
		if r.kind(statement) != "assignment" || r.field(statement, "type") != nil {
			continue
		}
		value := r.assignmentValue(statement)
		if value == nil || !r.isStringConstant(value) {
			continue
		}
		for _, target := range r.assignmentTargets(statement) {
			if r.kind(target) != "identifier" {
				continue
			}
			name := r.text(target)
			if name != "HELP" && name != "USAGE" {
				continue
			}
			constants = append(constants, cliConstant{
				Name: name, Value: r.stringConstantValue(value),
			})
		}
	}
	return constants
}
