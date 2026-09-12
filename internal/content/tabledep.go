package content

import (
	"os"
	"regexp"
	"strings"

	"github.com/BurntSushi/toml"
	"github.com/smm-h/selfdoc/internal/tables"
	"github.com/smm-h/selfdoc/internal/util"
)

// depSpecifierRE splits a PEP 508 dependency specifier at the end of its name:
// everything a distribution name may carry, then the rest.
var depSpecifierRE = regexp.MustCompile(`^([A-Za-z0-9_\-.\[\]]+)\s*(.*)`)

// pyprojectDeps is the part of a pyproject.toml this directive reads.
type pyprojectDeps struct {
	Project struct {
		Dependencies         []string            `toml:"dependencies"`
		OptionalDependencies map[string][]string `toml:"optional-dependencies"`
	} `toml:"project"`
}

// ResolveTableDep parses a pyproject.toml and produces a Markdown dependency
// table: the project's own dependencies, then one labelled block per
// optional-dependency group, in the order the document declares them.
func ResolveTableDep(attrs map[string]string, baseDir string) string {
	path := attrs["path"]
	if path == "" {
		return marker("table-dep requires a path attribute")
	}

	fullPath := util.ResolveDirectivePath(baseDir, path)
	info, err := os.Stat(fullPath)
	if err != nil || !info.Mode().IsRegular() {
		return marker("file '%s' not found", path)
	}

	raw, err := os.ReadFile(fullPath)
	if err != nil {
		return marker("cannot parse '%s': %s", path, err)
	}
	var document pyprojectDeps
	metadata, err := toml.Decode(string(raw), &document)
	if err != nil {
		return marker("cannot parse '%s': %s", path, err)
	}

	var rows [][]string
	for _, spec := range document.Project.Dependencies {
		name, constraint := parseDepSpecifier(spec)
		rows = append(rows, []string{"`" + name + "`", constraint})
	}

	for _, group := range optionalGroupOrder(metadata, document) {
		rows = append(rows, []string{"**[" + group + "]**", ""})
		for _, spec := range document.Project.OptionalDependencies[group] {
			name, constraint := parseDepSpecifier(spec)
			rows = append(rows, []string{"`" + name + "`", constraint})
		}
	}

	if len(rows) == 0 {
		return marker("no dependencies found in '%s'", path)
	}

	rendered, err := tables.RenderMarkdownTable(
		[]string{"Package", "Version Constraint"}, rows, nil, false,
	)
	if err != nil {
		return marker("cannot render '%s': %s", path, err)
	}
	return rendered
}

// optionalGroupOrder lists the optional-dependency group names in the order
// the document declares them.
//
// A Go map has no order, so the order comes from the decoder's own record of
// the keys it saw. Reordering a project's extras would misreport the document
// the page claims to show.
func optionalGroupOrder(metadata toml.MetaData, document pyprojectDeps) []string {
	groups := make([]string, 0, len(document.Project.OptionalDependencies))
	seen := map[string]bool{}
	for _, key := range metadata.Keys() {
		parts := []string(key)
		if len(parts) != 3 || parts[0] != "project" ||
			parts[1] != "optional-dependencies" {
			continue
		}
		name := parts[2]
		if seen[name] {
			continue
		}
		if _, declared := document.Project.OptionalDependencies[name]; !declared {
			continue
		}
		seen[name] = true
		groups = append(groups, name)
	}
	return groups
}

// parseDepSpecifier splits a PEP 508 dependency specifier into its package and
// its version constraint:
//
//	"requests>=2.0"              -> ("requests", ">=2.0")
//	"flask"                      -> ("flask", "*")
//	"black[jupyter]>=23.0,<24.0" -> ("black[jupyter]", ">=23.0,<24.0")
//
// An environment marker is dropped: it says when the dependency applies, not
// which version.
func parseDepSpecifier(spec string) (string, string) {
	match := depSpecifierRE.FindStringSubmatch(spec)
	if match == nil {
		return strings.TrimSpace(spec), "*"
	}
	name := strings.TrimSpace(match[1])
	constraint := strings.TrimSpace(match[2])
	if index := strings.Index(constraint, ";"); index >= 0 {
		constraint = strings.TrimSpace(constraint[:index])
	}
	if constraint == "" {
		return name, "*"
	}
	return name, constraint
}
