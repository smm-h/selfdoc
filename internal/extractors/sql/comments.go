package sql

import (
	"regexp"
	"strings"
)

// commentOnRe matches a COMMENT ON statement up to its value. The name can be
// schema-qualified, and a column's name carries its table, so the whole dotted
// token is captured and the parts are compared where they are looked up.
var commentOnRe = regexp.MustCompile(`(?i)\bCOMMENT` + spaceClass + `+ON` + spaceClass + `+` +
	`(TABLE|COLUMN|VIEW|TYPE|FUNCTION|INDEX|SCHEMA|SEQUENCE)` + spaceClass + `+` +
	`([` + wordChars + `.]+)` + spaceClass + `+` +
	`IS` + spaceClass + `+`)

// commentKey identifies one documented object: its kind, lowercased, and the
// name the statement wrote, schema qualification included.
type commentKey struct {
	objType string
	objName string
}

// commentSet is the COMMENT ON statements of one document, in the order they
// appear.
//
// Order is what decides which comment answers a lookup that matches more than
// one -- a bare table name against two schemas' tables -- so it is kept rather
// than left to a map's iteration.
type commentSet struct {
	keys   []commentKey
	values map[commentKey]string
}

// newCommentSet builds an empty set.
func newCommentSet() *commentSet {
	return &commentSet{values: map[commentKey]string{}}
}

// set records a comment, keeping the position of a key that is already there.
func (c *commentSet) set(key commentKey, text string) {
	if _, exists := c.values[key]; !exists {
		c.keys = append(c.keys, key)
	}
	c.values[key] = text
}

// get is the comment recorded for a key, empty when there is none.
func (c *commentSet) get(objType, objName string) string {
	return c.values[commentKey{objType: objType, objName: objName}]
}

// Keys lists the documented objects in document order.
func (c *commentSet) Keys() []commentKey { return c.keys }

// parseComments reads the COMMENT ON statements of a document.
//
// A comment set to NULL removes a comment rather than documenting anything, so
// such a statement contributes nothing.
func parseComments(source string) *commentSet {
	comments := newCommentSet()
	clean := stripComments(source)

	for _, m := range commentOnRe.FindAllStringSubmatchIndex(clean, -1) {
		objType := strings.ToLower(clean[m[2]:m[3]])
		objName := clean[m[4]:m[5]]
		rest := clean[m[1]:]

		if strings.HasPrefix(strings.ToUpper(lstrip(rest)), "NULL") {
			continue
		}

		text, ok := extractCommentString(rest)
		if !ok {
			continue
		}

		comments.set(commentKey{objType: objType, objName: objName}, text)
	}

	return comments
}

// extractCommentString reads the string literal a COMMENT ON statement's value
// is, in either spelling SQL offers: single-quoted with ” for an embedded
// quote, or dollar-quoted with an optional tag. An unterminated literal is not
// a value.
func extractCommentString(text string) (string, bool) {
	text = lstrip(text)

	if strings.HasPrefix(text, "'") {
		var parts strings.Builder
		i := 1
		n := len(text)
		for i < n {
			if text[i] == '\'' {
				if i+1 < n && text[i+1] == '\'' {
					parts.WriteByte('\'')
					i += 2
					continue
				}
				return parts.String(), true
			}
			parts.WriteByte(text[i])
			i++
		}
		return "", false // unterminated
	}

	if tag := dollarTagRe.FindString(text); tag != "" {
		start := len(tag)
		endPos := strings.Index(text[start:], tag)
		if endPos >= 0 {
			return text[start : start+endPos], true
		}
		return "", false // unterminated
	}

	return "", false
}

// lookupComment is the comment documenting one object, tried under its
// schema-qualified name first and then bare.
func lookupComment(comments *commentSet, objType, name, schema string) string {
	if schema != "" {
		if val := comments.get(objType, schema+"."+name); val != "" {
			return val
		}
	}
	return comments.get(objType, name)
}

// lookupColumnComment is the comment documenting one column, tried under the
// schema-qualified table name first and then the bare one.
func lookupColumnComment(comments *commentSet, tableName, colName, schema string) string {
	if schema != "" {
		if val := comments.get("column", schema+"."+tableName+"."+colName); val != "" {
			return val
		}
	}
	return comments.get("column", tableName+"."+colName)
}

// hasFunctionComment reports whether a function is documented, under any
// schema: a COMMENT ON FUNCTION is the only thing in a DDL document that says
// what a function returns, so its presence is what the return-value coverage
// measurement reads.
func hasFunctionComment(comments *commentSet, funcName string) bool {
	for _, key := range comments.Keys() {
		if key.objType != "function" {
			continue
		}
		bareName := key.objName
		if dotIdx := strings.LastIndex(bareName, "."); dotIdx >= 0 {
			bareName = bareName[dotIdx+1:]
		}
		if strings.EqualFold(bareName, funcName) {
			return true
		}
	}
	return false
}
