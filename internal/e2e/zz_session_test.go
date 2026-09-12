//go:build e2e

package e2e

import (
	"sort"
	"strings"
	"testing"
)

// The two session assertions: each reads what the sweep recorded while it ran,
// so both belong after every other test in the package. Go runs a package's
// tests in the order its files are compiled, which is sorted by file name --
// hence the name of this file.

// TestEveryRecordedAccessibilityFindingIsStillReal is the other half of
// KnownSerious: a recorded finding that has been fixed must leave the record.
//
// Without this, a fixed rule would sit in the list forever and quietly
// re-admit the same defect later.
func TestEveryRecordedAccessibilityFindingIsStillReal(t *testing.T) {
	seen := axeRulesSeen()
	if len(seen) == 0 {
		t.Skip("the accessibility sweep did not run in this session")
	}
	sawRule := map[string]bool{}
	for _, rule := range seen {
		sawRule[rule] = true
	}
	var stale []string
	for rule := range KnownSerious {
		if !sawRule[rule] {
			stale = append(stale, rule)
		}
	}
	sort.Strings(stale)
	if len(stale) > 0 {
		t.Errorf("KnownSerious records %v, which the sweep no longer sees. They are "+
			"fixed -- delete the entries, so the rule blocks again.", stale)
	}
}

// TestTheThreeThemesReallyRenderDifferently asserts three themes produce three
// renderings, or the sweep is decoration.
//
// Reads what the per-theme guards recorded; skips when the session was
// filtered down to fewer themes than the sweep declares.
func TestTheThreeThemesReallyRenderDifferently(t *testing.T) {
	signaturesMu.Lock()
	recorded := map[string]string{}
	for theme, signature := range themeSignatures {
		recorded[theme] = signature
	}
	signaturesMu.Unlock()

	if len(recorded) < len(Themes) {
		names := make([]string, 0, len(recorded))
		for theme := range recorded {
			names = append(names, theme)
		}
		t.Skipf("only %v of %v ran in this session", sortedStrings(names), Themes)
	}
	distinct := map[string]bool{}
	for _, signature := range recorded {
		distinct[signature] = true
	}
	if len(distinct) != len(Themes) {
		rendered := make([]string, 0, len(recorded))
		for theme, signature := range recorded {
			rendered = append(rendered, theme+": "+signature)
		}
		t.Errorf("themes that render identically: %s",
			strings.Join(sortedStrings(rendered), "; "))
	}
}
