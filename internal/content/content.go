// Package content resolves the content directives: the ones that need no
// language extractor.
//
// They cover the five callouts, the glossary list, and the filesystem and
// project-metadata directives (list-tree, table-dep, list-modules,
// table-commands, table-directives, table-config-schema, table-endpoint,
// list-crawlers, var and cv).
//
// # One dispatch, no registry
//
// The Python this replaces had two content modules and a directive registry
// between them: table-commands reads a strictcli schema, the schema reader
// lived in the application package, and the core package it had to be
// dispatched from was forbidden to import that package. The registry existed
// to carry one function across that boundary. One Go module has no such
// boundary, so table-commands is an ordinary branch of ResolveContent like
// every other directive, and the registry is gone -- along with the questions
// it raised (when is a resolver registered, what happens to a build that never
// imported the module that registers it).
package content

import (
	"fmt"
	"regexp"
	"strings"
)

// boldTermRE matches the bold term a glossary line opens with, so the markers
// can be stripped before the term is split from its definition.
var boldTermRE = regexp.MustCompile(`^\*\*(.+?)\*\*`)

// calloutTitles maps each callout directive to the title it renders.
var calloutTitles = map[string]string{
	"callout-note":      "Note",
	"callout-warning":   "Warning",
	"callout-tip":       "Tip",
	"callout-danger":    "Danger",
	"callout-important": "Important",
}

// ContentDirectives is every directive name this package resolves.
var ContentDirectives = map[string]struct{}{
	"callout-note": {}, "callout-warning": {}, "callout-tip": {},
	"callout-danger": {}, "callout-important": {}, "list-glossary": {},
	"list-tree": {}, "table-dep": {}, "list-modules": {},
	"table-commands": {}, "table-directives": {}, "table-config-schema": {},
	"table-endpoint": {}, "list-crawlers": {}, "var": {}, "cv": {},
}

// resolveCallout produces the HTML for a callout directive.
func resolveCallout(calloutType, title string, body []string) string {
	parts := []string{
		`<div class="callout ` + calloutType + `">`,
		`<p class="callout-title">` + title + `</p>`,
	}
	if len(body) > 0 {
		parts = append(parts, "<p>"+strings.Join(body, "\n")+"</p>")
	}
	parts = append(parts, "</div>")
	return strings.Join(parts, "\n")
}

// ResolveGlossary parses glossary body lines into HTML with dl/dt/dd elements.
//
// Each non-empty line is expected as "**Term**: Definition text". The "**"
// markers are stripped and the term and definition are split on the first ": "
// separator. The result is wrapped in <div class="glossary">.
func ResolveGlossary(body []string) string {
	type entry struct{ term, definition string }
	var items []entry
	for _, line := range body {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		// Strip the ** markers around the term.
		line = boldTermRE.ReplaceAllString(line, "$1")
		term, definition := line, ""
		if index := strings.Index(line, ": "); index >= 0 {
			term, definition = line[:index], line[index+2:]
		}
		items = append(items, entry{
			term:       strings.TrimSpace(term),
			definition: strings.TrimSpace(definition),
		})
	}

	if len(items) == 0 {
		return `<div class="glossary"><dl></dl></div>`
	}

	parts := make([]string, 0, len(items)*2)
	for _, item := range items {
		parts = append(parts, "<dt><dfn>"+item.term+"</dfn></dt>")
		parts = append(parts, "<dd>"+item.definition+"</dd>")
	}
	return `<div class="glossary">` + "\n<dl>\n" +
		strings.Join(parts, "\n") + "\n</dl>\n</div>"
}

// ResolveContent resolves a content directive.
//
// The second result is false when name is not a content directive at all,
// which is how the resolver learns to try the language extractors instead.
// An error is the hard-error family: a directive that reads source code in a
// project that declares none, a malformed CV, or a schema this project cannot
// name -- each a condition where rendering a placeholder note would hide the
// fact that the page lost the content it asked for.
//
// config is the loaded selfdoc.json and may be nil, which several directives
// report in band because a build without a config still renders its pages.
func ResolveContent(
	name string,
	attrs map[string]string,
	body []string,
	baseDir string,
	config map[string]any,
) (string, bool, error) {
	if title, isCallout := calloutTitles[name]; isCallout {
		return resolveCallout(name, title, body), true, nil
	}
	switch name {
	case "list-glossary":
		return ResolveGlossary(body), true, nil
	case "list-tree":
		return ResolveListTree(attrs, baseDir), true, nil
	case "table-dep":
		return ResolveTableDep(attrs, baseDir), true, nil
	case "list-modules":
		if config == nil {
			return "> *[selfdoc: list-modules requires project config]*", true, nil
		}
		rendered, err := ResolveListModules(attrs, config, baseDir)
		return rendered, true, err
	case "table-directives":
		rendered, err := ResolveTableDirectives()
		return rendered, true, err
	case "table-config-schema":
		rendered, err := ResolveTableConfigSchema()
		return rendered, true, err
	case "table-endpoint":
		rendered, err := ResolveTableEndpoint(attrs, baseDir)
		return rendered, true, err
	case "list-crawlers":
		return ResolveListCrawlers(), true, nil
	case "var":
		if config == nil {
			return "> *[selfdoc: var requires project config]*", true, nil
		}
		rendered, err := ResolveVar(attrs, config, baseDir)
		return rendered, true, err
	case "cv":
		rendered, err := ResolveCV(attrs, config, baseDir)
		return rendered, true, err
	case "table-commands":
		if config == nil {
			return "> *[selfdoc: table-commands requires project config]*", true, nil
		}
		rendered, err := ResolveTableCommands(attrs, config, baseDir)
		return rendered, true, err
	}
	return "", false, nil
}

// marker renders one of the notes this package leaves in place of content it
// could not produce.
func marker(format string, args ...any) string {
	return "> *[selfdoc: " + fmt.Sprintf(format, args...) + "]*"
}
