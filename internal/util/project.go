package util

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strings"

	"github.com/BurntSushi/toml"
)

// UnknownField is the value [ReadProjectField] returns when no manifest
// answers -- the sentinel string the Python surface returned, which templates
// and pages render verbatim.
const UnknownField = "unknown"

// DetectProjectVersion reads the project's version out of its manifest files.
//
// A source language declared in baseDir's selfdoc.json picks the manifest the
// version is read from (go -> VERSION, python -> pyproject.toml, js/node ->
// package.json), so a polyglot repository's incidental manifests -- a private
// browser-test harness's package.json at the root of a Go project, whose
// version field is conventionally 0.0.0 -- cannot win. That is the version
// counterpart of the rule [ReadProjectField] applies to the project name.
//
// Without a declaration, or when the picked manifest is absent or carries no
// version, the original lookup chain applies: pyproject.toml's
// [project].version, then package.json's "version", then a plain-text VERSION
// file. It returns fallback when no version is found.
func DetectProjectVersion(baseDir, fallback string) string {
	if lang := declaredSourceLanguage(baseDir); lang != "" {
		var version string
		switch lang {
		case "python":
			version = readPyprojectVersion(baseDir)
		case "go":
			version = readVersionFile(baseDir)
		case "js", "javascript", "node", "typescript":
			version = readPackageJSONVersion(baseDir)
		}
		if version != "" {
			return version
		}
		// A declared language without a readable version falls through.
	}
	for _, read := range []func(string) string{
		readPyprojectVersion,
		readPackageJSONVersion,
		readVersionFile,
	} {
		if version := read(baseDir); version != "" {
			return version
		}
	}
	return fallback
}

// ReadProjectField reads a project metadata field from the project's manifest.
//
// A source language declared in baseDir's selfdoc.json picks the manifest (go
// -> go.mod, python -> pyproject.toml, js/node -> package.json), so a polyglot
// repository's incidental manifests cannot win. Without a declaration, or when
// the picked manifest is absent or unreadable, the original lookup chain
// applies: pyproject.toml, then package.json, then go.mod.
//
// The "version" field is answered by [DetectProjectVersion] with
// [UnknownField] as the fallback. Every other unanswerable field is
// [UnknownField] too -- this surface reports absence in band, as the templates
// consuming it expect, and never as an error.
func ReadProjectField(baseDir, field string) string {
	if field == "version" {
		return DetectProjectVersion(baseDir, UnknownField)
	}

	if lang := declaredSourceLanguage(baseDir); lang != "" {
		switch lang {
		case "python":
			if pyproject := PathJoin(baseDir, "pyproject.toml"); isFile(pyproject) {
				return readTOMLField(pyproject, field)
			}
		case "go":
			if field == "name" {
				if name := readGoModName(baseDir); name != UnknownField {
					return name
				}
			}
		case "js", "javascript", "node", "typescript":
			if name := readPackageJSONField(baseDir, field); name != UnknownField {
				return name
			}
		}
		// A declared language without a readable manifest falls through.
	}

	if pyproject := PathJoin(baseDir, "pyproject.toml"); isFile(pyproject) {
		return readTOMLField(pyproject, field)
	}
	if isFile(PathJoin(baseDir, "package.json")) {
		return readPackageJSONField(baseDir, field)
	}
	if isFile(PathJoin(baseDir, "go.mod")) {
		if field == "name" {
			return readGoModName(baseDir)
		}
		return UnknownField
	}
	return UnknownField
}

// isFile reports whether path exists and is a regular file.
func isFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}

// readPyprojectVersion is the [project].version of baseDir's pyproject.toml,
// or "" when it is absent or unreadable.
func readPyprojectVersion(baseDir string) string {
	path := PathJoin(baseDir, "pyproject.toml")
	if !isFile(path) {
		return ""
	}
	var doc struct {
		Project struct {
			Version string `toml:"version"`
		} `toml:"project"`
	}
	if _, err := toml.DecodeFile(path, &doc); err != nil {
		return ""
	}
	return doc.Project.Version
}

// readPackageJSONVersion is the "version" of baseDir's package.json, or ""
// when it is absent or unreadable.
func readPackageJSONVersion(baseDir string) string {
	path := PathJoin(baseDir, "package.json")
	if !isFile(path) {
		return ""
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	var doc struct {
		Version string `json:"version"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		return ""
	}
	return doc.Version
}

// readVersionFile is the trimmed contents of baseDir's VERSION file, or ""
// when it is absent or unreadable.
func readVersionFile(baseDir string) string {
	path := PathJoin(baseDir, "VERSION")
	if !isFile(path) {
		return ""
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

// declaredSourceLanguage is the lower-cased language of the first entry in
// baseDir's selfdoc.json "source" array, or "".
func declaredSourceLanguage(baseDir string) string {
	data, err := os.ReadFile(PathJoin(baseDir, "selfdoc.json"))
	if err != nil {
		return ""
	}
	var doc struct {
		Source []struct {
			Language string `json:"language"`
		} `json:"source"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		return ""
	}
	if len(doc.Source) == 0 {
		return ""
	}
	return strings.ToLower(doc.Source[0].Language)
}

// readPackageJSONField is a top-level field of baseDir's package.json rendered
// as text, or [UnknownField].
func readPackageJSONField(baseDir, field string) string {
	path := PathJoin(baseDir, "package.json")
	if !isFile(path) {
		return UnknownField
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return UnknownField
	}
	var doc map[string]any
	if err := json.Unmarshal(data, &doc); err != nil {
		return UnknownField
	}
	value, ok := doc[field]
	if !ok {
		return UnknownField
	}
	return renderManifestValue(value)
}

// goModModuleRe matches a go.mod module declaration on a trimmed line.
var goModModuleRe = regexp.MustCompile(`^module\s+(.+)`)

// readGoModName is the module path declared by baseDir's go.mod, or
// [UnknownField].
func readGoModName(baseDir string) string {
	path := PathJoin(baseDir, "go.mod")
	if !isFile(path) {
		return UnknownField
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return UnknownField
	}
	for _, line := range strings.Split(string(data), "\n") {
		if m := goModModuleRe.FindStringSubmatch(strings.TrimSpace(line)); m != nil {
			return strings.TrimSpace(m[1])
		}
	}
	return UnknownField
}

// readTOMLField is a field of path's [project] table rendered as text, or
// [UnknownField].
func readTOMLField(path, field string) string {
	var doc map[string]any
	if _, err := toml.DecodeFile(path, &doc); err != nil {
		return UnknownField
	}
	project, ok := doc["project"].(map[string]any)
	if !ok {
		return UnknownField
	}
	value, ok := project[field]
	if !ok {
		return UnknownField
	}
	return renderManifestValue(value)
}

// renderManifestValue renders a decoded manifest value the way Python's str()
// did on the same value: a string unchanged, and anything else through the
// default formatting.
func renderManifestValue(value any) string {
	if s, ok := value.(string); ok {
		return s
	}
	return fmt.Sprint(value)
}
