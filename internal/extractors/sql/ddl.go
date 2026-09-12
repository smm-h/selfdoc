package sql

import (
	"regexp"
	"strings"
)

// The CREATE patterns. Every one of them admits OR REPLACE, IF NOT EXISTS and a
// schema qualification, because a DDL document writes all three, and every one
// is case-insensitive, because SQL is.
var (
	// createRe matches any of the four kinds of object, which is what the
	// symbol list reads.
	createRe = regexp.MustCompile(`(?i)CREATE` + spaceClass + `+(?:OR` + spaceClass + `+REPLACE` +
		spaceClass + `+)?(?:TABLE|VIEW|TYPE|FUNCTION)` + spaceClass + `+` +
		`(?:IF` + spaceClass + `+NOT` + spaceClass + `+EXISTS` + spaceClass + `+)?` +
		`(?:(` + wordClass + `+)\.)?(` + wordClass + `+)`)

	createTableRe = regexp.MustCompile(`(?i)CREATE` + spaceClass + `+(?:OR` + spaceClass +
		`+REPLACE` + spaceClass + `+)?TABLE` + spaceClass + `+` +
		`(?:IF` + spaceClass + `+NOT` + spaceClass + `+EXISTS` + spaceClass + `+)?` +
		`(?:(` + wordClass + `+)\.)?(` + wordClass + `+)` + spaceClass + `*\(`)

	createViewRe = regexp.MustCompile(`(?i)CREATE` + spaceClass + `+(?:OR` + spaceClass +
		`+REPLACE` + spaceClass + `+)?VIEW` + spaceClass + `+` +
		`(?:(` + wordClass + `+)\.)?(` + wordClass + `+)` + spaceClass + `+AS\b`)

	createTypeEnumRe = regexp.MustCompile(`(?i)CREATE` + spaceClass + `+TYPE` + spaceClass + `+` +
		`(?:(` + wordClass + `+)\.)?(` + wordClass + `+)` + spaceClass + `+AS` + spaceClass +
		`+ENUM` + spaceClass + `*\(`)

	createTypeCompositeRe = regexp.MustCompile(`(?i)CREATE` + spaceClass + `+TYPE` + spaceClass +
		`+(?:(` + wordClass + `+)\.)?(` + wordClass + `+)` + spaceClass + `+AS` + spaceClass + `*\(`)

	createFunctionRe = regexp.MustCompile(`(?i)CREATE` + spaceClass + `+(?:OR` + spaceClass +
		`+REPLACE` + spaceClass + `+)?FUNCTION` + spaceClass + `+` +
		`(?:(` + wordClass + `+)\.)?(` + wordClass + `+)` + spaceClass + `*\(`)

	// enumValueRe matches one quoted label of an enum, with '' read as an
	// embedded quote.
	enumValueRe = regexp.MustCompile(`'([^']*(?:''[^']*)*)'`)

	// The column-constraint patterns, each read off what is left of a column
	// definition once the type has been taken from the front of it.
	notNullRe    = regexp.MustCompile(`(?i)\bNOT` + spaceClass + `+NULL\b`)
	identityRe   = regexp.MustCompile(`(?i)\bGENERATED` + spaceClass + `+(ALWAYS|BY` + spaceClass + `+DEFAULT)` + spaceClass + `+AS` + spaceClass + `+IDENTITY\b`)
	generatedRe  = regexp.MustCompile(`(?i)\bGENERATED` + spaceClass + `+ALWAYS` + spaceClass + `+AS` + spaceClass + `*\(`)
	defaultRe    = regexp.MustCompile(`(?i)\bDEFAULT` + spaceClass + `+`)
	primaryKeyRe = regexp.MustCompile(`(?i)\bPRIMARY` + spaceClass + `+KEY\b`)
	uniqueRe     = regexp.MustCompile(`(?i)\bUNIQUE\b`)
	referencesRe = regexp.MustCompile(`(?i)\bREFERENCES` + spaceClass + `+(` + wordClass +
		`+(?:\.` + wordClass + `+)?)` + spaceClass + `*(\([^)]*\))?`)
	checkRe = regexp.MustCompile(`(?i)\bCHECK` + spaceClass + `*\(`)

	// castSuffixRe matches the type cast a quoted default value can carry.
	castSuffixRe = regexp.MustCompile(`^` + spaceClass + `*::` + spaceClass + `*` + wordClass +
		`+(\[\])?`)
)

// tableConstraintPrefixes open a table-level constraint rather than a column,
// so a definition beginning with one declares no column.
var tableConstraintPrefixes = []string{
	"CHECK", "CONSTRAINT", "PRIMARY KEY", "UNIQUE", "FOREIGN KEY", "EXCLUDE",
}

// typeEndKeywords end a column's type: the first of them is where the type
// stops and the constraints begin.
var typeEndKeywords = map[string]bool{
	"NOT": true, "NULL": true, "DEFAULT": true, "PRIMARY": true, "UNIQUE": true,
	"REFERENCES": true, "CHECK": true, "GENERATED": true, "CONSTRAINT": true,
	"COLLATE": true,
}

// defaultEndKeywords end a DEFAULT expression: the clause runs until one of
// them begins a word.
var defaultEndKeywords = []string{
	"NOT", "NULL", "PRIMARY", "UNIQUE", "REFERENCES", "CHECK",
	"CONSTRAINT", "GENERATED", "COLLATE",
}

// column is one column of a table.
type column struct {
	name         string
	colType      string
	nullable     bool
	defaultValue string
	constraints  []string
	description  string
}

// table is one CREATE TABLE and the columns it declares.
type table struct {
	name    string
	schema  string
	columns []column
}

// view is one CREATE VIEW.
type view struct {
	name   string
	schema string
}

// typeField is one field of a composite type.
type typeField struct {
	name      string
	fieldType string
}

// userType is one CREATE TYPE: an enum with its labels, or a composite with
// its fields.
type userType struct {
	name   string
	schema string
	kind   string
	values []string
	fields []typeField
}

// function is one CREATE FUNCTION.
type function struct {
	name   string
	schema string
}

// extractSymbols lists the objects a DDL document creates, by their
// unqualified names.
func extractSymbols(source string) []string {
	clean := stripComments(source)
	var symbols []string
	for _, m := range createRe.FindAllStringSubmatch(clean, -1) {
		name := m[2]
		if !containsString(symbols, name) {
			symbols = append(symbols, name)
		}
	}
	return symbols
}

// containsString reports whether values carries want.
func containsString(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}

// parseCreateTable reads the CREATE TABLE statements of a document, each with
// the columns it declares.
func parseCreateTable(source string) []table {
	clean := stripComments(source)
	var tables []table

	for _, m := range createTableRe.FindAllStringSubmatchIndex(clean, -1) {
		schema := ""
		if m[2] >= 0 {
			schema = clean[m[2]:m[3]]
		}
		tableName := clean[m[4]:m[5]]

		parenStart := m[1] - 1 // the opening parenthesis the match ends on
		end := matchingParen(clean, parenStart)

		var columns []column
		for _, colText := range splitTopLevel(clean[parenStart+1 : end]) {
			if col, ok := parseColumnDef(colText); ok {
				columns = append(columns, col)
			}
		}

		tables = append(tables, table{name: tableName, schema: schema, columns: columns})
	}

	return tables
}

// parseCreateView reads the CREATE VIEW statements of a document.
func parseCreateView(source string) []view {
	clean := stripComments(source)
	var views []view
	for _, m := range createViewRe.FindAllStringSubmatch(clean, -1) {
		views = append(views, view{name: m[2], schema: m[1]})
	}
	return views
}

// parseCreateType reads the CREATE TYPE statements of a document: the enums
// first, then the composites, each name recorded once.
func parseCreateType(source string) []userType {
	clean := stripComments(source)
	var types []userType
	seen := map[[2]string]bool{}

	for _, m := range createTypeEnumRe.FindAllStringSubmatchIndex(clean, -1) {
		schema := ""
		if m[2] >= 0 {
			schema = clean[m[2]:m[3]]
		}
		typeName := clean[m[4]:m[5]]
		key := [2]string{schema, typeName}
		if seen[key] {
			continue
		}
		seen[key] = true

		parenStart := m[1] - 1
		end := matchingParen(clean, parenStart)

		var values []string
		for _, valueMatch := range enumValueRe.FindAllStringSubmatch(clean[parenStart+1:end], -1) {
			values = append(values, strings.ReplaceAll(valueMatch[1], "''", "'"))
		}

		types = append(types, userType{
			name:   typeName,
			schema: schema,
			kind:   "enum",
			values: values,
		})
	}

	for _, m := range createTypeCompositeRe.FindAllStringSubmatchIndex(clean, -1) {
		schema := ""
		if m[2] >= 0 {
			schema = clean[m[2]:m[3]]
		}
		typeName := clean[m[4]:m[5]]
		key := [2]string{schema, typeName}
		if seen[key] {
			continue
		}
		seen[key] = true

		parenStart := m[1] - 1
		end := matchingParen(clean, parenStart)

		var typeFields []typeField
		for _, fieldDef := range strings.Split(clean[parenStart+1:end], ",") {
			fieldDef = strip(fieldDef)
			if fieldDef == "" {
				continue
			}
			parts := splitOnce(fieldDef)
			if len(parts) == 2 {
				typeFields = append(typeFields, typeField{
					name:      parts[0],
					fieldType: strip(strings.TrimRight(parts[1], ");")),
				})
			} else if len(parts) == 1 {
				typeFields = append(typeFields, typeField{name: parts[0]})
			}
		}

		types = append(types, userType{
			name:   typeName,
			schema: schema,
			kind:   "composite",
			fields: typeFields,
		})
	}

	return types
}

// splitOnce splits text on its first run of whitespace, which is what Python's
// str.split(None, 1) does.
func splitOnce(text string) []string {
	text = lstrip(text)
	if text == "" {
		return nil
	}
	for i := 0; i < len(text); i++ {
		if isSpaceByte(text[i]) {
			return []string{text[:i], lstrip(text[i:])}
		}
	}
	return []string{text}
}

// parseCreateFunction reads the CREATE FUNCTION statements of a document, each
// name recorded once: a function replaced later in the same document is still
// one function.
func parseCreateFunction(source string) []function {
	clean := stripComments(source)
	var functions []function
	seen := map[[2]string]bool{}

	for _, m := range createFunctionRe.FindAllStringSubmatch(clean, -1) {
		key := [2]string{m[1], m[2]}
		if seen[key] {
			continue
		}
		seen[key] = true
		functions = append(functions, function{name: m[2], schema: m[1]})
	}

	return functions
}

// parseColumnDef reads one column definition: its name, its type, whether it
// accepts a null, its default and its inline constraints.
//
// A table-level constraint declares no column, and answers nothing.
func parseColumnDef(colText string) (column, bool) {
	colText = strip(colText)
	if colText == "" {
		return column{}, false
	}

	upper := strings.ToUpper(strip(colText))
	for _, prefix := range tableConstraintPrefixes {
		if strings.HasPrefix(upper, prefix) {
			return column{}, false
		}
	}

	tokens := fields(colText)
	if len(tokens) == 0 {
		return column{}, false
	}
	colName := tokens[0]

	rest := strip(colText[len(colName):])

	nullable := true
	defaultValue := ""
	var constraints []string

	typeStr, remainder := extractType(rest)

	// The nullability tests read the remainder as it stood before either of
	// them removed anything, so NOT NULL and an explicit NULL are decided
	// against the same text.
	remainderUpper := strings.ToUpper(remainder)

	if notNullRe.MatchString(remainderUpper) {
		nullable = false
		remainder = strip(notNullRe.ReplaceAllString(remainder, ""))
	}

	if hasBareNull(remainderUpper) {
		nullable = true
		remainder = strip(removeBareNulls(remainder))
	}

	if identityMatch := identityRe.FindStringIndex(remainder); identityMatch != nil {
		defaultValue = strings.ToUpper(remainder[identityMatch[0]:identityMatch[1]])
		remainder = strip(remainder[:identityMatch[0]] + remainder[identityMatch[1]:])
	}

	if generatedMatch := generatedRe.FindStringIndex(remainder); generatedMatch != nil && defaultValue == "" {
		start := generatedMatch[0]
		parenStart := strings.Index(remainder[start:], "(") + start
		end := matchingParen(remainder, parenStart)

		afterParen := strip(remainder[end+1:])
		if strings.HasPrefix(strings.ToUpper(afterParen), "STORED") {
			defaultValue = strip(remainder[start:end+1] + " STORED")
			tail := end + 1 + len("STORED")
			if tail > len(remainder) {
				tail = len(remainder)
			}
			remainder = strip(remainder[:start] + lstrip(remainder[tail:]))
		} else {
			defaultValue = strip(remainder[start : end+1])
			remainder = remainder[:start] + strip(remainder[end+1:])
		}
	}

	if defaultValue == "" {
		if defaultMatch := defaultRe.FindStringIndex(remainder); defaultMatch != nil {
			defaultStart := defaultMatch[1]
			defaultVal := extractDefaultValue(remainder[defaultStart:])
			defaultValue = defaultVal
			tail := defaultStart + len(defaultVal)
			if tail > len(remainder) {
				tail = len(remainder)
			}
			remainder = strip(remainder[:defaultMatch[0]] + strip(remainder[tail:]))
		}
	}

	if primaryKeyRe.MatchString(remainder) {
		constraints = append(constraints, "PRIMARY KEY")
		remainder = strip(primaryKeyRe.ReplaceAllString(remainder, ""))
	}

	if uniqueRe.MatchString(remainder) {
		constraints = append(constraints, "UNIQUE")
		remainder = strip(uniqueRe.ReplaceAllString(remainder, ""))
	}

	if refMatch := referencesRe.FindStringSubmatchIndex(remainder); refMatch != nil {
		refStr := "REFERENCES " + remainder[refMatch[2]:refMatch[3]]
		if refMatch[4] >= 0 {
			refStr += remainder[refMatch[4]:refMatch[5]]
		}
		constraints = append(constraints, refStr)
		remainder = remainder[:refMatch[0]] + strip(remainder[refMatch[1]:])
	}

	if checkMatch := checkRe.FindStringIndex(remainder); checkMatch != nil {
		parenStart := strings.Index(remainder[checkMatch[0]:], "(") + checkMatch[0]
		end := matchingParen(remainder, parenStart)
		constraints = append(constraints, remainder[checkMatch[0]:end+1])
		remainder = remainder[:checkMatch[0]] + strip(remainder[end+1:])
	}

	return column{
		name:         colName,
		colType:      typeStr,
		nullable:     nullable,
		defaultValue: defaultValue,
		constraints:  constraints,
	}, true
}

// extractType takes the type off the front of what follows a column's name,
// and answers it with the text that remains.
//
// A parameterized type keeps its parentheses -- numeric(10,2) -- and an array
// type its brackets, because both are part of what the column is declared as;
// the type ends at the first constraint keyword.
func extractType(rest string) (string, string) {
	var tokens []string
	i := 0
	n := len(rest)

	for i < n {
		for i < n && isSpaceByte(rest[i]) {
			i++
		}
		if i >= n {
			break
		}

		// A parenthesized parameter list belongs to the token before it.
		if rest[i] == '(' {
			start := i
			depth := 0
			for i < n {
				if rest[i] == '(' {
					depth++
				} else if rest[i] == ')' {
					depth--
					if depth == 0 {
						i++
						break
					}
				}
				i++
			}
			if len(tokens) > 0 {
				tokens[len(tokens)-1] += rest[start:i]
			}
			// Array brackets can follow the parameter list.
			for i < n && rest[i] == '[' {
				bracketStart := i
				for i < n && rest[i] != ']' {
					i++
				}
				if i < n {
					i++
				}
				if len(tokens) > 0 {
					tokens[len(tokens)-1] += rest[bracketStart:i]
				}
			}
			continue
		}

		// Array brackets belong to the token before them too.
		if rest[i] == '[' {
			bracketStart := i
			for i < n && rest[i] != ']' {
				i++
			}
			if i < n {
				i++
			}
			if len(tokens) > 0 {
				tokens[len(tokens)-1] += rest[bracketStart:i]
			}
			continue
		}

		wordStart := i
		for i < n && !isSpaceByte(rest[i]) && rest[i] != '(' && rest[i] != '[' {
			i++
		}
		word := rest[wordStart:i]

		if word == "" {
			break
		}

		if typeEndKeywords[strings.ToUpper(word)] {
			// The word begins the constraints: put the cursor back on it.
			i = wordStart
			break
		}

		tokens = append(tokens, word)
	}

	return strings.Join(tokens, " "), strip(rest[i:])
}

// extractDefaultValue takes a DEFAULT expression off the front of text.
//
// A quoted literal runs to its closing quote and keeps the type cast that can
// follow it; anything else runs until a constraint keyword begins a word at
// paren depth zero, so a function call and a parenthesized expression are read
// whole.
func extractDefaultValue(text string) string {
	text = strip(text)
	if text == "" {
		return ""
	}

	if text[0] == '\'' {
		end := skipSingleQuoted(text, 0)
		if cast := castSuffixRe.FindString(text[end:]); cast != "" {
			end += len(cast)
		}
		return strip(text[:end])
	}

	i := 0
	n := len(text)
	depth := 0

	for i < n {
		ch := text[i]
		switch {
		case ch == '(':
			depth++
		case ch == ')':
			depth--
		case ch == '\'' && depth == 0:
			i = skipSingleQuoted(text, i)
			continue
		case depth == 0 && isSpaceByte(ch):
			rest := lstrip(text[i:])
			restUpper := strings.ToUpper(rest)
			for _, kw := range defaultEndKeywords {
				if !strings.HasPrefix(restUpper, kw) {
					continue
				}
				if len(rest) == len(kw) || !isPyAlnum([]rune(rest[len(kw):])[0]) {
					return strip(text[:i])
				}
			}
		}
		i++
	}

	return strip(text)
}
