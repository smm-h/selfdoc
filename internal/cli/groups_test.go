package cli

import (
	"sort"
	"strings"
	"testing"
)

// The command tree, pinned. One binary carries what used to be two CLIs, so
// the groups and commands below are the whole surface a consumer addresses.

func TestTheCommandTreeIsTheDeclaredOne(t *testing.T) {
	registered := make([]string, 0, len(commandEffects))
	for path := range walk(t) {
		registered = append(registered, path)
	}
	sort.Strings(registered)

	expected := []string{
		"assembly.generate-shared", "assembly.init", "assembly.integrate",
		"assembly.preview", "assembly.push", "assembly.rebuild",
		"assembly.redirects", "assembly.retire", "assembly.status",
		"assembly.sync-workflow", "assembly.verify",
		"baseline.accept",
		"build", "check", "deploy", "docs.publish",
		"editor.list-repos", "editor.serve",
		"gen", "gen-data", "init",
		"post.generate", "post.list", "post.new", "post.publish",
		"quality", "serve", "spell-corpus",
	}
	if strings.Join(registered, " ") != strings.Join(expected, " ") {
		t.Errorf("the command tree is\n  %v\nwant\n  %v", registered, expected)
	}
}

func TestTheGroupsCarryTheirHelp(t *testing.T) {
	groups, ok := New(Options{}).DumpSchemaDict()["groups"].(map[string]any)
	if !ok {
		t.Fatal("no groups registered")
	}
	for name, want := range map[string]string{
		"baseline": "Manage the content and description hash baselines that drive staleness (STALE001) and source-drift (DRIFT001) detection during selfdoc check",
		"post":     "Manage blog posts and chronological content for the documentation site",
		"docs":     "Publish this project's documentation to the unified assembly without a release",
		"assembly": "Manage the unified multi-project documentation assembly and deployment",
		"editor":   "Run and inspect the local authoring app for blog posts",
	} {
		group, ok := groups[name].(map[string]any)
		if !ok {
			t.Errorf("group %q is not registered", name)
			continue
		}
		if group["help"] != want {
			t.Errorf("group %q help is %q", name, group["help"])
		}
	}
}

func TestEveryGroupAndCommandAnswersHelp(t *testing.T) {
	dir := t.TempDir()
	for _, argv := range [][]string{
		{"--help"},
		{"baseline", "--help"}, {"baseline", "accept", "--help"},
		{"post", "--help"}, {"post", "new", "--help"},
		{"docs", "--help"}, {"docs", "publish", "--help"},
		{"assembly", "--help"},
		{"assembly", "init", "--help"}, {"assembly", "push", "--help"},
		{"assembly", "status", "--help"}, {"assembly", "rebuild", "--help"},
		{"assembly", "retire", "--help"}, {"assembly", "preview", "--help"},
		{"editor", "--help"}, {"editor", "serve", "--help"},
		{"editor", "list-repos", "--help"},
		{"build", "--help"}, {"check", "--help"},
	} {
		result := run(t, dir, argv...)
		if result.ExitCode != 0 {
			t.Errorf("%v exited %d: %s", argv, result.ExitCode, result.Stderr)
		}
	}
}

func TestServeHelpSurvivesDryRunOnTheSameLine(t *testing.T) {
	// --help always beats a dry-run refusal.
	if result := run(t, t.TempDir(), "editor", "serve", "--dry-run", "--help"); result.ExitCode != 0 {
		t.Errorf("help refused: %d %s", result.ExitCode, result.Stderr)
	}
}
