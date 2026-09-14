package layout

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/smm-h/selfdoc/internal/effects"
	"github.com/smm-h/stricttest/go/hygiene"
)

// validated is a repository whose layout is exactly as declared: every claimed
// directory present, the ignore file derived, nothing else inside.
func validated(t *testing.T) string {
	t.Helper()
	dir := owned(t)
	for _, declared := range Declared() {
		if !declared.CreatedByTool {
			// A directory selfdoc never creates has no row until its
			// content arrives, so a repository without that content is
			// laid out correctly without it.
			continue
		}
		if err := EnsureDir(effects.Unbound(), dir, Root+"/"+declared.Name); err != nil {
			t.Fatalf("EnsureDir %s: %v", declared.Name, err)
		}
	}
	problems, err := Validate(dir)
	if err != nil {
		t.Fatalf("Validate: %v", err)
	}
	if len(problems) != 0 {
		t.Fatalf("a freshly laid out repository has problems: %v", problems)
	}
	return dir
}

// problemsOf validates a repository and returns the problems of one check.
func problemsOf(t *testing.T, dir, check string) []Problem {
	t.Helper()
	problems, err := Validate(dir)
	if err != nil {
		t.Fatalf("Validate: %v", err)
	}
	var matching []Problem
	for _, problem := range problems {
		if problem.Check == check {
			matching = append(matching, problem)
		}
	}
	return matching
}

func TestValidateRefusesARepositoryWithNoLayoutAtAll(t *testing.T) {
	hygiene.Isolate(t)
	_, err := Validate(t.TempDir())
	if err == nil {
		t.Fatal("a repository with no tool-state directory validated")
	}
	for _, want := range []string{Root, OwnersHeader, DocsName + "," + Owner} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("the refusal does not carry %q: %v", want, err)
		}
	}
}

func TestValidateReportsADirectoryNoRowNames(t *testing.T) {
	hygiene.Isolate(t)
	dir := validated(t)
	if err := os.MkdirAll(filepath.Join(dir, Root, "unclaimed"), 0o755); err != nil {
		t.Fatal(err)
	}
	problems := problemsOf(t, dir, CheckOwnership)
	if len(problems) != 1 {
		t.Fatalf("ownership problems = %v, want the unclaimed directory's one", problems)
	}
	if !strings.Contains(problems[0].Message, "unclaimed,<owner>") {
		t.Errorf("the problem does not name the row to add: %s", problems[0].Message)
	}
}

func TestValidateReportsARowNothingAnswersTo(t *testing.T) {
	hygiene.Isolate(t)
	dir := validated(t)
	write(t, filepath.Join(dir, Root, OwnersFileName),
		strings.Join(append(RequiredRows(), VocabularyName+","+Owner), "\n")+"\n")
	problems := problemsOf(t, dir, CheckOwnership)
	if len(problems) != 1 {
		t.Fatalf("ownership problems = %v, want the missing directory's one", problems)
	}
	if !strings.Contains(problems[0].Message, VocabularyName) {
		t.Errorf("the problem does not name the missing directory: %s", problems[0].Message)
	}
}

func TestValidateReportsAGeneratedPageInAHandwrittenDirectory(t *testing.T) {
	hygiene.Isolate(t)
	dir := validated(t)
	write(t, filepath.Join(Path(dir, DocsRel), "api.md"),
		"+++\ntitle = \"API\"\n+++\n"+GeneratedMarkerPrefix+", do not edit -->\n\n# API\n")
	problems := problemsOf(t, dir, CheckSide)
	if len(problems) != 1 {
		t.Fatalf("side problems = %v, want the generated page's one", problems)
	}
	for _, want := range []string{"docs/api.md", GeneratedPagesRel} {
		if !strings.Contains(problems[0].Message, want) {
			t.Errorf("the problem does not carry %q: %s", want, problems[0].Message)
		}
	}
}

func TestValidateReportsAHandwrittenPageInAGeneratedDirectory(t *testing.T) {
	hygiene.Isolate(t)
	dir := validated(t)
	write(t, filepath.Join(Path(dir, GeneratedPagesRel), "notes.md"),
		"+++\ntitle = \"Notes\"\n+++\n\n# Notes\n")
	problems := problemsOf(t, dir, CheckSide)
	if len(problems) != 1 {
		t.Fatalf("side problems = %v, want the handwritten page's one", problems)
	}
	for _, want := range []string{"notes.md", DocsRel} {
		if !strings.Contains(problems[0].Message, want) {
			t.Errorf("the problem does not carry %q: %s", want, problems[0].Message)
		}
	}
}

func TestValidateReportsAHiddenEntry(t *testing.T) {
	hygiene.Isolate(t)
	dir := validated(t)
	write(t, filepath.Join(Path(dir, DocsRel), ".notes.md"), "# Hidden\n")
	if err := os.MkdirAll(filepath.Join(dir, Root, ".cache"), 0o755); err != nil {
		t.Fatal(err)
	}
	problems := problemsOf(t, dir, CheckHidden)
	if len(problems) != 2 {
		t.Fatalf("hidden problems = %v, want both dotted entries", problems)
	}
	joined := problems[0].Message + problems[1].Message
	for _, want := range []string{".cache", ".notes.md"} {
		if !strings.Contains(joined, want) {
			t.Errorf("the problems do not name %q: %s", want, joined)
		}
	}
	// The derived ignore file is the one hidden entry that is allowed.
	if strings.Count(joined, IgnoreFileName+" starts with a dot") != 0 {
		t.Errorf("the derived ignore file was reported: %s", joined)
	}
}

func TestValidateReportsAStaleIgnoreFile(t *testing.T) {
	hygiene.Isolate(t)
	dir := validated(t)
	write(t, IgnorePath(dir), "# BEGIN othertool\nother/\n# END othertool\n")
	problems := problemsOf(t, dir, CheckIgnore)
	if len(problems) != 1 {
		t.Fatalf("ignore problems = %v, want the stale file's one", problems)
	}
	if !strings.Contains(problems[0].Message, DocsCacheName+"/") {
		t.Errorf("the problem does not carry the content it should hold: %s", problems[0].Message)
	}

	// The remedy: writing the file through the layout clears the problem,
	// and the other tool's lines are still there.
	if err := WriteIgnore(effects.Unbound(), dir); err != nil {
		t.Fatalf("WriteIgnore: %v", err)
	}
	if remaining := problemsOf(t, dir, CheckIgnore); len(remaining) != 0 {
		t.Errorf("the remedy did not clear the problem: %v", remaining)
	}
	if ignore := read(t, IgnorePath(dir)); !strings.Contains(ignore, "other/") {
		t.Errorf("the other tool's lines were dropped:\n%s", ignore)
	}
}
