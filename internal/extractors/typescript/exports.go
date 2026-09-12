package typescript

import (
	"regexp"
	"strings"
)

// tsExport is one exported declaration: the name it exports, the signature
// line as written, and the JSDoc block above it when it has one.
type tsExport struct {
	Name      string
	Signature string
	JSDoc     *JSDoc
}

// declKeywords is the alternation every declaration pattern shares. A function
// admits the generator star, and each keyword carries its own trailing
// whitespace so "function*" needs none.
const declKeywords = `(?:function` + pySpace + `*\*?` + pySpace + `*|class` + pySpace +
	`+|interface` + pySpace + `+|type` + pySpace + `+|const` + pySpace + `+|let` +
	pySpace + `+|var` + pySpace + `+|enum` + pySpace + `+)`

var (
	// exportPattern matches an export declaration and captures its signature
	// up to the body's brace or the statement's semicolon.
	exportPattern = regexp.MustCompile(
		`(?m)^(export` + pySpace + `+` +
			`(?:default` + pySpace + `+)?` +
			`(?:async` + pySpace + `+)?` +
			declKeywords +
			`[^\n{;]*(?:[{;]|\([^)]*\)[^{;]*[{;])?` +
			`)`)

	// exportName captures the declared name out of an export signature.
	exportName = regexp.MustCompile(
		`^export` + pySpace + `+(?:default` + pySpace + `+)?(?:async` + pySpace + `+)?` +
			declKeywords + `(` + pyWord + `+)`)

	// signatureTail is the trailing brace or semicolon a captured signature
	// carries, which the rendered signature drops.
	signatureTail = regexp.MustCompile(pySpace + `*[{;]` + pySpace + `*$`)

	// reexportPattern matches a re-export list: "export { A, B as C }".
	reexportPattern = regexp.MustCompile(`(?m)^export` + pySpace + `*\{([^}]+)\}`)

	// fromClause captures the module a re-export names.
	fromClause = regexp.MustCompile(`from` + pySpace + `+['"]([^'"]+)['"]`)
)

// extractExports lists every declaration a source file exports, with its
// signature and its JSDoc.
//
// Two passes: the declaration exports, then the re-export lists. A re-export
// whose name has a local declaration is rendered from that declaration, so
// "export { Foo }" beside "class Foo" shows the class; one that names another
// module renders the re-export statement itself.
func extractExports(source string) []tsExport {
	var results []tsExport

	for _, match := range exportPattern.FindAllStringSubmatchIndex(source, -1) {
		sigRaw := pyStrip(source[match[2]:match[3]])
		name := extractNameFromSignature(sigRaw)
		if name == "" {
			continue
		}
		results = append(results, tsExport{
			Name:      name,
			Signature: pyStrip(signatureTail.ReplaceAllString(sigRaw, "")),
			JSDoc:     findJSDocBefore(source, match[0]),
		})
	}

	seen := map[string]bool{}
	for _, r := range results {
		seen[r.Name] = true
	}

	for _, match := range reexportPattern.FindAllStringSubmatchIndex(source, -1) {
		lineStart := match[0]
		lineEnd := strings.Index(source[lineStart:], "\n")
		if lineEnd == -1 {
			lineEnd = len(source)
		} else {
			lineEnd += lineStart
		}
		fullLine := pyStrip(source[lineStart:lineEnd])

		fromModule := ""
		if m := fromClause.FindStringSubmatch(fullLine); m != nil {
			fromModule = m[1]
		}

		for _, namePart := range strings.Split(source[match[2]:match[3]], ",") {
			namePart = pyStrip(namePart)
			if namePart == "" {
				continue
			}

			original := namePart
			exportedName := namePart
			if idx := strings.Index(namePart, " as "); idx >= 0 {
				original = pyStrip(namePart[:idx])
				exportedName = pyStrip(namePart[idx+len(" as "):])
			}

			if seen[exportedName] {
				continue
			}
			seen[exportedName] = true

			if local := findLocalDeclaration(source, original); local != nil {
				results = append(results, tsExport{
					Name:      exportedName,
					Signature: local.Signature,
					JSDoc:     local.JSDoc,
				})
				continue
			}
			signature := "export { " + namePart + " }"
			if fromModule != "" {
				signature = "export { " + namePart + " } from '" + fromModule + "'"
			}
			results = append(results, tsExport{Name: exportedName, Signature: signature})
		}
	}

	return results
}

// extractNameFromSignature is the declared name in an export signature, or the
// empty string for a statement that declares none.
func extractNameFromSignature(sig string) string {
	if m := exportName.FindStringSubmatch(sig); m != nil {
		return m[1]
	}
	return ""
}

// findLocalDeclaration is the declaration of name in this file, exported or
// not, with the JSDoc above it. It returns nil when the file declares no such
// name.
func findLocalDeclaration(source, name string) *tsExport {
	declPattern := regexp.MustCompile(
		`(?m)^((?:export` + pySpace + `+)?(?:default` + pySpace + `+)?(?:async` + pySpace + `+)?` +
			declKeywords + regexp.QuoteMeta(name) +
			`[^\n{;]*(?:[{;]|\([^)]*\)[^{;]*[{;])?)`)
	match := declPattern.FindStringSubmatchIndex(source)
	if match == nil {
		return nil
	}

	sigRaw := pyStrip(source[match[2]:match[3]])
	return &tsExport{
		Name:      name,
		Signature: pyStrip(signatureTail.ReplaceAllString(sigRaw, "")),
		JSDoc:     findJSDocBefore(source, match[0]),
	}
}
