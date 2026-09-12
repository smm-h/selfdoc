package verify

import (
	"fmt"
	"sort"
	"strings"
)

// Checks is every assertion, in the order a run reports them. A check that
// finds nothing still reports itself as run, so a report can tell "asserted
// and clean" from "never asked".
var Checks = []string{
	"roster-agreement",
	"home-project",
	"manifest-identity",
	"manifest-pages-emitted",
	"manifest-posts-emitted",
	"shared-artifacts",
	"internal-references",
	"sitemap-entries",
	"feed-links",
	"page-metadata",
	"site-chrome",
	"unresolved-directives",
	"routing-artifacts",
	"cross-project-links",
	"outbound-links",
}

// checkOrder is the position of every name in Checks, so the final sort is one
// lookup per failure rather than a scan of the list.
var checkOrder = func() map[string]int {
	order := make(map[string]int, len(Checks))
	for index, name := range Checks {
		order[name] = index
	}
	return order
}()

// Failure is one asserted property, one offender.
type Failure struct {
	// Check is the assertion that was violated, one of Checks.
	Check string
	// Offender is what violated it, named the way a reader finds it.
	Offender string
	// Message is why it is a violation.
	Message string
}

// String renders the failure as one line, the way the report's own rendering
// and every diagnostic that quotes a single failure spell it.
func (f Failure) String() string {
	return fmt.Sprintf("[%s] %s: %s", f.Check, f.Offender, f.Message)
}

// Skip is one check that could not run, and why. It is never silent -- the
// CLI prints them and the deploy logs them.
type Skip struct {
	// Check is the assertion that did not run, one of Checks.
	Check string
	// Reason says what was missing, in the words the report prints.
	Reason string
}

// VerifyReport is what a verification found.
type VerifyReport struct {
	// Failures is every violated property, in check order.
	Failures []Failure
	// Ran is the checks that were asserted.
	Ran []string
	// Skipped is each check that could not run, with its reason.
	Skipped []Skip
	// OutboundCache is the outbound store as this run leaves it. The caller
	// persists it or does not; verification does not write.
	OutboundCache map[string]any
	// Requests is how many outbound fetches this run actually made.
	Requests int
}

// OK reports whether the tree passed every assertion.
func (r *VerifyReport) OK() bool { return len(r.Failures) == 0 }

// FailuresOf returns the failures reported under one check, in report order.
func (r *VerifyReport) FailuresOf(check string) []Failure {
	var found []Failure
	for _, failure := range r.Failures {
		if failure.Check == check {
			found = append(found, failure)
		}
	}
	return found
}

// ErrorText renders the whole report as one message, for a raise or a stderr
// dump.
func (r *VerifyReport) ErrorText() string {
	distinct := map[string]bool{}
	for _, failure := range r.Failures {
		distinct[failure.Check] = true
	}
	lines := []string{fmt.Sprintf(
		"the assembled tree failed verification: %d problem(s) across %d check(s).",
		len(r.Failures), len(distinct),
	)}
	for _, check := range Checks {
		found := r.FailuresOf(check)
		if len(found) == 0 {
			continue
		}
		lines = append(lines, fmt.Sprintf("  %s:", check))
		for _, failure := range found {
			lines = append(lines, fmt.Sprintf(
				"    %s: %s", failure.Offender, failure.Message,
			))
		}
	}
	return strings.Join(lines, "\n")
}

// sortFailures orders the failures by check and then by offender, the way the
// report presents them. The sort is stable, so two failures naming the same
// offender under the same check stay in the order the check emitted them.
func sortFailures(failures []Failure) {
	sort.SliceStable(failures, func(i, j int) bool {
		left, right := failures[i], failures[j]
		if checkOrder[left.Check] != checkOrder[right.Check] {
			return checkOrder[left.Check] < checkOrder[right.Check]
		}
		return left.Offender < right.Offender
	})
}
