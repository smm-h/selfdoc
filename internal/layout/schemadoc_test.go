package layout

import (
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"testing"
)

// schemaPath is the strictspec schema governing a directory's ownership
// manifest, relative to this package.
const schemaPath = "../../.strictspec/directory-manifest.schema.toml"

// layoutIdentifierPattern finds every "layout.<Name>" the schema's prose
// names.
var layoutIdentifierPattern = regexp.MustCompile(`\blayout\.([A-Z]\w*)`)

// TestTheSchemaNamesIdentifiersThisPackageDeclares pins the schema's prose to
// this package's surface.
//
// The schema explains itself by naming the functions that read a manifest, and
// its text is embedded verbatim in the generated validator, so a renamed
// function leaves two files describing a call nothing can make. Nothing else
// binds the two: the generator copies the comment without reading it.
func TestTheSchemaNamesIdentifiersThisPackageDeclares(t *testing.T) {
	raw, err := os.ReadFile(schemaPath)
	if err != nil {
		t.Fatalf("reading the schema: %v", err)
	}

	declared := declaredNames(t)
	named := map[string]bool{}
	for _, match := range layoutIdentifierPattern.FindAllStringSubmatch(string(raw), -1) {
		named[match[1]] = true
	}
	if len(named) == 0 {
		t.Fatal("the schema names no identifier of this package at all")
	}

	var missing []string
	for name := range named {
		if !declared[name] {
			missing = append(missing, name)
		}
	}
	sort.Strings(missing)
	for _, name := range missing {
		t.Errorf("the schema names layout.%s, which this package does not declare", name)
	}
}

// declaredNames is every exported top-level name this package declares:
// functions, types, constants and variables.
func declaredNames(t *testing.T) map[string]bool {
	t.Helper()
	names := map[string]bool{}
	entries, err := filepath.Glob("*.go")
	if err != nil {
		t.Fatalf("listing the package's files: %v", err)
	}
	fileSet := token.NewFileSet()
	for _, path := range entries {
		parsed, err := parser.ParseFile(fileSet, path, nil, parser.SkipObjectResolution)
		if err != nil {
			t.Fatalf("parsing %s: %v", path, err)
		}
		for _, decl := range parsed.Decls {
			switch declared := decl.(type) {
			case *ast.FuncDecl:
				// A method is named on its receiver, which the schema
				// never spells.
				if declared.Recv == nil {
					names[declared.Name.Name] = true
				}
			case *ast.GenDecl:
				for _, spec := range declared.Specs {
					switch named := spec.(type) {
					case *ast.TypeSpec:
						names[named.Name.Name] = true
					case *ast.ValueSpec:
						for _, ident := range named.Names {
							names[ident.Name] = true
						}
					}
				}
			}
		}
	}
	return names
}
