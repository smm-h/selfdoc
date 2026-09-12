package extractors

import (
	"reflect"
	"testing"
)

func strptr(s string) *string { return &s }

// TestParseDocstringSections drives the parser with the docstrings the Python
// implementation was probed on; every expectation below is the structure
// python3 produced for the same input.
func TestParseDocstringSections(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		doc  string
		want DocSections
	}{
		{
			name: "basic args and returns",
			doc: "Do something useful.\n" +
				"\n" +
				"Args:\n" +
				"    x: The first value.\n" +
				"    y: The second value.\n" +
				"\n" +
				"Returns:\n" +
				"    The sum of x and y.",
			want: DocSections{
				Description: "Do something useful.",
				Params: []DocParam{
					{Name: "x", Description: "The first value."},
					{Name: "y", Description: "The second value."},
				},
				Returns: strptr("The sum of x and y."),
			},
		},
		{
			name: "typed params",
			doc: "Process data.\n" +
				"\n" +
				"Args:\n" +
				"    name (str): The name to use.\n" +
				"    count (int): How many times.",
			want: DocSections{
				Description: "Process data.",
				Params: []DocParam{
					{Name: "name", Type: strptr("str"), Description: "The name to use."},
					{Name: "count", Type: strptr("int"), Description: "How many times."},
				},
			},
		},
		{
			name: "raises section",
			doc: "Open a file.\n" +
				"\n" +
				"Raises:\n" +
				"    FileNotFoundError: If the file does not exist.\n" +
				"    PermissionError: If access is denied.",
			want: DocSections{
				Description: "Open a file.",
				Raises: []DocRaise{
					{Type: "FileNotFoundError", Description: "If the file does not exist."},
					{Type: "PermissionError", Description: "If access is denied."},
				},
			},
		},
		{
			name: "no sections keeps the paragraph break",
			doc:  "Just a simple description.\n\nWith a second paragraph.",
			want: DocSections{Description: "Just a simple description.\n\nWith a second paragraph."},
		},
		{
			name: "empty docstring",
			doc:  "",
			want: DocSections{},
		},
		{
			name: "continuation lines join onto the previous param",
			doc: "Do work.\n" +
				"\n" +
				"Args:\n" +
				"    path: The file path to process,\n" +
				"        which can be relative or absolute.\n" +
				"    mode: The mode to use.",
			want: DocSections{
				Description: "Do work.",
				Params: []DocParam{
					{Name: "path", Description: "The file path to process, which can be relative or absolute."},
					{Name: "mode", Description: "The mode to use."},
				},
			},
		},
		{
			name: "star args and kwargs keep their prefixes",
			doc: "Flexible function.\n" +
				"\n" +
				"Args:\n" +
				"    *args: Positional arguments.\n" +
				"    **kwargs: Keyword arguments.",
			want: DocSections{
				Description: "Flexible function.",
				Params: []DocParam{
					{Name: "*args", Description: "Positional arguments."},
					{Name: "**kwargs", Description: "Keyword arguments."},
				},
			},
		},
		{
			name: "yields is read as the return section",
			doc:  "Stream it.\n\nYields:\n    One row at a time.",
			want: DocSections{Description: "Stream it.", Returns: strptr("One row at a time.")},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ParseDocstringSections(tt.doc)
			if got.Description != tt.want.Description {
				t.Errorf("description = %q, want %q", got.Description, tt.want.Description)
			}
			if !reflect.DeepEqual(derefParams(got.Params), derefParams(tt.want.Params)) {
				t.Errorf("params = %#v, want %#v", derefParams(got.Params), derefParams(tt.want.Params))
			}
			if !reflect.DeepEqual(got.Raises, tt.want.Raises) {
				t.Errorf("raises = %#v, want %#v", got.Raises, tt.want.Raises)
			}
			switch {
			case got.Returns == nil && tt.want.Returns == nil:
			case got.Returns == nil || tt.want.Returns == nil:
				t.Errorf("returns = %v, want %v", got.Returns, tt.want.Returns)
			case *got.Returns != *tt.want.Returns:
				t.Errorf("returns = %q, want %q", *got.Returns, *tt.want.Returns)
			}
		})
	}
}

// derefParams flattens a param list so the comparison reads types by value
// rather than by pointer identity.
func derefParams(params []DocParam) []struct {
	Name, Type, Description string
} {
	var out []struct {
		Name, Type, Description string
	}
	for _, p := range params {
		typeName := "<none>"
		if p.Type != nil {
			typeName = *p.Type
		}
		out = append(out, struct {
			Name, Type, Description string
		}{p.Name, typeName, p.Description})
	}
	return out
}

// TestFormatDocstring drives the renderer with the docstrings the Python
// implementation was probed on; every expectation below is the string python3
// produced for the same input and base level.
func TestFormatDocstring(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name      string
		raw       string
		baseLevel int
		want      string
	}{
		{
			name:      "wrapped prose is joined and a code block is left verbatim",
			raw:       "Manages configuration loading for the whole\napplication, resolving defaults and env overrides.\n\n    run()\n    done()\n",
			baseLevel: 2,
			want:      "Manages configuration loading for the whole application, resolving defaults and env overrides.\n\n    run()\n    done()\n",
		},
		{
			name:      "blank-line paragraph breaks are kept",
			raw:       "First paragraph\nwrapped line.\n\nSecond paragraph\nwrapped.",
			baseLevel: 2,
			want:      "First paragraph wrapped line.\n\nSecond paragraph wrapped.",
		},
		{
			name:      "a heading is not joined into the line below it",
			raw:       "# Usage\nCall it.\n",
			baseLevel: 2,
			want:      "### Usage\nCall it.\n",
		},
		{
			name:      "headings are renested under the emitting heading",
			raw:       "Intro.\n\n# Usage\n\nHow.\n\n## Detail\n\nMore.\n",
			baseLevel: 3,
			want:      "Intro.\n\n#### Usage\n\nHow.\n\n##### Detail\n\nMore.\n",
		},
		{
			name:      "a heading inside a fence is content",
			raw:       "Intro.\n\n```\n# not a heading\n```\n\n# Usage\n\nHow.\n",
			baseLevel: 2,
			want:      "Intro.\n\n```\n# not a heading\n```\n\n### Usage\n\nHow.\n",
		},
		{
			name:      "a doc already nested deeply enough is left alone",
			raw:       "Intro.\n\n#### Deep\n\nText.\n",
			baseLevel: 2,
			want:      "Intro.\n\n#### Deep\n\nText.\n",
		},
		{
			name:      "an args section becomes a bold header and a bullet list",
			raw:       "Say hello to someone.\n\nArgs:\n    name: The person to greet.\n    loud: Whether to shout.\n",
			baseLevel: 2,
			want:      "Say hello to someone.\n\n**Args:**\n\n- `name`: The person to greet.\n- `loud`: Whether to shout.\n",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := FormatDocstring(tt.raw, tt.baseLevel); got != tt.want {
				t.Fatalf("FormatDocstring =\n%q\nwant\n%q", got, tt.want)
			}
		})
	}
}

func TestIsParamLine(t *testing.T) {
	t.Parallel()
	tests := []struct {
		text string
		want bool
	}{
		{"name: description", true},
		{"name (str): description", true},
		{"*args: things", true},
		{"**kwargs: things", true},
		{"dotted.name: description", true},
		{"kebab-name: description", true},
		{": no name", false},
		{"no colon here", false},
		{"a sentence with spaces: and a colon", false},
	}
	for _, tt := range tests {
		t.Run(tt.text, func(t *testing.T) {
			if got := isParamLine(tt.text); got != tt.want {
				t.Fatalf("isParamLine(%q) = %v, want %v", tt.text, got, tt.want)
			}
		})
	}
}

func TestSplitParamLine(t *testing.T) {
	t.Parallel()
	name, desc := splitParamLine("path (str): the file")
	if name != "path (str)" || desc != "the file" {
		t.Fatalf("splitParamLine = (%q, %q)", name, desc)
	}
	name, desc = splitParamLine("flag:")
	if name != "flag" || desc != "" {
		t.Fatalf("splitParamLine = (%q, %q)", name, desc)
	}
}

func TestMatchSectionHeader(t *testing.T) {
	t.Parallel()
	if name, ok := matchSectionHeader("Args:"); !ok || name != "Args" {
		t.Fatalf("matchSectionHeader(\"Args:\") = (%q, %v)", name, ok)
	}
	if name, ok := matchSectionHeader("See Also:"); !ok || name != "See Also" {
		t.Fatalf("matchSectionHeader(\"See Also:\") = (%q, %v)", name, ok)
	}
	if _, ok := matchSectionHeader("Whatever:"); ok {
		t.Fatal("an unrecognized header was accepted")
	}
	if _, ok := matchSectionHeader("Args"); ok {
		t.Fatal("a header with no colon was accepted")
	}
}
