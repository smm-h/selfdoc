package python

// The expression renderer: ast.unparse, reproduced over a concrete syntax
// tree.
//
// Every Python reference page selfdoc has ever produced renders an annotation,
// a default value and a base class the way ast.unparse renders them, and that
// rendering is a normalization rather than a quotation of the source: parens
// the grammar needed are dropped and the ones precedence needs are put back,
// operators get one space on each side, a string is re-quoted by repr, and a
// number is rewritten in base ten. This file reproduces that, node by node,
// against the precedence table in CPython's own unparser.
//
// A node type this file does not know is rendered as its source text. That is
// the closest an unknown construct can get to what the author wrote, and it
// keeps one unrecognized corner of the grammar from emptying a page.

import (
	"strings"

	"github.com/odvcencio/gotreesitter"
)

// precedence is CPython's _Precedence table. The renderer parenthesizes a node
// when the precedence its parent demands is higher than the node's own.
type precedence int

const (
	precNamedExpr precedence = iota + 1 // <target> := <value>
	precTuple                           // <a>, <b>
	precYield                           // yield, yield from
	precTest                            // if-else, lambda -- the default
	precOr                              // or
	precAnd                             // and
	precNot                             // not
	precCmp                             // <, >, ==, in, is
	precExpr                            // | (BOR shares this level)
	precBxor                            // ^
	precBand                            // &
	precShift                           // <<, >>
	precArith                           // +, -
	precTerm                            // *, @, /, %, //
	precFactor                          // unary +, -, ~
	precPower                           // **
	precAwait                           // await
	precAtom
)

// next is the precedence one level tighter, which is what a left-associative
// operator demands of its right operand.
func (p precedence) next() precedence {
	if p < precAtom {
		return p + 1
	}
	return p
}

// binaryPrecedence is the level of each binary operator.
var binaryPrecedence = map[string]precedence{
	"+": precArith, "-": precArith,
	"*": precTerm, "@": precTerm, "/": precTerm, "%": precTerm, "//": precTerm,
	"<<": precShift, ">>": precShift,
	"|": precExpr, "^": precBxor, "&": precBand,
	"**": precPower,
}

// reader is one parsed file: the grammar it was parsed with and the bytes the
// nodes point into.
type reader struct {
	lang   *gotreesitter.Language
	source []byte
}

// kind is a node's type name.
func (r *reader) kind(n *gotreesitter.Node) string { return n.Type(r.lang) }

// text is a node's own source text.
func (r *reader) text(n *gotreesitter.Node) string { return n.Text(r.source) }

// field is the child a field name selects, nil when there is none.
func (r *reader) field(n *gotreesitter.Node, name string) *gotreesitter.Node {
	if n == nil {
		return nil
	}
	return n.ChildByFieldName(name, r.lang)
}

// fieldAll is every child carrying a field name, which a repeated field (a
// subscript's indices, an import's names) needs.
func (r *reader) fieldAll(n *gotreesitter.Node, name string) []*gotreesitter.Node {
	var found []*gotreesitter.Node
	for i := 0; i < n.ChildCount(); i++ {
		if n.FieldNameForChild(i, r.lang) == name {
			found = append(found, n.Child(i))
		}
	}
	return found
}

// named is a node's named children with the comments and the line
// continuations removed. Both are extras the grammar admits anywhere, and
// neither has an ast node at all.
func (r *reader) named(n *gotreesitter.Node) []*gotreesitter.Node {
	var kept []*gotreesitter.Node
	for i := 0; i < n.NamedChildCount(); i++ {
		child := n.NamedChild(i)
		if isTrivia(r.kind(child)) {
			continue
		}
		kept = append(kept, child)
	}
	return kept
}

// isTrivia reports the node types that carry no meaning to ast.
func isTrivia(kind string) bool { return kind == "comment" || kind == "line_continuation" }

// unparse renders an expression the way ast.unparse renders it at the top of a
// tree, where the demanded precedence is TEST.
func (r *reader) unparse(n *gotreesitter.Node) string { return r.expr(n, precTest) }

// expr renders one expression node. ctx is the precedence the parent demands.
func (r *reader) expr(n *gotreesitter.Node, ctx precedence) string {
	if n == nil {
		return ""
	}
	switch r.kind(n) {
	case "type", "parenthesized_expression":
		// Neither has an ast node of its own: the annotation wrapper is a
		// grammar artifact, and the parens the author wrote are not in the
		// tree the unparser reads.
		children := r.named(n)
		if len(children) == 1 {
			return r.expr(children[0], ctx)
		}
		return r.text(n)

	case "identifier", "keyword_identifier", "dotted_name":
		return r.text(n)

	case "string":
		return r.stringLiteral(n)
	case "concatenated_string":
		return r.concatenatedString(n)
	case "integer", "float":
		return numberLiteral(r.text(n))
	case "true":
		return "True"
	case "false":
		return "False"
	case "none":
		return "None"
	case "ellipsis":
		return "..."

	case "attribute", "member_type":
		object := r.field(n, "object")
		attr := r.field(n, "attribute")
		if object == nil || attr == nil {
			children := r.named(n)
			if len(children) != 2 {
				return r.text(n)
			}
			object, attr = children[0], children[1]
		}
		rendered := r.expr(object, precAtom)
		// 3 .__abs__() -- an integer literal needs the space, or the dot
		// reads as a decimal point. ast asks this of the constant it holds,
		// so the parens the author wrote around it change nothing.
		if r.isIntegerConstant(object) {
			rendered += " "
		}
		return rendered + "." + r.text(attr)

	case "subscript":
		return r.expr(r.field(n, "value"), precAtom) + "[" + r.subscriptIndex(n) + "]"

	case "generic_type":
		children := r.named(n)
		if len(children) != 2 {
			return r.text(n)
		}
		return r.expr(children[0], precAtom) + "[" + r.typeParameter(children[1]) + "]"

	case "slice":
		return r.slice(n)

	case "call":
		return r.expr(r.field(n, "function"), precAtom) + r.arguments(r.field(n, "arguments"))

	case "argument_list":
		return r.arguments(n)

	case "list":
		return "[" + strings.Join(r.exprList(r.named(n), precTest), ", ") + "]"

	case "set":
		return "{" + strings.Join(r.exprList(r.named(n), precTest), ", ") + "}"

	case "tuple", "expression_list", "tuple_pattern", "pattern_list":
		elements := r.named(n)
		rendered := r.itemsView(elements)
		if len(elements) == 0 || ctx > precTuple {
			return "(" + rendered + ")"
		}
		return rendered

	case "dictionary":
		var items []string
		for _, child := range r.named(n) {
			switch r.kind(child) {
			case "pair":
				items = append(items,
					r.expr(r.field(child, "key"), precTest)+": "+
						r.expr(r.field(child, "value"), precTest))
			case "dictionary_splat":
				items = append(items, "**"+r.expr(r.splatValue(child), precExpr))
			default:
				items = append(items, r.expr(child, precTest))
			}
		}
		return "{" + strings.Join(items, ", ") + "}"

	case "pair":
		return r.expr(r.field(n, "key"), precTest) + ": " + r.expr(r.field(n, "value"), precTest)

	case "list_splat":
		return "*" + r.expr(r.splatValue(n), precExpr)
	case "splat_type":
		stars := "*"
		if strings.HasPrefix(r.text(n), "**") {
			stars = "**"
		}
		return stars + r.expr(r.splatValue(n), precExpr)
	case "dictionary_splat":
		return "**" + r.expr(r.splatValue(n), precExpr)

	case "keyword_argument":
		return r.text(r.field(n, "name")) + "=" + r.expr(r.field(n, "value"), precTest)

	case "unary_operator":
		operator := r.operatorToken(n)
		own := precFactor
		rendered := operator + r.expr(r.field(n, "argument"), own)
		return parenthesize(rendered, ctx > own)

	case "not_operator":
		own := precNot
		rendered := "not " + r.expr(r.field(n, "argument"), own)
		return parenthesize(rendered, ctx > own)

	case "binary_operator", "union_type":
		return r.binaryOperator(n, ctx)

	case "boolean_operator":
		return r.booleanOperator(n, ctx)

	case "comparison_operator":
		return r.comparisonChain(n, ctx)

	case "conditional_expression":
		own := precTest
		children := r.named(n)
		if len(children) != 3 {
			return r.text(n)
		}
		rendered := r.expr(children[0], own.next()) + " if " + r.expr(children[1], own.next()) +
			" else " + r.expr(children[2], own)
		return parenthesize(rendered, ctx > own)

	case "lambda":
		own := precTest
		params := r.renderParams(r.field(n, "parameters"))
		rendered := "lambda"
		if len(params) > 0 {
			rendered += " " + strings.Join(params, ", ")
		}
		rendered += ": " + r.expr(r.field(n, "body"), own)
		return parenthesize(rendered, ctx > own)

	case "named_expression":
		own := precNamedExpr
		rendered := r.expr(r.field(n, "name"), precAtom) + " := " +
			r.expr(r.field(n, "value"), precAtom)
		return parenthesize(rendered, ctx > own)

	case "await":
		own := precAwait
		children := r.named(n)
		rendered := "await"
		if len(children) > 0 {
			rendered += " " + r.expr(children[0], precAtom)
		}
		return parenthesize(rendered, ctx > own)

	case "yield":
		own := precYield
		rendered := "yield"
		if strings.HasPrefix(r.text(n), "yield from") {
			rendered = "yield from"
		}
		if children := r.named(n); len(children) > 0 {
			rendered += " " + r.expr(children[0], precAtom)
		}
		return parenthesize(rendered, ctx > own)

	case "list_comprehension":
		return "[" + r.comprehension(n) + "]"
	case "set_comprehension", "dictionary_comprehension":
		return "{" + r.comprehension(n) + "}"
	case "generator_expression":
		return "(" + r.comprehension(n) + ")"

	case "constrained_type":
		children := r.named(n)
		if len(children) == 2 {
			return r.expr(children[0], precTest) + ": " + r.expr(children[1], precTest)
		}
		return r.text(n)

	default:
		return r.text(n)
	}
}

// isIntegerConstant reports whether a node is an integer literal, looking
// through the wrappers that have no ast node of their own.
func (r *reader) isIntegerConstant(n *gotreesitter.Node) bool {
	switch r.kind(n) {
	case "integer":
		return true
	case "parenthesized_expression", "type":
		children := r.named(n)
		return len(children) == 1 && r.isIntegerConstant(children[0])
	}
	return false
}

// parenthesize wraps a rendering when the precedence context demands it.
func parenthesize(rendered string, needed bool) string {
	if needed {
		return "(" + rendered + ")"
	}
	return rendered
}

// exprList renders each node at the same demanded precedence.
func (r *reader) exprList(nodes []*gotreesitter.Node, ctx precedence) []string {
	rendered := make([]string, 0, len(nodes))
	for _, node := range nodes {
		rendered = append(rendered, r.expr(node, ctx))
	}
	return rendered
}

// itemsView is CPython's items_view: a comma-separated list, with a trailing
// comma when there is exactly one item -- which is how a one-element tuple
// keeps being a tuple.
func (r *reader) itemsView(nodes []*gotreesitter.Node) string {
	if len(nodes) == 1 {
		return r.expr(nodes[0], precTest) + ","
	}
	return strings.Join(r.exprList(nodes, precTest), ", ")
}

// splatValue is the expression a splat node carries.
func (r *reader) splatValue(n *gotreesitter.Node) *gotreesitter.Node {
	children := r.named(n)
	if len(children) == 0 {
		return nil
	}
	return children[0]
}

// operatorToken is the anonymous operator token a unary or binary node carries.
func (r *reader) operatorToken(n *gotreesitter.Node) string {
	if operator := r.field(n, "operator"); operator != nil {
		return r.text(operator)
	}
	for i := 0; i < n.ChildCount(); i++ {
		if child := n.Child(i); !child.IsNamed() {
			return r.text(child)
		}
	}
	return ""
}

// comparisonChain renders a comparison, including a chained one, whose
// operators are anonymous tokens between the operands -- two of them for the
// two-word "is not" and "not in".
func (r *reader) comparisonChain(n *gotreesitter.Node, ctx precedence) string {
	own := precCmp
	var out strings.Builder
	var operator []string
	first := true
	for i := 0; i < n.ChildCount(); i++ {
		child := n.Child(i)
		if !child.IsNamed() {
			operator = append(operator, r.text(child))
			continue
		}
		if isTrivia(r.kind(child)) {
			continue
		}
		rendered := r.expr(child, own.next())
		if first {
			out.WriteString(rendered)
			first = false
		} else {
			out.WriteString(" " + strings.Join(operator, " ") + " " + rendered)
		}
		operator = nil
	}
	return parenthesize(out.String(), ctx > own)
}

// binaryOperator renders a binary operation, including the annotation-only
// union spelling, which is the same node to the unparser.
func (r *reader) binaryOperator(n *gotreesitter.Node, ctx precedence) string {
	left := r.field(n, "left")
	right := r.field(n, "right")
	operator := r.operatorToken(n)
	if r.kind(n) == "union_type" {
		return r.unionChain(n, ctx)
	}
	if left == nil || right == nil {
		return r.text(n)
	}
	if operator == "|" {
		return r.unionChain(n, ctx)
	}
	own, known := binaryPrecedence[operator]
	if !known {
		own = precArith
	}
	leftCtx, rightCtx := own, own.next()
	if operator == "**" {
		// The one right-associative operator.
		leftCtx, rightCtx = own.next(), own
	}
	rendered := r.expr(left, leftCtx) + " " + operator + " " + r.expr(right, rightCtx)
	return parenthesize(rendered, ctx > own)
}

// unionChain renders a chain of the | operator.
//
// ast reads a | b | c left-associatively, so nothing in the chain is
// parenthesized; the annotation grammar nests it to the right instead, and
// rendering that nesting as an ordinary binary operation would put parens
// around everything after the first operand. The chain is flattened first --
// through the annotation wrapper and the union node, but never through parens
// the author wrote, which ast does keep.
func (r *reader) unionChain(n *gotreesitter.Node, ctx precedence) string {
	var operands []*gotreesitter.Node
	var flatten func(node *gotreesitter.Node)
	flatten = func(node *gotreesitter.Node) {
		if node == nil {
			return
		}
		switch r.kind(node) {
		case "type":
			if children := r.named(node); len(children) == 1 {
				flatten(children[0])
				return
			}
		case "union_type":
			if children := r.named(node); len(children) == 2 {
				flatten(children[0])
				flatten(children[1])
				return
			}
		case "binary_operator":
			if r.operatorToken(node) == "|" {
				flatten(r.field(node, "left"))
				flatten(r.field(node, "right"))
				return
			}
		}
		operands = append(operands, node)
	}
	flatten(n)

	own := precExpr
	rendered := make([]string, 0, len(operands))
	for index, operand := range operands {
		level := own.next()
		if index == 0 {
			level = own
		}
		rendered = append(rendered, r.expr(operand, level))
	}
	return parenthesize(strings.Join(rendered, " | "), ctx > own)
}

// booleanOperator renders an and/or chain.
//
// ast folds a chain of one operator into a single node whose operands are
// demanded at ever tighter precedence, so the nested tree the grammar produces
// is flattened first -- otherwise a right-nested chain would keep parens ast
// drops.
func (r *reader) booleanOperator(n *gotreesitter.Node, ctx precedence) string {
	operator := r.operatorToken(n)
	own := precOr
	if operator == "and" {
		own = precAnd
	}

	var operands []*gotreesitter.Node
	var flatten func(node *gotreesitter.Node)
	flatten = func(node *gotreesitter.Node) {
		if r.kind(node) == "boolean_operator" && r.operatorToken(node) == operator {
			flatten(r.field(node, "left"))
			flatten(r.field(node, "right"))
			return
		}
		operands = append(operands, node)
	}
	flatten(n)

	level := own
	rendered := make([]string, 0, len(operands))
	for _, operand := range operands {
		level = level.next()
		rendered = append(rendered, r.expr(operand, level))
	}
	return parenthesize(strings.Join(rendered, " "+operator+" "), ctx > own)
}

// subscriptIndex renders what sits between the brackets. Several indices are
// one tuple to ast, and a tuple there is written without its parens.
func (r *reader) subscriptIndex(n *gotreesitter.Node) string {
	indices := r.fieldAll(n, "subscript")
	switch {
	case len(indices) == 0:
		return ""
	case len(indices) > 1:
		return r.itemsView(indices)
	case r.kind(indices[0]) == "tuple":
		elements := r.named(indices[0])
		if len(elements) > 0 {
			return r.itemsView(elements)
		}
	}
	return r.expr(indices[0], precTest)
}

// typeParameter renders the bracketed parameters of a generic annotation,
// which ast reads as a subscript.
func (r *reader) typeParameter(n *gotreesitter.Node) string {
	children := r.named(n)
	if len(children) == 1 {
		return r.expr(children[0], precTest)
	}
	return strings.Join(r.exprList(children, precTest), ", ")
}

// slice renders a slice, reading the lower, upper and step positions out of
// the colons the node carries. ast writes one colon always and a second only
// when there is a step.
func (r *reader) slice(n *gotreesitter.Node) string {
	var positions [3]string
	slot := 0
	for i := 0; i < n.ChildCount(); i++ {
		child := n.Child(i)
		if !child.IsNamed() {
			if r.text(child) == ":" && slot < len(positions)-1 {
				slot++
			}
			continue
		}
		if isTrivia(r.kind(child)) {
			continue
		}
		positions[slot] = r.expr(child, precTest)
	}
	rendered := positions[0] + ":" + positions[1]
	if positions[2] != "" {
		rendered += ":" + positions[2]
	}
	return rendered
}

// arguments renders a call's arguments, in the source order the tree carries
// them.
//
// A sole generator argument is the grammar's own node rather than an argument
// list, and it keeps the parens it writes for itself inside the call's -- which
// is what ast writes too, since a generator expression is always parenthesized.
func (r *reader) arguments(n *gotreesitter.Node) string {
	if n == nil {
		return "()"
	}
	if r.kind(n) != "argument_list" {
		return "(" + r.expr(n, precTest) + ")"
	}
	// ast writes every positional argument before every keyword one,
	// whatever order the call was written in: the two are separate lists on
	// the call node, and a keyword written before a star-arg moves.
	var positional, keyword []string
	for _, argument := range r.named(n) {
		switch r.kind(argument) {
		case "keyword_argument", "dictionary_splat":
			keyword = append(keyword, r.expr(argument, precTest))
		default:
			positional = append(positional, r.expr(argument, precTest))
		}
	}
	return "(" + strings.Join(append(positional, keyword...), ", ") + ")"
}

// comprehension renders a comprehension's element and its clauses.
func (r *reader) comprehension(n *gotreesitter.Node) string {
	var out strings.Builder
	for index, child := range r.named(n) {
		switch r.kind(child) {
		case "for_in_clause":
			keyword := " for "
			if strings.HasPrefix(r.text(child), "async") {
				keyword = " async for "
			}
			out.WriteString(keyword)
			out.WriteString(r.expr(r.field(child, "left"), precTuple))
			out.WriteString(" in ")
			rights := r.fieldAll(child, "right")
			out.WriteString(strings.Join(r.exprList(rights, precTest.next()), ", "))
		case "if_clause":
			out.WriteString(" if ")
			for _, condition := range r.named(child) {
				out.WriteString(r.expr(condition, precTest.next()))
			}
		default:
			if index == 0 {
				out.WriteString(r.expr(child, precTest))
			}
		}
	}
	return out.String()
}

// stringLiteral renders one string literal: a constant through repr, an
// f-string through the f-string writer.
func (r *reader) stringLiteral(n *gotreesitter.Node) string {
	prefix, _, _, ok := literalPrefix(r.text(n))
	if !ok {
		return r.text(n)
	}
	if strings.Contains(prefix, "f") {
		return r.fString([]*gotreesitter.Node{n})
	}
	value, isBytes := r.stringValue(n)
	if isBytes {
		return reprBytes(value)
	}
	return reprString(value)
}

// concatenatedString renders adjacent string literals, which the parser folds
// into one constant before the unparser ever sees them.
func (r *reader) concatenatedString(n *gotreesitter.Node) string {
	parts := r.named(n)
	for _, part := range parts {
		if prefix, _, _, ok := literalPrefix(r.text(part)); ok && strings.Contains(prefix, "f") {
			return r.fString(parts)
		}
	}
	var value strings.Builder
	isBytes := false
	for _, part := range parts {
		text, partIsBytes := r.stringValue(part)
		isBytes = isBytes || partIsBytes
		value.WriteString(text)
	}
	if isBytes {
		return reprBytes(value.String())
	}
	return reprString(value.String())
}

// stringValue decodes one string literal to the value it denotes.
func (r *reader) stringValue(n *gotreesitter.Node) (value string, isBytes bool) {
	text := r.text(n)
	prefix, _, body, ok := literalPrefix(text)
	if !ok {
		return text, false
	}
	isBytes = strings.Contains(prefix, "b")
	raw := strings.Contains(prefix, "r")
	return decodeEscapes(body, raw, isBytes), isBytes
}

// isStringConstant reports whether a node is a plain string constant -- a
// string literal or an implicit concatenation of them, never an f-string and
// never bytes. That is the shape ast reads as a Constant str, which is what a
// docstring and a CLI help constant both have to be.
func (r *reader) isStringConstant(n *gotreesitter.Node) bool {
	switch r.kind(n) {
	case "string":
		prefix, _, _, ok := literalPrefix(r.text(n))
		return ok && !strings.Contains(prefix, "f") && !strings.Contains(prefix, "b")
	case "concatenated_string":
		for _, part := range r.named(n) {
			if !r.isStringConstant(part) {
				return false
			}
		}
		return len(r.named(n)) > 0
	}
	return false
}

// stringConstantValue is a string constant's decoded text.
func (r *reader) stringConstantValue(n *gotreesitter.Node) string {
	if r.kind(n) == "concatenated_string" {
		var value strings.Builder
		for _, part := range r.named(n) {
			value.WriteString(r.stringConstantValue(part))
		}
		return value.String()
	}
	value, _ := r.stringValue(n)
	return value
}

// fStringPart is one piece of an f-string: either a constant run or an
// interpolation already rendered.
type fStringPart struct {
	text       string
	isConstant bool
}

// fString renders an f-string the way CPython's unparser writes a JoinedStr,
// including its quote choice.
func (r *reader) fString(nodes []*gotreesitter.Node) string {
	var parts []fStringPart
	for _, node := range nodes {
		prefix, _, _, ok := literalPrefix(r.text(node))
		if !ok {
			continue
		}
		raw := strings.Contains(prefix, "r")
		if !strings.Contains(prefix, "f") {
			value, _ := r.stringValue(node)
			parts = append(parts, fStringPart{text: escapeBraces(value), isConstant: true})
			continue
		}
		for i := 0; i < node.ChildCount(); i++ {
			child := node.Child(i)
			switch r.kind(child) {
			case "string_content":
				parts = append(parts, fStringPart{
					text: decodeEscapes(r.text(child), raw, false), isConstant: true,
				})
			case "interpolation":
				parts = append(parts, fStringPart{text: r.interpolation(child)})
			}
		}
	}
	return "f" + ftstringHelper(parts)
}

// escapeBraces doubles the braces of a constant that joins an f-string, which
// is what the unparser writes so the result reads back the same.
func escapeBraces(value string) string {
	value = strings.ReplaceAll(value, "{", "{{")
	return strings.ReplaceAll(value, "}", "}}")
}

// interpolation renders one {...} of an f-string, with its conversion and
// format specification.
func (r *reader) interpolation(n *gotreesitter.Node) string {
	expression := r.expr(r.field(n, "expression"), precTest.next())
	var out strings.Builder
	out.WriteString("{")
	if strings.HasPrefix(expression, "{") {
		out.WriteString(" ")
	}
	out.WriteString(expression)
	if conversion := r.field(n, "type_conversion"); conversion != nil {
		out.WriteString(r.text(conversion))
	}
	if spec := r.field(n, "format_specifier"); spec != nil {
		out.WriteString(r.formatSpecifier(spec))
	}
	out.WriteString("}")
	return out.String()
}

// formatSpecifier renders a format specification, rebuilding its literal runs
// from the source between the nested expressions.
func (r *reader) formatSpecifier(n *gotreesitter.Node) string {
	var out strings.Builder
	out.WriteString(":")
	cursor := n.StartByte() + 1 // past the colon
	for i := 0; i < n.ChildCount(); i++ {
		child := n.Child(i)
		if r.kind(child) != "format_expression" {
			continue
		}
		out.WriteString(escapeFormatSpec(string(r.source[cursor:child.StartByte()])))
		out.WriteString("{")
		out.WriteString(r.expr(r.field(child, "expression"), precTest.next()))
		out.WriteString("}")
		cursor = child.EndByte()
	}
	out.WriteString(escapeFormatSpec(string(r.source[cursor:n.EndByte()])))
	return out.String()
}

// escapeFormatSpec escapes a format specification's literal run the way the
// unparser does, where a backslash or a quote would otherwise close the
// f-string.
func escapeFormatSpec(text string) string {
	text = strings.ReplaceAll(text, `\`, `\\`)
	text = strings.ReplaceAll(text, "'", `\'`)
	text = strings.ReplaceAll(text, `"`, `\"`)
	return strings.ReplaceAll(text, "\n", `\n`)
}

// ftstringHelper is CPython's _ftstring_helper: it picks the quote run that
// needs the fewest escapes across every part of the f-string.
func ftstringHelper(parts []fStringPart) string {
	quoteTypes := append([]string(nil), allQuotes...)
	rendered := make([]string, 0, len(parts))
	fallback := false

	for _, part := range parts {
		value := part.text
		if part.isConstant {
			escaped, newQuotes := strLiteralHelper(value, quoteTypes, true)
			if len(keepQuotes(newQuotes, quoteTypes)) == 0 {
				fallback = true
				break
			}
			quoteTypes = newQuotes
			value = escaped
		} else {
			if strings.Contains(value, "\n") {
				quoteTypes = keepQuotes(quoteTypes, multiQuotes)
			}
			if narrowed := dropContained(quoteTypes, value); len(narrowed) > 0 {
				quoteTypes = narrowed
			}
		}
		rendered = append(rendered, value)
	}

	if fallback {
		// No quote run works for every part: fall back to repr inside triple
		// single quotes.
		quoteTypes = []string{"'''"}
		rendered = rendered[:0]
		for _, part := range parts {
			value := part.text
			if part.isConstant {
				quoted := reprString(`"` + value)
				value = strings.TrimSuffix(strings.TrimPrefix(quoted, `'"`), "'")
			}
			rendered = append(rendered, value)
		}
	}

	quote := "'"
	if len(quoteTypes) > 0 {
		quote = quoteTypes[0]
	}
	return quote + strings.Join(rendered, "") + quote
}
