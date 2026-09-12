package util

import (
	"os"
	"path/filepath"
	"testing"
)

// writeTree writes files into a fresh temporary directory and returns it. The
// keys are repo-relative paths.
func writeTree(t *testing.T, files map[string]string) string {
	t.Helper()
	dir := t.TempDir()
	for name, content := range files {
		path := filepath.Join(dir, name)
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return dir
}

const (
	pyprojectWithVersion = "[project]\nname = \"demo\"\nversion = \"1.2.3\"\ndescription = \"A demo\"\n"
	packageJSONWithAll   = "{\"name\": \"demo-js\", \"version\": \"0.0.0\", \"description\": \"JS demo\"}\n"
)

func TestDetectProjectVersion(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		files map[string]string
		want  string
	}{
		{
			name:  "nothing found returns the fallback",
			files: map[string]string{"README.md": "hi"},
			want:  "FALLBACK",
		},
		{
			name:  "pyproject wins the undeclared chain",
			files: map[string]string{"pyproject.toml": pyprojectWithVersion, "package.json": packageJSONWithAll, "VERSION": "9.9.9\n"},
			want:  "1.2.3",
		},
		{
			name:  "package.json is next in the undeclared chain",
			files: map[string]string{"package.json": packageJSONWithAll, "VERSION": "9.9.9\n"},
			want:  "0.0.0",
		},
		{
			name:  "VERSION is last in the undeclared chain",
			files: map[string]string{"VERSION": "9.9.9\n"},
			want:  "9.9.9",
		},
		{
			name: "a declared go source picks VERSION over an incidental package.json",
			files: map[string]string{
				"selfdoc.json":   `{"source": [{"language": "go", "path": "."}]}`,
				"package.json":   packageJSONWithAll,
				"pyproject.toml": pyprojectWithVersion,
				"VERSION":        "9.9.9\n",
			},
			want: "9.9.9",
		},
		{
			name: "a declared python source picks pyproject",
			files: map[string]string{
				"selfdoc.json":   `{"source": [{"language": "Python"}]}`,
				"package.json":   packageJSONWithAll,
				"pyproject.toml": pyprojectWithVersion,
			},
			want: "1.2.3",
		},
		{
			name: "a declared node source picks package.json",
			files: map[string]string{
				"selfdoc.json":   `{"source": [{"language": "typescript"}]}`,
				"pyproject.toml": pyprojectWithVersion,
				"package.json":   packageJSONWithAll,
			},
			want: "0.0.0",
		},
		{
			name: "a declared language with no readable version falls through",
			files: map[string]string{
				"selfdoc.json":   `{"source": [{"language": "go"}]}`,
				"pyproject.toml": pyprojectWithVersion,
			},
			want: "1.2.3",
		},
		{
			name: "an unknown declared language falls through",
			files: map[string]string{
				"selfdoc.json": `{"source": [{"language": "cobol"}]}`,
				"VERSION":      "9.9.9\n",
			},
			want: "9.9.9",
		},
		{
			name:  "a malformed manifest is treated as absent",
			files: map[string]string{"pyproject.toml": "[project\nbroken", "VERSION": "9.9.9\n"},
			want:  "9.9.9",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			dir := writeTree(t, tt.files)
			if got := DetectProjectVersion(dir, "FALLBACK"); got != tt.want {
				t.Errorf("DetectProjectVersion = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestReadProjectField(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		files map[string]string
		field string
		want  string
	}{
		{
			name:  "version delegates to the version chain",
			files: map[string]string{"pyproject.toml": pyprojectWithVersion},
			field: "version",
			want:  "1.2.3",
		},
		{
			name:  "an unanswerable version is the unknown sentinel",
			files: map[string]string{"README.md": "hi"},
			field: "version",
			want:  UnknownField,
		},
		{
			name:  "name from pyproject",
			files: map[string]string{"pyproject.toml": pyprojectWithVersion},
			field: "name",
			want:  "demo",
		},
		{
			name:  "description from pyproject",
			files: map[string]string{"pyproject.toml": pyprojectWithVersion},
			field: "description",
			want:  "A demo",
		},
		{
			name:  "a missing pyproject field is the unknown sentinel",
			files: map[string]string{"pyproject.toml": pyprojectWithVersion},
			field: "license",
			want:  UnknownField,
		},
		{
			name:  "name from package.json",
			files: map[string]string{"package.json": packageJSONWithAll},
			field: "name",
			want:  "demo-js",
		},
		{
			name:  "name from go.mod",
			files: map[string]string{"go.mod": "module github.com/smm-h/demo\n\ngo 1.26\n"},
			field: "name",
			want:  "github.com/smm-h/demo",
		},
		{
			name:  "a go.mod answers no field other than the name",
			files: map[string]string{"go.mod": "module github.com/smm-h/demo\n"},
			field: "description",
			want:  UnknownField,
		},
		{
			name: "a declared go source picks go.mod over an incidental package.json",
			files: map[string]string{
				"selfdoc.json": `{"source": [{"language": "go"}]}`,
				"go.mod":       "module github.com/smm-h/demo\n",
				"package.json": packageJSONWithAll,
			},
			field: "name",
			want:  "github.com/smm-h/demo",
		},
		{
			name: "a declared go source falls through for a field go.mod cannot answer",
			files: map[string]string{
				"selfdoc.json":   `{"source": [{"language": "go"}]}`,
				"go.mod":         "module github.com/smm-h/demo\n",
				"pyproject.toml": pyprojectWithVersion,
			},
			field: "description",
			want:  "A demo",
		},
		{
			name:  "no manifest at all is the unknown sentinel",
			files: map[string]string{"README.md": "hi"},
			field: "name",
			want:  UnknownField,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			dir := writeTree(t, tt.files)
			if got := ReadProjectField(dir, tt.field); got != tt.want {
				t.Errorf("ReadProjectField(%q) = %q, want %q", tt.field, got, tt.want)
			}
		})
	}
}
