package catalog

import (
	"errors"
	"reflect"
	"sort"
	"strings"
	"testing"
)

// -- The embedded document loads and validates -------------------------------

// expectedCoreNames is the shipped core catalogue, named rather than counted,
// so adding a directive to directives.toml without adding it here fails.
var expectedCoreNames = []string{
	"ref",
	"table-schema",
	"code-test",
	"code-help",
	"table-config",
	"callout-note",
	"callout-warning",
	"callout-tip",
	"callout-danger",
	"callout-important",
	"list-glossary",
	"prose-desc",
	"list-tree",
	"table-dep",
	"list-modules",
	"table-commands",
	"table-directives",
	"table-config-schema",
	"table-endpoint",
	"list-crawlers",
	"table-lints",
	"var",
	"cv",
}

func TestEmbeddedDocumentValidates(t *testing.T) {
	c, err := Load()
	if err != nil {
		t.Fatalf("the embedded catalogue document is not valid: %v", err)
	}
	if c.Len() != len(expectedCoreNames) {
		t.Fatalf("catalogue carries %d directives, want %d", c.Len(), len(expectedCoreNames))
	}
}

func TestCoreNamesAreTheShippedSet(t *testing.T) {
	got := append([]string(nil), Core().Names()...)
	want := append([]string(nil), expectedCoreNames...)
	sort.Strings(got)
	sort.Strings(want)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("core names = %v, want %v", got, want)
	}
}

func TestCoreKeepsDocumentOrder(t *testing.T) {
	document, diags := ValidateBytes(catalogueDocument, "toml")
	if len(diags) > 0 {
		t.Fatalf("the embedded catalogue document is not valid: %v", diags)
	}
	want := make([]string, 0, len(document.Directives))
	for _, d := range document.Directives {
		want = append(want, d.Name)
	}
	if !reflect.DeepEqual(Core().Names(), want) {
		t.Fatalf("Names() = %v, want the document order %v", Core().Names(), want)
	}
}

// -- Set invariants -----------------------------------------------------------

func TestCoreAndFutureDoNotOverlap(t *testing.T) {
	for _, name := range Core().Names() {
		if IsFutureDirective(name) {
			t.Errorf("%q is both core and future", name)
		}
	}
}

func TestAllBuiltinIsCoreUnionFuture(t *testing.T) {
	want := make(map[string]struct{})
	for _, name := range Core().Names() {
		want[name] = struct{}{}
	}
	for _, name := range FutureDirectiveNames() {
		want[name] = struct{}{}
	}
	if !reflect.DeepEqual(AllBuiltinDirectives(), want) {
		t.Fatalf("AllBuiltinDirectives is not the core-plus-future union")
	}
}

func TestAllBuiltinDirectivesIsAFreshSet(t *testing.T) {
	first := AllBuiltinDirectives()
	delete(first, "ref")
	if _, ok := AllBuiltinDirectives()["ref"]; !ok {
		t.Fatal("mutating the returned set changed the catalogue")
	}
}

// -- IsValidDirective ---------------------------------------------------------

func TestIsValidDirective(t *testing.T) {
	custom := map[string]struct{}{"my-widget": {}, "project-badge": {}}
	tests := []struct {
		name   string
		custom map[string]struct{}
		want   bool
	}{
		{name: "ref", want: true},
		{name: "table-schema", want: true},
		{name: "code-source", want: true},
		{name: "prose-summary", want: true},
		{name: "my-widget", custom: custom, want: true},
		{name: "project-badge", custom: custom, want: true},
		{name: "nonexistent", want: false},
		{name: "nonexistent", custom: map[string]struct{}{}, want: false},
		{name: "my-widget", want: false},
	}
	for _, tc := range tests {
		if got := IsValidDirective(tc.name, tc.custom); got != tc.want {
			t.Errorf("IsValidDirective(%q, %v) = %v, want %v",
				tc.name, tc.custom, got, tc.want)
		}
	}
}

// -- DirectiveStatus ----------------------------------------------------------

func TestDirectiveStatus(t *testing.T) {
	for _, name := range Core().Names() {
		if got := DirectiveStatus(name); got != "core" {
			t.Errorf("DirectiveStatus(%q) = %q, want core", name, got)
		}
	}
	for _, name := range FutureDirectiveNames() {
		if got := DirectiveStatus(name); got != "future" {
			t.Errorf("DirectiveStatus(%q) = %q, want future", name, got)
		}
	}
	for _, name := range []string{"nonexistent", "my-custom"} {
		if got := DirectiveStatus(name); got != "unknown" {
			t.Errorf("DirectiveStatus(%q) = %q, want unknown", name, got)
		}
	}
}

// -- Spec metadata ------------------------------------------------------------

func TestEverySpecIsPopulated(t *testing.T) {
	for _, name := range Core().Names() {
		spec, _ := Core().Spec(name)
		if spec.Description == "" {
			t.Errorf("%s: empty description", name)
		}
		if spec.Category != "code" && spec.Category != "content" {
			t.Errorf("%s: invalid category %q", name, spec.Category)
		}
		if spec.Example == "" {
			t.Errorf("%s: empty example", name)
		}
	}
}

func TestCodeDirectivesRequirePath(t *testing.T) {
	for _, name := range Core().Names() {
		spec, _ := Core().Spec(name)
		if spec.Category != "code" {
			continue
		}
		if !contains(spec.RequiredAttrs, "path") {
			t.Errorf("%s: code directive does not require 'path'", name)
		}
	}
}

func TestSharedCodeAttrsOnEveryCodeDirective(t *testing.T) {
	for _, name := range Core().Names() {
		spec, _ := Core().Spec(name)
		if spec.Category != "code" {
			continue
		}
		for _, attr := range SharedCodeAttrs() {
			if !contains(spec.OptionalAttrs, attr) {
				t.Errorf("%s: code directive does not accept the shared attr %q",
					name, attr)
			}
		}
	}
}

// bodyOnlyContent are the content directives that take body content -- the
// callouts and the glossary -- and therefore accept no attributes at all.
var bodyOnlyContent = []string{
	"callout-note", "callout-warning", "callout-tip",
	"callout-danger", "callout-important", "list-glossary",
}

func TestBodyOnlyContentDirectivesRequireNothing(t *testing.T) {
	for _, name := range bodyOnlyContent {
		spec, ok := Core().Spec(name)
		if !ok {
			t.Fatalf("%s is not in the catalogue", name)
		}
		if len(spec.RequiredAttrs) != 0 {
			t.Errorf("%s: body-only content directive requires %v", name, spec.RequiredAttrs)
		}
	}
}

func TestFilesystemContentDirectivesRequirePath(t *testing.T) {
	for _, name := range []string{"list-tree", "table-dep"} {
		spec, ok := Core().Spec(name)
		if !ok {
			t.Fatalf("%s is not in the catalogue", name)
		}
		if !contains(spec.RequiredAttrs, "path") {
			t.Errorf("%s: filesystem content directive does not require 'path'", name)
		}
	}
}

// expectedAttrs is the hand-verified map of every core directive to its
// required and optional attribute sets, derived by reading each directive's
// resolver:
//
//   - code directives dispatch through the extractor base (reads path,
//     target) and the multi-language resolver (reads lang); exclude is read by
//     the table-config and table-schema handlers.
//   - content directives resolve in the content package (list-tree reads
//     depth, list-modules reads files, table-endpoint reads endpoint and
//     method, var reads key), and table-commands discovers its schema with an
//     optional schema-dir override.
//
// Any drift between a resolver's attribute reads and the catalogue fails here,
// so the catalogue stays truthful.
var expectedAttrs = map[string]struct {
	required []string
	optional []string
}{
	"ref":                 {[]string{"path"}, []string{"target", "lang"}},
	"table-schema":        {[]string{"path"}, []string{"target", "exclude", "lang"}},
	"code-test":           {[]string{"path"}, []string{"target", "lang"}},
	"code-help":           {[]string{"path"}, []string{"lang"}},
	"table-config":        {[]string{"path"}, []string{"exclude", "lang"}},
	"prose-desc":          {[]string{"path"}, []string{"lang"}},
	"callout-note":        {nil, nil},
	"callout-warning":     {nil, nil},
	"callout-tip":         {nil, nil},
	"callout-danger":      {nil, nil},
	"callout-important":   {nil, nil},
	"list-glossary":       {nil, nil},
	"list-tree":           {[]string{"path"}, []string{"depth"}},
	"table-dep":           {[]string{"path"}, nil},
	"list-modules":        {[]string{"path"}, []string{"files"}},
	"table-commands":      {nil, []string{"schema-dir"}},
	"table-directives":    {nil, nil},
	"table-config-schema": {nil, nil},
	"table-endpoint":      {[]string{"path"}, []string{"endpoint", "method"}},
	"list-crawlers":       {nil, nil},
	"table-lints":         {nil, nil},
	"var":                 {[]string{"key"}, nil},
	"cv":                  {[]string{"path"}, nil},
}

func TestExpectedAttrsCoversEveryCoreDirective(t *testing.T) {
	got := append([]string(nil), Core().Names()...)
	want := make([]string, 0, len(expectedAttrs))
	for name := range expectedAttrs {
		want = append(want, name)
	}
	sort.Strings(got)
	sort.Strings(want)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("expectedAttrs covers %v, the catalogue carries %v", want, got)
	}
}

func TestCatalogAttrsMatchExpected(t *testing.T) {
	for name, want := range expectedAttrs {
		spec, ok := Core().Spec(name)
		if !ok {
			t.Fatalf("%s is not in the catalogue", name)
		}
		if !sameSet(spec.RequiredAttrs, want.required) {
			t.Errorf("%s: required_attrs %v, want %v", name, spec.RequiredAttrs, want.required)
		}
		if !sameSet(spec.OptionalAttrs, want.optional) {
			t.Errorf("%s: optional_attrs %v, want %v", name, spec.OptionalAttrs, want.optional)
		}
	}
}

func TestRequiredAndOptionalAttrsAreDisjoint(t *testing.T) {
	for _, name := range Core().Names() {
		spec, _ := Core().Spec(name)
		for _, req := range spec.RequiredAttrs {
			if contains(spec.OptionalAttrs, req) {
				t.Errorf("%s: %q is both required and optional", name, req)
			}
		}
	}
}

// -- Attribute enforcement ----------------------------------------------------

func TestValidateDirectiveAttrsAccepts(t *testing.T) {
	tests := []struct {
		name  string
		attrs map[string]string
	}{
		{"ref", map[string]string{"path": "pkg.mod", "lang": "python"}},
		{"table-schema", map[string]string{"path": "m.py", "target": "User", "exclude": "x"}},
		{"var", map[string]string{"key": "project.name"}},
		{"callout-note", map[string]string{}},
		{"table-commands", map[string]string{"schema-dir": "."}},
		{"table-commands", map[string]string{}},
		// Not a core directive, so it has no spec and no enforcement: a
		// custom directive defines its own attribute contract.
		{"my-widget", map[string]string{"anything": "goes"}},
		// A future directive name has no descriptor either.
		{"code-source", map[string]string{"whatever": "x"}},
	}
	for _, tc := range tests {
		if err := ValidateDirectiveAttrs(tc.name, tc.attrs, "a.md", 1); err != nil {
			t.Errorf("ValidateDirectiveAttrs(%q, %v) = %v, want nil", tc.name, tc.attrs, err)
		}
	}
}

func TestValidateDirectiveAttrsRefusals(t *testing.T) {
	tests := []struct {
		label string
		name  string
		attrs map[string]string
		file  string
		line  int
		want  string
	}{
		{
			label: "unknown attribute names the position and the allowed set",
			name:  "ref",
			attrs: map[string]string{"path": "m", "bogus": "1"},
			file:  "docs/x.md",
			line:  7,
			want: "docs/x.md:7: directive 'ref' has unknown attribute " +
				"'bogus'. Allowed attributes: lang, path, target.",
		},
		{
			label: "missing required attribute",
			name:  "ref",
			attrs: map[string]string{},
			file:  "docs/x.md",
			line:  2,
			want: "docs/x.md:2: directive 'ref' is missing required " +
				"attribute 'path'. Required attributes: path.",
		},
		{
			label: "var requires key",
			name:  "var",
			attrs: map[string]string{},
			file:  "a.md",
			line:  1,
			want: "a.md:1: directive 'var' is missing required " +
				"attribute 'key'. Required attributes: key.",
		},
		{
			label: "a callout accepts no attribute at all",
			name:  "callout-note",
			attrs: map[string]string{"title": "hi"},
			file:  "a.md",
			line:  1,
			want: "a.md:1: directive 'callout-note' has unknown attribute " +
				"'title'. Allowed attributes: (none).",
		},
		{
			label: "table-commands path carries a migration note",
			name:  "table-commands",
			attrs: map[string]string{"path": "."},
			file:  "docs/_README.md",
			line:  9,
			want: "docs/_README.md:9: directive 'table-commands' no longer takes " +
				"'path'; the schema is discovered automatically. Use " +
				`schema-dir="<dir>" only if discovery reports ambiguity.`,
		},
	}
	for _, tc := range tests {
		t.Run(tc.label, func(t *testing.T) {
			err := ValidateDirectiveAttrs(tc.name, tc.attrs, tc.file, tc.line)
			if err == nil {
				t.Fatalf("expected a refusal, got nil")
			}
			var attrErr *DirectiveAttrError
			if !errors.As(err, &attrErr) {
				t.Fatalf("error %T is not a *DirectiveAttrError", err)
			}
			if err.Error() != tc.want {
				t.Fatalf("message = %q, want %q", err.Error(), tc.want)
			}
		})
	}
}

// -- Document validation ------------------------------------------------------

// validDocument is a well-formed minimal catalogue document, the base every
// malformed variant below is derived from.
const validDocument = "format_version = 1\n" +
	"[[directives]]\n" +
	"name = \"ref\"\n" +
	"description = \"Extract module docstring\"\n" +
	"category = \"code\"\n" +
	"required_attrs = [\"path\"]\n" +
	"optional_attrs = [\"target\", \"lang\"]\n" +
	"example = \":::ref path=\\\"m\\\"\"\n"

func diagCodes(t *testing.T, document string) []string {
	t.Helper()
	_, diags := ValidateBytes([]byte(document), "toml")
	codes := make([]string, 0, len(diags))
	for _, d := range diags {
		codes = append(codes, d.Code)
	}
	return codes
}

func TestMinimalValidDocumentHasNoDiagnostics(t *testing.T) {
	if codes := diagCodes(t, validDocument); len(codes) != 0 {
		t.Fatalf("the minimal document produced %v", codes)
	}
}

func TestMalformedDocumentsAreRejected(t *testing.T) {
	tests := []struct {
		label    string
		document string
		want     string
	}{
		{
			label:    "a name with a leading digit",
			document: strings.Replace(validDocument, `name = "ref"`, `name = "1bad"`, 1),
			want:     "STRICTSPEC_VALUE_STRING_REGEX",
		},
		{
			label:    "a name with an illegal character",
			document: strings.Replace(validDocument, `name = "ref"`, `name = "my.directive"`, 1),
			want:     "STRICTSPEC_VALUE_STRING_REGEX",
		},
		{
			label:    "an unknown key",
			document: validDocument + "extra_junk = \"x\"\n",
			want:     "STRICTSPEC_KEY_UNKNOWN",
		},
		{
			label: "a missing required field",
			document: strings.Replace(validDocument,
				"description = \"Extract module docstring\"\n", "", 1),
			want: "STRICTSPEC_TYPE_MISSING_REQUIRED",
		},
		{
			label:    "a category outside the enum",
			document: strings.Replace(validDocument, `category = "code"`, `category = "sideways"`, 1),
			want:     "STRICTSPEC_TYPE_NOT_ENUM_MEMBER",
		},
		{
			label:    "no format_version marker",
			document: strings.Replace(validDocument, "format_version = 1\n", "", 1),
			want:     "STRICTSPEC_GATE_ABSENT",
		},
		{
			label: "a duplicate name",
			document: validDocument + "[[directives]]\n" +
				"name = \"ref\"\n" +
				"description = \"dup\"\n" +
				"category = \"code\"\n" +
				"required_attrs = [\"path\"]\n" +
				"optional_attrs = []\n" +
				"example = \":::ref\"\n",
			want: "STRICTSPEC_INTRA_UNIQUE_BY",
		},
	}
	for _, tc := range tests {
		t.Run(tc.label, func(t *testing.T) {
			codes := diagCodes(t, tc.document)
			if !contains(codes, tc.want) {
				t.Fatalf("diagnostics %v do not include %s", codes, tc.want)
			}
		})
	}
}

func TestBuildCatalogueRefusesAMalformedDocument(t *testing.T) {
	bad := strings.Replace(validDocument, `name = "ref"`, `name = "1bad"`, 1)
	_, err := BuildCatalogue([]byte(bad))
	if err == nil {
		t.Fatal("expected a refusal, got nil")
	}
	var docErr *CatalogDocumentError
	if !errors.As(err, &docErr) {
		t.Fatalf("error %T is not a *CatalogDocumentError", err)
	}
	// The refusal surfaces the offending diagnostic, so it is actionable.
	if !strings.Contains(err.Error(), "STRICTSPEC_VALUE_STRING_REGEX") {
		t.Fatalf("message %q does not name the diagnostic", err.Error())
	}
	if !strings.Contains(err.Error(), "directives.toml is not a valid directive catalogue:") {
		t.Fatalf("message %q does not name the document", err.Error())
	}
}

// TestBuildCatalogueRefusalIsByteIdenticalToThePythonSurface pins the whole
// refusal, because the diagnostic rendering is what a consumer reads and the
// two implementations render it through different runtimes. The expected text
// is what the Python loader printed for the same bytes.
func TestBuildCatalogueRefusalIsByteIdenticalToThePythonSurface(t *testing.T) {
	bad := []byte("format_version = 1\n[[directives]]\nname = \"1bad\"\n" +
		"description = \"d\"\ncategory = \"code\"\nrequired_attrs = []\n" +
		"optional_attrs = []\nexample = \"e\"\n")
	_, err := BuildCatalogue(bad)
	if err == nil {
		t.Fatal("expected a refusal, got nil")
	}
	want := "directives.toml is not a valid directive catalogue:\n" +
		"  $.directives[0].name: String \"1bad\" at $.directives[0].name " +
		"does not match the required pattern \"^[a-zA-Z][\\\\w-]*$\". " +
		"[STRICTSPEC_VALUE_STRING_REGEX]"
	if err.Error() != want {
		t.Fatalf("message =\n%q\nwant\n%q", err.Error(), want)
	}
}

func TestBuildCatalogueBindsAValidDocument(t *testing.T) {
	c, err := BuildCatalogue([]byte(validDocument))
	if err != nil {
		t.Fatalf("BuildCatalogue returned %v", err)
	}
	if !reflect.DeepEqual(c.Names(), []string{"ref"}) {
		t.Fatalf("names = %v, want [ref]", c.Names())
	}
	spec, ok := c.Spec("ref")
	if !ok {
		t.Fatal("the bound catalogue does not carry 'ref'")
	}
	if spec.Category != "code" {
		t.Errorf("category = %q, want code", spec.Category)
	}
	if !reflect.DeepEqual(spec.RequiredAttrs, []string{"path"}) {
		t.Errorf("required_attrs = %v, want [path]", spec.RequiredAttrs)
	}
	if !reflect.DeepEqual(spec.OptionalAttrs, []string{"target", "lang"}) {
		t.Errorf("optional_attrs = %v, want [target lang]", spec.OptionalAttrs)
	}
}

// -- helpers ------------------------------------------------------------------

func contains(haystack []string, needle string) bool {
	for _, v := range haystack {
		if v == needle {
			return true
		}
	}
	return false
}

func sameSet(got, want []string) bool {
	if len(got) != len(want) {
		return false
	}
	g := append([]string(nil), got...)
	w := append([]string(nil), want...)
	sort.Strings(g)
	sort.Strings(w)
	return reflect.DeepEqual(g, w)
}
