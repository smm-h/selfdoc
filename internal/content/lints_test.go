package content

import (
	"strings"
	"testing"

	"github.com/smm-h/selfdoc/internal/lints"
)

// TestResolveListLintsRendersTheWholeRegistry pins the directive that keeps
// the check guide's lint table from being a second copy of the registry: every
// registered code renders, in the registry's own documentation order, with the
// severity and description the registry declares.
func TestResolveListLintsRendersTheWholeRegistry(t *testing.T) {
	rendered, err := ResolveListLints()
	if err != nil {
		t.Fatalf("ResolveListLints: %v", err)
	}
	registry := lints.Registered()

	lines := strings.Split(strings.TrimSpace(rendered), "\n")
	if len(lines) != registry.Len()+2 {
		t.Fatalf("rendered %d lines, want %d rows plus a header and its rule",
			len(lines), registry.Len())
	}
	for _, want := range []string{"Code", "Severity", "What it checks"} {
		if !strings.Contains(lines[0], want) {
			t.Errorf("the header does not name %q: %s", want, lines[0])
		}
	}

	for index, code := range registry.Codes() {
		row := lines[index+2]
		spec, _ := registry.Spec(code)
		for _, want := range []string{code, spec.Severity, spec.Description} {
			if !strings.Contains(row, want) {
				t.Errorf("the row for %s does not carry %q: %s", code, want, row)
			}
		}
	}
}

// TestResolveListLintsIsDispatched pins that the directive is reachable by
// name, not only as a function.
func TestResolveListLintsIsDispatched(t *testing.T) {
	rendered, handled, err := ResolveContent("list-lints", nil, nil, "", nil)
	if err != nil {
		t.Fatalf("ResolveContent: %v", err)
	}
	if !handled {
		t.Fatal("list-lints is not dispatched by ResolveContent")
	}
	if !strings.Contains(rendered, "SEO001") {
		t.Errorf("the dispatched directive rendered no registry row:\n%s", rendered)
	}
}
