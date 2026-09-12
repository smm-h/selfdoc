package directives

import (
	"errors"
	"reflect"
	"strings"
	"testing"
)

// names builds a NameSet from the given names.
func names(v ...string) NameSet {
	s := make(NameSet, len(v))
	for _, n := range v {
		s[n] = struct{}{}
	}
	return s
}

// mustParse parses content and fails the test on any error.
func mustParse(t *testing.T, content string, validNames NameSet) []Directive {
	t.Helper()
	got, err := ParseDirectives(content, validNames)
	if err != nil {
		t.Fatalf("ParseDirectives(%q) returned error %v", content, err)
	}
	return got
}

// mustResolve resolves content and fails the test on any error.
func mustResolve(t *testing.T, content string, resolver Resolver, validNames NameSet) string {
	t.Helper()
	got, err := ResolveDirectives(content, resolver, validNames)
	if err != nil {
		t.Fatalf("ResolveDirectives(%q) returned error %v", content, err)
	}
	return got
}

// wantErr asserts err is non-nil and its message contains want.
func wantErr(t *testing.T, err error, want string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected an error containing %q, got nil", want)
	}
	if !strings.Contains(err.Error(), want) {
		t.Fatalf("error %q does not contain %q", err.Error(), want)
	}
}

func TestParseDirectives(t *testing.T) {
	tests := []struct {
		name    string
		content string
		valid   NameSet
		want    []Directive
	}{
		{
			name:    "one-liner with no attrs",
			content: ":-: ref",
			want: []Directive{{
				Name: "ref", Attrs: map[string]string{}, Body: []string{}, LineNumber: 1,
			}},
		},
		{
			name:    "one-liner with attrs",
			content: `:-: ref src="selfdoc.config" lang="python"`,
			want: []Directive{{
				Name:       "ref",
				Attrs:      map[string]string{"src": "selfdoc.config", "lang": "python"},
				Body:       []string{},
				LineNumber: 1,
			}},
		},
		{
			name:    "one-liner single attr holding a space",
			content: `:-: code-help cmd="selfdoc --help"`,
			want: []Directive{{
				Name:       "code-help",
				Attrs:      map[string]string{"cmd": "selfdoc --help"},
				Body:       []string{},
				LineNumber: 1,
			}},
		},
		{
			name:    "one-liner hyphenated attr key",
			content: `:-: table-commands schema-dir="."`,
			want: []Directive{{
				Name:       "table-commands",
				Attrs:      map[string]string{"schema-dir": "."},
				Body:       []string{},
				LineNumber: 1,
			}},
		},
		{
			name:    "inline hyphenated attr key",
			content: `See :-: table-commands schema-dir="sub" inline.`,
			want: []Directive{{
				Name:       "table-commands",
				Attrs:      map[string]string{"schema-dir": "sub"},
				Body:       []string{},
				LineNumber: 1,
				Inline:     true,
				Column:     intp(4),
			}},
		},
		{
			name:    "block with attr lines only",
			content: ":<: ref\n:@: src=\"selfdoc.config\"\n:@: lang=\"python\"\n:>:",
			want: []Directive{{
				Name:       "ref",
				Attrs:      map[string]string{"src": "selfdoc.config", "lang": "python"},
				Body:       []string{},
				LineNumber: 1,
			}},
		},
		{
			name:    "block with inline attrs",
			content: ":<: ref src=\"selfdoc.config\"\n:>:",
			want: []Directive{{
				Name:       "ref",
				Attrs:      map[string]string{"src": "selfdoc.config"},
				Body:       []string{},
				LineNumber: 1,
			}},
		},
		{
			name:    "block merges inline and line attrs",
			content: ":<: ref src=\"selfdoc.config\"\n:@: lang=\"python\"\n:>:",
			want: []Directive{{
				Name:       "ref",
				Attrs:      map[string]string{"src": "selfdoc.config", "lang": "python"},
				Body:       []string{},
				LineNumber: 1,
			}},
		},
		{
			name:    "block with body only",
			content: ":<: callout-note\n:=:\n::: This is a note.\n::: Second line.\n:>:",
			want: []Directive{{
				Name:       "callout-note",
				Attrs:      map[string]string{},
				Body:       []string{"This is a note.", "Second line."},
				LineNumber: 1,
			}},
		},
		{
			name:    "body line prefix is four characters",
			content: ":<: callout-note\n:=:\n::: Hello world\n:>:",
			want: []Directive{{
				Name:       "callout-note",
				Attrs:      map[string]string{},
				Body:       []string{"Hello world"},
				LineNumber: 1,
			}},
		},
		{
			name:    "bare body marker is an empty body line",
			content: ":<: callout-note\n:=:\n::: \n:>:",
			want: []Directive{{
				Name:       "callout-note",
				Attrs:      map[string]string{},
				Body:       []string{""},
				LineNumber: 1,
			}},
		},
		{
			name:    "block with attrs and body",
			content: ":<: code-test\n:@: file=\"tests/test_config.py\"\n:@: class=\"TestValidConfig\"\n:=:\n::: Extra context here.\n:>:",
			want: []Directive{{
				Name: "code-test",
				Attrs: map[string]string{
					"file": "tests/test_config.py", "class": "TestValidConfig",
				},
				Body:       []string{"Extra context here."},
				LineNumber: 1,
			}},
		},
		{
			name:    "empty block",
			content: ":<: ref\n:>:",
			want: []Directive{{
				Name: "ref", Attrs: map[string]string{}, Body: []string{}, LineNumber: 1,
			}},
		},
		{
			name: "several directives keep their line numbers",
			content: "# Heading\n\n:-: ref src=\"selfdoc.config\"\n\nSome text.\n\n" +
				":<: code-test\n:@: file=\"tests/test_config.py\"\n:>:\n",
			want: []Directive{
				{
					Name:       "ref",
					Attrs:      map[string]string{"src": "selfdoc.config"},
					Body:       []string{},
					LineNumber: 3,
				},
				{
					Name:       "code-test",
					Attrs:      map[string]string{"file": "tests/test_config.py"},
					Body:       []string{},
					LineNumber: 7,
				},
			},
		},
		{
			name:    "several attrs on one line",
			content: `:-: ref src="a.py" lang="python" version="3"`,
			want: []Directive{{
				Name: "ref",
				Attrs: map[string]string{
					"src": "a.py", "lang": "python", "version": "3",
				},
				Body:       []string{},
				LineNumber: 1,
			}},
		},
		{
			name:    "directive inside a backtick fence is ignored",
			content: "```\n:-: ref src=\"selfdoc.config\"\n```\n",
			want:    nil,
		},
		{
			name:    "directive inside a tilde fence is ignored",
			content: "~~~\n:<: ref\n:>:\n~~~\n",
			want:    nil,
		},
		{
			name:    "block markers inside a fence are ignored",
			content: "```\n:<: ref\n:@: src=\"foo\"\n:=:\n::: body\n:>:\n```\n",
			want:    nil,
		},
		{
			name:    "directive after a closed fence is found",
			content: "```\n:-: ref src=\"inside\"\n```\n\n:-: ref src=\"outside\"\n",
			want: []Directive{{
				Name:       "ref",
				Attrs:      map[string]string{"src": "outside"},
				Body:       []string{},
				LineNumber: 5,
			}},
		},
		{
			name: "a longer fence needs a fence at least as long to close",
			content: "````\n:-: ref src=\"inside\"\n```\n" +
				":-: ref src=\"still_inside\"\n````\n",
			want: nil,
		},
		{
			name:    "empty content",
			content: "",
			want:    nil,
		},
		{
			name:    "non-directive content",
			content: "# Heading\n\nSome paragraph.\n\n- list item\n",
			want:    nil,
		},
		{
			name:    "a known name is accepted",
			content: `:-: ref src="foo"`,
			valid:   names("ref", "code-test"),
			want: []Directive{{
				Name:       "ref",
				Attrs:      map[string]string{"src": "foo"},
				Body:       []string{},
				LineNumber: 1,
			}},
		},
		{
			name:    "a nil name set accepts anything",
			content: `:-: totally-made-up-name src="whatever"`,
			want: []Directive{{
				Name:       "totally-made-up-name",
				Attrs:      map[string]string{"src": "whatever"},
				Body:       []string{},
				LineNumber: 1,
			}},
		},
		{
			name:    "inline directive is found with a column",
			content: "prefix :-: var end",
			want: []Directive{{
				Name:       "var",
				Attrs:      map[string]string{},
				Body:       []string{},
				LineNumber: 1,
				Inline:     true,
				Column:     intp(7),
			}},
		},
		{
			name:    "inline directive inside a fence is not found",
			content: "```\ntext :-: var end\n```\n",
			want:    nil,
		},
		{
			name:    "a standalone directive is not inline and has no column",
			content: `:-: ref src="foo"`,
			want: []Directive{{
				Name:       "ref",
				Attrs:      map[string]string{"src": "foo"},
				Body:       []string{},
				LineNumber: 1,
			}},
		},
		{
			name:    "standalone and inline directives are both found",
			content: ":-: ref src=\"foo\"\ntext :-: var end\n",
			want: []Directive{
				{
					Name:       "ref",
					Attrs:      map[string]string{"src": "foo"},
					Body:       []string{},
					LineNumber: 1,
				},
				{
					Name:       "var",
					Attrs:      map[string]string{},
					Body:       []string{},
					LineNumber: 2,
					Inline:     true,
					Column:     intp(5),
				},
			},
		},
		{
			name:    "inline directive parses attributes",
			content: `see :-: var key="val" here`,
			want: []Directive{{
				Name:       "var",
				Attrs:      map[string]string{"key": "val"},
				Body:       []string{},
				LineNumber: 1,
				Inline:     true,
				Column:     intp(4),
			}},
		},
		{
			name:    "inline directive inside a single-backtick span is not found",
			content: "see `:-: var` here",
			want:    nil,
		},
		{
			name:    "inline directive inside a double-backtick span is not found",
			content: "see ``:-: var`` here",
			want:    nil,
		},
		{
			name:    "inline directive name stops before trailing punctuation",
			content: "(v:-: test-dir).",
			valid:   names("test-dir"),
			want: []Directive{{
				Name:       "test-dir",
				Attrs:      map[string]string{},
				Body:       []string{},
				LineNumber: 1,
				Inline:     true,
				Column:     intp(2),
			}},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := mustParse(t, tc.content, tc.valid)
			// Attribute order has its own table (TestAttrOrderFollowsTheSource),
			// which also asserts AttrOrder and Attrs name the same keys. This
			// table is about everything else, so it compares without it rather
			// than restating a derived list on every case.
			for i := range got {
				got[i].AttrOrder = nil
			}
			if !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("ParseDirectives = %#v, want %#v", got, tc.want)
			}
		})
	}
}

func intp(v int) *int { return &v }

func TestParseDirectivesErrors(t *testing.T) {
	tests := []struct {
		name    string
		content string
		valid   NameSet
		want    string
	}{
		{
			name:    "unclosed block in the attrs state",
			content: ":<: ref\n:@: src=\"foo\"",
			want:    "Unclosed directive 'ref' opened at line 1",
		},
		{
			name:    "unclosed block in the body state",
			content: ":<: ref\n:=:\n::: body line",
			want:    "Unclosed directive 'ref' opened at line 1",
		},
		{
			name:    "unknown one-liner name",
			content: `:-: unknown-thing src="foo"`,
			valid:   names("ref", "code-test"),
			want:    "Unknown directive 'unknown-thing' at line 1",
		},
		{
			name:    "unknown block name",
			content: ":<: bad-name\n:>:",
			valid:   names("ref"),
			want:    "Unknown directive 'bad-name' at line 1",
		},
		{
			name:    "an ungrammatical standalone name is still refused",
			content: ":-: 123invalid",
			valid:   names("other"),
			want:    "Unknown directive '123invalid' at line 1",
		},
		{
			name:    "an inline name is validated like a standalone one",
			content: "text :-: valid-name more text",
			valid:   names("other-name"),
			want:    "Unknown directive 'valid-name' at line 1",
		},
		{
			name:    "attr line after the body separator",
			content: ":<: ref\n:=:\n:@: src=\"foo\"\n:>:",
			want:    `Unexpected line inside directive block at line 3: ':@: src="foo"'`,
		},
		{
			name:    "body line before the separator",
			content: ":<: ref\n::: body without separator\n:>:",
			want:    "Unexpected line inside directive block at line 2: '::: body without separator'",
		},
		{
			name:    "plain text in the attrs state",
			content: ":<: ref\njust some random text\n:>:",
			want:    "Unexpected line inside directive block at line 2: 'just some random text'",
		},
		{
			name:    "plain text in the body state",
			content: ":<: ref\n:=:\ntext without ::: prefix\n:>:",
			want:    "Unexpected line inside directive block at line 3: 'text without ::: prefix'",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			_, err := ParseDirectives(tc.content, tc.valid)
			wantErr(t, err, tc.want)
			var de *DirectiveError
			if !errors.As(err, &de) {
				t.Fatalf("error %T is not a *DirectiveError", err)
			}
		})
	}
}

func TestResolveDirectives(t *testing.T) {
	// bracket renders a directive as [name:src] so a test can see which
	// occurrence produced which output.
	bracket := func(name string, attrs map[string]string, body []string) (string, error) {
		return "[RESOLVED " + name + ": " + attrs["src"] + "]", nil
	}
	constant := func(text string) Resolver {
		return func(string, map[string]string, []string) (string, error) {
			return text, nil
		}
	}
	named := func(name string, attrs map[string]string, body []string) (string, error) {
		return "[" + name + "]", nil
	}
	refuse := func(name string, attrs map[string]string, body []string) (string, error) {
		return "", errors.New("resolver must not be called for " + name)
	}

	tests := []struct {
		name     string
		content  string
		resolver Resolver
		valid    NameSet
		want     string
	}{
		{
			name:     "one-liner is replaced",
			content:  "# Title\n\n:-: ref src=\"selfdoc.config\"\n\nFooter.\n",
			resolver: bracket,
			want:     "# Title\n\n[RESOLVED ref: selfdoc.config]\n\nFooter.\n",
		},
		{
			name:    "block is replaced",
			content: ":<: code-test\n:@: file=\"tests/test_foo.py\"\n:>:\n",
			resolver: func(name string, attrs map[string]string, body []string) (string, error) {
				return "[" + name + " file=" + attrs["file"] + "]", nil
			},
			want: "[code-test file=tests/test_foo.py]\n",
		},
		{
			name:     "non-directive content passes through",
			content:  "# Just markdown\n\nNo directives here.\n",
			resolver: refuse,
			want:     "# Just markdown\n\nNo directives here.\n",
		},
		{
			name:     "fenced content passes through",
			content:  "```\n:-: ref src=\"inside\"\n```\n",
			resolver: refuse,
			want:     "```\n:-: ref src=\"inside\"\n```\n",
		},
		{
			name:     "a known name is accepted",
			content:  `:-: ref src="foo"`,
			resolver: constant("ok"),
			valid:    names("ref"),
			want:     "ok",
		},
		{
			name:    "inline directive is substituted in place",
			content: `has :-: var key="x" features`,
			resolver: func(name string, attrs map[string]string, body []string) (string, error) {
				return "[" + name + ":" + attrs["key"] + "]", nil
			},
			want: "has [var:x] features",
		},
		{
			name:     "inline directive mid-sentence",
			content:  "The value is :-: version and more text.",
			resolver: constant("1.2.3"),
			want:     "The value is 1.2.3 and more text.",
		},
		{
			name:     "several inline directives on one line",
			content:  "A :-: foo then :-: bar end",
			resolver: named,
			want:     "A [foo] then [bar] end",
		},
		{
			name:     "a standalone directive still resolves through pass 1",
			content:  `:-: ref src="selfdoc.config"`,
			resolver: bracket,
			want:     "[RESOLVED ref: selfdoc.config]",
		},
		{
			name:     "inline directive inside a fence is literal",
			content:  "```\nuse :-: var key=\"x\" here\n```\n",
			resolver: refuse,
			want:     "```\nuse :-: var key=\"x\" here\n```\n",
		},
		{
			name:     "inline directive inside a single-backtick span is literal",
			content:  "see `:-: var key=\"x\"` for details",
			resolver: refuse,
			want:     "see `:-: var key=\"x\"` for details",
		},
		{
			name:     "inline directive inside a double-backtick span is literal",
			content:  "see ``:-: var key=\"x\"`` for details",
			resolver: refuse,
			want:     "see ``:-: var key=\"x\"`` for details",
		},
		{
			name:     "a span is preserved while the directive beside it resolves",
			content:  "text `code` then :-: var end",
			resolver: constant("[VAR]"),
			want:     "text `code` then [VAR] end",
		},
		{
			name:     "a double-backtick span is preserved beside a resolved directive",
			content:  "text ``code`` then :-: var end",
			resolver: constant("[VAR]"),
			want:     "text ``code`` then [VAR] end",
		},
		{
			name:     "single and double spans mask on the same line",
			content:  "`single` and ``double :-: var`` then :-: ref end",
			resolver: constant("[RESOLVED]"),
			want:     "`single` and ``double :-: var`` then [RESOLVED] end",
		},
		{
			name:    "trailing paren and period",
			content: "(v:-: test-dir).",
			resolver: func(name string, attrs map[string]string, body []string) (string, error) {
				if name != "test-dir" {
					return "", errors.New("unexpected directive name " + name)
				}
				return "1.0", nil
			},
			want: "(v1.0).",
		},
		{
			name:     "followed by a closing paren",
			content:  "result :-: name)",
			resolver: constant("VALUE"),
			want:     "result VALUE)",
		},
		{
			name:     "followed by a comma",
			content:  "text :-: name, and more",
			resolver: constant("VALUE"),
			want:     "text VALUE, and more",
		},
		{
			name:     "wrapped in brackets",
			content:  "[:-: name]",
			resolver: constant("VALUE"),
			want:     "[VALUE]",
		},
		{
			name:     "wrapped in angle brackets",
			content:  "<:-: name>",
			resolver: constant("VALUE"),
			want:     "<VALUE>",
		},
		{
			name:     "two parenthesised inline directives",
			content:  "(:-: a) and (:-: b).",
			resolver: named,
			want:     "([a]) and ([b]).",
		},
		{
			name:     "a plausible name resolves rather than being refused",
			content:  "text :-: some random text",
			resolver: constant("VALUE"),
			want:     "text VALUE random text",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := mustResolve(t, tc.content, tc.resolver, tc.valid)
			if got != tc.want {
				t.Fatalf("ResolveDirectives = %q, want %q", got, tc.want)
			}
		})
	}
}

func TestResolveDirectivesPassesAttrsAndBody(t *testing.T) {
	content := ":<: callout-note\n:@: style=\"info\"\n:=:\n::: Important note here.\n:>:\n"
	var gotName string
	var gotAttrs map[string]string
	var gotBody []string
	resolver := func(name string, attrs map[string]string, body []string) (string, error) {
		gotName, gotAttrs, gotBody = name, attrs, body
		return "replaced", nil
	}
	if _, err := ResolveDirectives(content, resolver, nil); err != nil {
		t.Fatalf("ResolveDirectives returned error %v", err)
	}
	if gotName != "callout-note" {
		t.Errorf("name = %q, want callout-note", gotName)
	}
	if !reflect.DeepEqual(gotAttrs, map[string]string{"style": "info"}) {
		t.Errorf("attrs = %#v", gotAttrs)
	}
	if !reflect.DeepEqual(gotBody, []string{"Important note here."}) {
		t.Errorf("body = %#v", gotBody)
	}
}

func TestResolveDirectivesErrors(t *testing.T) {
	t.Run("unclosed block during resolution", func(t *testing.T) {
		_, err := ResolveDirectives(":<: ref", func(string, map[string]string, []string) (string, error) {
			return "", nil
		}, nil)
		wantErr(t, err, "Unclosed directive 'ref' during resolution")
	})

	t.Run("multi-line output from an inline directive", func(t *testing.T) {
		_, err := ResolveDirectives("text :-: var end",
			func(string, map[string]string, []string) (string, error) {
				return "line1\nline2", nil
			}, nil)
		wantErr(t, err, "returned multi-line output")
		var ioe *InlineOutputError
		if !errors.As(err, &ioe) {
			t.Fatalf("error %T is not an *InlineOutputError", err)
		}
		if ioe.Name != "var" {
			t.Errorf("Name = %q, want var", ioe.Name)
		}
	})

	t.Run("malformed inline name", func(t *testing.T) {
		_, err := ResolveDirectives("text :-: my.directive here",
			func(string, map[string]string, []string) (string, error) {
				return "VALUE", nil
			}, nil)
		wantErr(t, err, "Malformed directive name 'my.directive' at line 1")
		wantErr(t, err, `names must match [a-zA-Z][\w-]*`)
	})

	t.Run("a resolver error aborts resolution", func(t *testing.T) {
		sentinel := errors.New("boom")
		_, err := ResolveDirectives(":-: ref",
			func(string, map[string]string, []string) (string, error) {
				return "", sentinel
			}, nil)
		if !errors.Is(err, sentinel) {
			t.Fatalf("error = %v, want the resolver's own error", err)
		}
	})
}

func TestValidateDirectiveNames(t *testing.T) {
	tests := []struct {
		name  string
		names []string
		want  string
	}{
		{name: "grammatical names", names: []string{"a", "a-b", "a_b", "a1", "ABC"}},
		{
			name:  "a leading digit is refused",
			names: []string{"3d-model"},
			want:  `Invalid directive name '3d-model': must match [a-zA-Z][\w-]*`,
		},
		{
			name:  "a leading underscore is refused",
			names: []string{"_private"},
			want:  `Invalid directive name '_private': must match [a-zA-Z][\w-]*`,
		},
		{
			name:  "a dot is refused",
			names: []string{"my.directive"},
			want:  `Invalid directive name 'my.directive': must match [a-zA-Z][\w-]*`,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			err := ValidateDirectiveNames(tc.names)
			if tc.want == "" {
				if err != nil {
					t.Fatalf("unexpected error %v", err)
				}
				return
			}
			wantErr(t, err, tc.want)
		})
	}
}

func TestFindDirectiveMarkers(t *testing.T) {
	tests := []struct {
		name    string
		content string
		want    []Marker
	}{
		{name: "empty content", content: ""},
		{name: "prose carries no marker", content: "# Heading\n\nJust prose.\n"},
		{
			name:    "each line marker is reported once",
			content: ":-: ref\n:<: ref\n:@: a=\"b\"\n:=:\n::: body\n:>:\n",
			want: []Marker{
				{1, ":-:"}, {2, ":<:"}, {3, ":@:"}, {4, ":=:"}, {5, ":::"}, {6, ":>:"},
			},
		},
		{
			name:    "an inline marker is reported",
			content: "see :-: version here",
			want:    []Marker{{1, ":-:"}},
		},
		{
			name:    "two inline markers on one line are reported twice",
			content: "a :-: one and :-: two",
			want:    []Marker{{1, ":-:"}, {1, ":-:"}},
		},
		{
			name:    "a marker inside a fence is skipped",
			content: "```\n:-: ref\n```\n",
		},
		{
			name:    "a marker inside a backtick span is skipped",
			content: "an example of `:-: ref` syntax",
		},
		{
			name:    "an unclosed block still reports its markers",
			content: ":<: ref\n:@: src=\"x\"\n",
			want:    []Marker{{1, ":<:"}, {2, ":@:"}},
		},
		{
			name:    "a bare marker with no trailing space is reported",
			content: ":=:",
			want:    []Marker{{1, ":=:"}},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := FindDirectiveMarkers(tc.content)
			if !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("FindDirectiveMarkers = %#v, want %#v", got, tc.want)
			}
		})
	}
}
