package svelte

import (
	"regexp"
)

// export is one function or constant a script block exports.
type export struct {
	Name string
	// Kind is "function" or "const".
	Kind string
	// Signature is the declaration as a reference page renders it.
	Signature string
}

var (
	// exportFunc matches an exported function declaration and captures its
	// parameter list with any return-type annotation.
	exportFunc = regexp.MustCompile(
		`export` + pySpace + `+(?:async` + pySpace + `+)?function` + pySpace + `+(` + pyWord +
			`+)` + pySpace + `*(\([^)]*\)(?:` + pySpace + `*:` + pySpace + `*[^{;]+)?)`)

	// exportConst matches an exported constant declaration with its value.
	exportConst = regexp.MustCompile(
		`export` + pySpace + `+const` + pySpace + `+(` + pyWord + `+)(?:` + pySpace + `*:` +
			pySpace + `*([^=]+?))?` + pySpace + `*=` + pySpace + `*([^;]+);`)
)

// extractExports reads the functions and constants a script block exports,
// functions first and then constants -- the order the two patterns are applied
// in, which is what the rendered sections follow.
func extractExports(scriptContent string) []export {
	var exports []export

	for _, match := range exportFunc.FindAllStringSubmatch(scriptContent, -1) {
		exports = append(exports, export{
			Name:      match[1],
			Kind:      "function",
			Signature: "export function " + match[1] + pyStrip(match[2]),
		})
	}

	for _, match := range exportConst.FindAllStringSubmatch(scriptContent, -1) {
		name := match[1]
		typeAnnotation := pyStrip(match[2])
		value := pyStrip(match[3])
		signature := "export const " + name + " = " + value
		if typeAnnotation != "" {
			signature = "export const " + name + ": " + typeAnnotation + " = " + value
		}
		exports = append(exports, export{Name: name, Kind: "const", Signature: signature})
	}

	return exports
}
