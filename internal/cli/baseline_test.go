package cli

import (
	"path/filepath"
	"strings"
	"testing"
)

// `selfdoc baseline accept` -- the STALE001/DRIFT001 escape hatch.
//
// STALE001 fires when a page's resolved content changed versus its stored
// baseline but its frontmatter description did not. The baseline is
// deliberately frozen while a page is in an error state, so re-running
// gen/check can never clear the error on its own -- the only other escape is
// editing the description. `baseline accept <page>` is the deliberate,
// auditable human action that clears such a dead end when the existing
// description was reviewed and is still accurate.

// baselineProject creates a project with one documentation page.
func baselineProject(t *testing.T) string {
	t.Helper()
	return postProject(t, map[string]any{
		"docs":   "docs/",
		"output": "docs/_build/",
	})
}

// writePage writes a documentation page with the given description and body.
func writePage(t *testing.T, dir, description, body, name string) {
	t.Helper()
	writeText(t, filepath.Join(dir, "docs", name),
		"---\ndescription: "+description+"\n---\n# Page\n\n"+body+"\n")
}

// staleIdentifiers runs the check and returns every page the run reports as
// stale, named exactly as the report names it.
func staleIdentifiers(t *testing.T, dir string) []string {
	t.Helper()
	result := run(t, dir, "check", "--json", "--no-auto-commit")
	payload := payloadOf(t, result)
	var pages []string
	for _, raw := range payload["lints"].([]any) {
		lint := raw.(map[string]any)
		if lint["code"] == "STALE001" {
			pages = append(pages, lint["file"].(string))
		}
	}
	return pages
}

func TestBaselineAcceptClearsTheDeadEnd(t *testing.T) {
	isolate(t)
	dir := baselineProject(t)

	// First check: establish the baseline -- a new page is not stale.
	writePage(t, dir, "Original description", "Original content here.", "page.md")
	if stale := staleIdentifiers(t, dir); len(stale) != 0 {
		t.Fatalf("a fresh page is reported stale: %v", stale)
	}

	// Change the content, keep the description: STALE001, and it persists
	// across runs because the baseline stays frozen.
	writePage(t, dir, "Original description", "Completely rewritten content.", "page.md")
	stale := staleIdentifiers(t, dir)
	if len(stale) != 1 {
		t.Fatalf("expected one stale page, got %v", stale)
	}
	if again := staleIdentifiers(t, dir); len(again) != 1 {
		t.Fatalf("STALE001 did not persist across runs: %v", again)
	}

	result := run(t, dir, "baseline", "accept", stale[0], "--no-auto-commit")
	if result.ExitCode != 0 {
		t.Fatalf("baseline accept failed: %s\n%s", result.Stdout, result.Stderr)
	}
	if !strings.Contains(result.Stdout, "Accepted new baseline for 1 page(s):") {
		t.Errorf("the summary is not the declared one:\n%s", result.Stdout)
	}
	if !strings.Contains(result.Stdout, stale[0]) {
		t.Errorf("the report does not name the page:\n%s", result.Stdout)
	}
	if !strings.Contains(result.Stdout, "(cleared STALE001)") {
		t.Errorf("the report does not name what it cleared:\n%s", result.Stdout)
	}

	if after := staleIdentifiers(t, dir); len(after) != 0 {
		t.Errorf("STALE001 survived the acceptance: %v", after)
	}
}

func TestBaselineAcceptClearsSeveralPagesAtOnce(t *testing.T) {
	isolate(t)
	dir := baselineProject(t)
	writePage(t, dir, "Desc A original", "Body A original.", "a.md")
	writePage(t, dir, "Desc B original", "Body B original.", "b.md")
	staleIdentifiers(t, dir)

	writePage(t, dir, "Desc A original", "Body A rewritten.", "a.md")
	writePage(t, dir, "Desc B original", "Body B rewritten.", "b.md")
	stale := staleIdentifiers(t, dir)
	if len(stale) != 2 {
		t.Fatalf("expected two stale pages, got %v", stale)
	}

	result := run(t, dir, append([]string{"baseline", "accept"},
		append(stale, "--no-auto-commit")...)...)
	if result.ExitCode != 0 {
		t.Fatalf("baseline accept failed: %s\n%s", result.Stdout, result.Stderr)
	}
	if !strings.Contains(result.Stdout, "Accepted new baseline for 2 page(s):") {
		t.Errorf("the summary is not the declared one:\n%s", result.Stdout)
	}
	if after := staleIdentifiers(t, dir); len(after) != 0 {
		t.Errorf("STALE001 survived the acceptance: %v", after)
	}
}

func TestBaselineAcceptRefusesAnUnknownPage(t *testing.T) {
	isolate(t)
	dir := baselineProject(t)
	writePage(t, dir, "Original description", "Original content here.", "page.md")
	staleIdentifiers(t, dir)

	result := run(t, dir, "baseline", "accept", "nope.md", "--no-auto-commit")
	if result.ExitCode != 1 {
		t.Fatalf("exit code is %d, want 1\n%s", result.ExitCode, result.Stdout)
	}
	if !strings.Contains(result.Stderr, "Error:") {
		t.Errorf("no refusal printed: %s", result.Stderr)
	}
}

func TestBaselineAcceptRefusesAPageThatIsNotStale(t *testing.T) {
	// Accepting a page that is not stale is a hard error, not a no-op.
	isolate(t)
	dir := baselineProject(t)
	writePage(t, dir, "Original description", "Original content here.", "page.md")
	staleIdentifiers(t, dir)

	result := run(t, dir, "baseline", "accept", "en/page.md", "--no-auto-commit")
	if result.ExitCode != 1 {
		t.Fatalf("exit code is %d, want 1\n%s", result.ExitCode, result.Stdout)
	}
}

func TestBaselineAcceptRefusesWithoutAConfig(t *testing.T) {
	isolate(t)
	result := run(t, t.TempDir(), "baseline", "accept", "page.md", "--no-auto-commit")
	if result.ExitCode != 1 {
		t.Fatalf("exit code is %d, want 1", result.ExitCode)
	}
	if !strings.Contains(result.Stderr, "No selfdoc.json") {
		t.Errorf("the refusal is not the missing config's: %s", result.Stderr)
	}
}

func TestBaselineAcceptNamesPagesVariadically(t *testing.T) {
	// Pages are named explicitly with no glob and no --all shortcut, so the
	// argument is variadic and required.
	entry := walk(t)["baseline.accept"]
	args, ok := entry["args"].([]any)
	if !ok || len(args) != 1 {
		t.Fatalf("expected one positional argument, got %v", entry["args"])
	}
	arg := args[0].(map[string]any)
	if arg["name"] != "page" {
		t.Errorf("the argument is named %v", arg["name"])
	}
	if arg["variadic"] != true {
		t.Errorf("the argument is not variadic: %v", arg)
	}
	if arg["presence"] != "required" {
		t.Errorf("the argument's presence is %v", arg["presence"])
	}
}
