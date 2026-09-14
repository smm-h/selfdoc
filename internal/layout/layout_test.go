package layout

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/smm-h/selfdoc/internal/effects"
	"github.com/smm-h/stricttest/go/hygiene"
)

// owned writes the ownership declaration a repository grants selfdoc, and
// returns the repository root.
func owned(t *testing.T, rows ...string) string {
	t.Helper()
	dir := t.TempDir()
	if len(rows) == 0 {
		rows = RequiredRows()
	}
	write(t, filepath.Join(dir, Root, OwnersFileName), strings.Join(rows, "\n")+"\n")
	return dir
}

func write(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir %s: %v", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

func read(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(data)
}

func TestTheDeclarationCoversEveryDirectorySelfdocWrites(t *testing.T) {
	hygiene.Isolate(t)
	claimed := map[string]bool{}
	for _, dir := range Declared() {
		claimed[dir.Name] = true
	}
	for _, rel := range []string{
		DocsRel, GeneratedPagesRel, ManifestRel, PostManifestRel, RevisionsRel,
		HashesRel, DataRel, OutputRel, VersionsRel, PostsRel, VocabularyRel,
	} {
		name, ok := FunctionOf(rel)
		if !ok {
			t.Errorf("%s is not a path under %s", rel, Root)
			continue
		}
		if !claimed[name] {
			t.Errorf("%s sits in %s, which the declaration does not claim", rel, name)
		}
	}
}

func TestTheOwnersFileNeedsItsHeader(t *testing.T) {
	hygiene.Isolate(t)
	dir := t.TempDir()
	write(t, filepath.Join(dir, Root, OwnersFileName), "docs,selfdoc\n")
	_, err := ReadOwners(dir)
	if err == nil {
		t.Fatal("a headerless owners file was accepted")
	}
	if !strings.Contains(err.Error(), OwnersHeader) {
		t.Errorf("the refusal does not name the header: %v", err)
	}
}

func TestTheOwnersFileRefusesADirectoryDeclaredTwice(t *testing.T) {
	hygiene.Isolate(t)
	dir := owned(t, OwnersHeader, "docs,selfdoc", "docs,other")
	_, err := ReadOwners(dir)
	if err == nil || !strings.Contains(err.Error(), "twice") {
		t.Fatalf("err = %v, want a refusal naming the repeated directory", err)
	}
}

func TestCreatingADirectoryNeedsItsRow(t *testing.T) {
	hygiene.Isolate(t)
	dir := owned(t, OwnersHeader, "posts,selfdoc")

	err := EnsureDir(effects.Unbound(), dir, DocsStateRel)
	if err == nil {
		t.Fatal("a directory with no row was created")
	}
	if !strings.Contains(err.Error(), DocsStateName+","+Owner) {
		t.Errorf("the refusal does not name the row to add: %v", err)
	}
	if _, statErr := os.Stat(Path(dir, DocsStateRel)); !os.IsNotExist(statErr) {
		t.Errorf("the directory was created anyway (stat err = %v)", statErr)
	}
}

func TestADirectoryAnotherToolOwnsIsRefused(t *testing.T) {
	hygiene.Isolate(t)
	dir := owned(t, OwnersHeader, "docs-state,someothertool")
	err := EnsureDir(effects.Unbound(), dir, DocsStateRel)
	if err == nil || !strings.Contains(err.Error(), "someothertool") {
		t.Fatalf("err = %v, want a refusal naming the declared owner", err)
	}
}

func TestCreatingADirectoryWritesTheDerivedIgnoreFile(t *testing.T) {
	hygiene.Isolate(t)
	dir := owned(t)
	if err := EnsureDir(effects.Unbound(), dir, OutputRel); err != nil {
		t.Fatalf("EnsureDir: %v", err)
	}
	if info, err := os.Stat(Path(dir, OutputRel)); err != nil || !info.IsDir() {
		t.Fatalf("the output directory was not created: %v", err)
	}
	ignore := read(t, IgnorePath(dir))
	if !strings.Contains(ignore, DocsCacheName+"/") {
		t.Errorf("the derived ignore file does not ignore the uncommitted directory:\n%s", ignore)
	}
	if strings.Contains(ignore, DocsStateName+"/") {
		t.Errorf("the derived ignore file ignores a committed directory:\n%s", ignore)
	}
}

func TestTheDerivedIgnoreFileLeavesOtherToolsLinesAlone(t *testing.T) {
	hygiene.Isolate(t)
	existing := "# BEGIN othertool\nother-cache/\n# END othertool\n"
	rendered := RenderIgnore(existing)
	for _, want := range []string{"# BEGIN othertool", "other-cache/", "# END othertool", DocsCacheName + "/"} {
		if !strings.Contains(rendered, want) {
			t.Errorf("the rendered ignore file lost %q:\n%s", want, rendered)
		}
	}
	// Rendering what was rendered changes nothing: the block is replaced in
	// place rather than appended again.
	if again := RenderIgnore(rendered); again != rendered {
		t.Errorf("a second render differs:\n%s\n---\n%s", rendered, again)
	}
}

func TestTheOldLayoutIsRefused(t *testing.T) {
	hygiene.Isolate(t)
	for _, testCase := range []struct {
		name                          string
		deprecated                    string
		docs, output, posts, wantName string
	}{
		{
			name:       "the tool-state directory selfdoc used before",
			deprecated: DeprecatedRoot,
			wantName:   DeprecatedRoot + "/",
		},
		{
			name:     "a docs path outside the layout",
			docs:     "docs/",
			wantName: `"docs"`,
		},
		{
			name:     "an output path outside the layout",
			output:   "docs/_build/",
			wantName: `"output"`,
		},
		{
			name:     "a posts path outside the layout",
			posts:    "posts/",
			wantName: `"posts.dir"`,
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			dir := t.TempDir()
			if testCase.deprecated != "" {
				if err := os.MkdirAll(filepath.Join(dir, testCase.deprecated), 0o755); err != nil {
					t.Fatal(err)
				}
			}
			err := RefuseOldLayout(dir, testCase.docs, testCase.output, testCase.posts)
			if err == nil {
				t.Fatal("the old layout was accepted")
			}
			if !strings.Contains(err.Error(), testCase.wantName) {
				t.Errorf("the refusal does not name what it found: %v", err)
			}
			if !strings.Contains(err.Error(), MoveScript) {
				t.Errorf("the refusal does not name the move script: %v", err)
			}
		})
	}
}

func TestTheNewLayoutIsAccepted(t *testing.T) {
	hygiene.Isolate(t)
	dir := owned(t)
	if err := RefuseOldLayout(dir, DocsDefault, OutputDefault, PostsDefault); err != nil {
		t.Errorf("a moved repository was refused: %v", err)
	}
	// An undeclared key is the default, which is inside the layout.
	if err := RefuseOldLayout(dir, "", "", ""); err != nil {
		t.Errorf("a repository declaring nothing was refused: %v", err)
	}
}
