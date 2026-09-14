package layout

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Problem is one thing wrong with a repository's layout: what is wrong, and
// what to do about it.
type Problem struct {
	// Check names the rule that failed: "ownership", "side", "hidden" or
	// "ignore-file".
	Check string
	// Message states the defect and names the remedy.
	Message string
}

// Error renders a problem the way the command prints it.
func (p Problem) Error() string { return "[" + p.Check + "] " + p.Message }

// The names of the rules [Validate] holds a repository to.
const (
	CheckOwnership = "ownership"
	CheckSide      = "side"
	CheckHidden    = "hidden"
	CheckIgnore    = "ignore-file"
)

// Validate checks one repository's layout and returns every problem it finds,
// in check order.
//
// The rules: every directory under [Root] is named in the owners file and
// everything the owners file names exists; every directory selfdoc owns holds
// only what its side allows; nothing under [Root] starts with a dot except the
// derived ignore file; and that file's selfdoc block is what the declaration
// says it should be.
//
// An unreadable owners file is returned as an error rather than a problem: the
// rest of the rules are unanswerable without it.
func Validate(baseDir string) ([]Problem, error) {
	rootPath := Path(baseDir, Root)
	info, err := os.Stat(rootPath)
	if err != nil || !info.IsDir() {
		return nil, fmt.Errorf(
			"%s is missing. selfdoc never creates it: make the directory and write %s yourself, with these lines:\n%s",
			Root, filepath.Join(Root, OwnersFileName), strings.Join(RequiredRows(), "\n"))
	}
	owners, err := ReadOwners(baseDir)
	if err != nil {
		return nil, err
	}

	var problems []Problem
	problems = append(problems, bijectionProblems(baseDir, owners)...)
	problems = append(problems, sideProblems(baseDir, owners)...)
	problems = append(problems, hiddenProblems(baseDir, owners)...)
	problems = append(problems, ignoreProblems(baseDir)...)
	return problems, nil
}

// bijectionProblems reports the directories the owners file does not name and
// the names it declares that nothing on disk answers to.
func bijectionProblems(baseDir string, owners *Owners) []Problem {
	var problems []Problem
	entries, err := os.ReadDir(Path(baseDir, Root))
	if err != nil {
		return []Problem{{Check: CheckOwnership, Message: err.Error()}}
	}
	for _, entry := range entries {
		name := entry.Name()
		if name == OwnersFileName || name == IgnoreFileName {
			continue
		}
		if !entry.IsDir() {
			problems = append(problems, Problem{
				Check: CheckOwnership,
				Message: fmt.Sprintf(
					"%s is a file, and %s holds directories: one function per directory, one owner per function. Move it into the directory of the function it belongs to.",
					filepath.Join(Root, name), Root),
			})
			continue
		}
		if _, declared := owners.Owner[name]; !declared {
			suggested := Owner
			if _, claimed := Lookup(name); !claimed {
				suggested = "<owner>"
			}
			problems = append(problems, Problem{
				Check: CheckOwnership,
				Message: fmt.Sprintf(
					"%s exists but no row in %s names its owner. Add this row:\n%s",
					filepath.Join(Root, name), owners.Path, name+","+suggested),
			})
		}
	}
	for _, name := range owners.Order {
		info, err := os.Stat(Path(baseDir, Root+"/"+name))
		if err != nil || !info.IsDir() {
			problems = append(problems, Problem{
				Check: CheckOwnership,
				Message: fmt.Sprintf(
					"%s names %q, which does not exist. Create the directory, or drop its row from %s.",
					owners.Path, filepath.Join(Root, name), owners.Path),
			})
		}
	}
	return problems
}

// sideProblems reports the files sitting on the wrong side of the authorship
// line in the directories selfdoc owns.
//
// A Markdown file carrying selfdoc's generated-page marker belongs in the
// generated pages directory; one without it belongs in the handwritten docs
// directory. The uncommitted cache is not checked: it holds extracted
// checkouts and built output, which carry whatever the source tree carries.
func sideProblems(baseDir string, owners *Owners) []Problem {
	var problems []Problem
	for _, dir := range Declared() {
		if owners.Owner[dir.Name] != Owner || dir.Commitment == Uncommitted {
			continue
		}
		root := Path(baseDir, Root+"/"+dir.Name)
		if info, err := os.Stat(root); err != nil || !info.IsDir() {
			continue
		}
		_ = filepath.WalkDir(root, func(full string, entry os.DirEntry, err error) error {
			if err != nil || entry.IsDir() || !strings.HasSuffix(entry.Name(), ".md") {
				return nil
			}
			content, readErr := os.ReadFile(full)
			if readErr != nil {
				return nil
			}
			marked := strings.Contains(string(content), GeneratedMarkerPrefix)
			shown := showPath(baseDir, full)
			switch {
			case dir.Side == Handwritten && marked:
				problems = append(problems, Problem{
					Check: CheckSide,
					Message: fmt.Sprintf(
						"%s carries selfdoc's generated-page marker but sits in %s, which is handwritten. Move it under %s, or delete the marker if a person wrote the page.",
						shown, filepath.Join(Root, dir.Name), GeneratedPagesRel),
				})
			case dir.Side == Generated && !marked:
				problems = append(problems, Problem{
					Check: CheckSide,
					Message: fmt.Sprintf(
						"%s carries no generated-page marker but sits in %s, which is generated. Move it under %s, where handwritten pages live.",
						shown, filepath.Join(Root, dir.Name), DocsRel),
				})
			}
			return nil
		})
	}
	sort.Slice(problems, func(i, j int) bool { return problems[i].Message < problems[j].Message })
	return problems
}

// hiddenProblems reports the entries under [Root] whose names start with a dot.
//
// [Root] is hidden already, so nothing inside it needs to be. The derived
// ignore file is the one exception, because git will not read it under another
// name. Only the committed directories are walked through: an uncommitted one
// holds extracted checkouts, whose dotted entries are the source tree's.
func hiddenProblems(baseDir string, owners *Owners) []Problem {
	var problems []Problem
	entries, err := os.ReadDir(Path(baseDir, Root))
	if err != nil {
		return nil
	}
	for _, entry := range entries {
		name := entry.Name()
		if strings.HasPrefix(name, ".") && name != IgnoreFileName {
			problems = append(problems, Problem{
				Check: CheckHidden,
				Message: fmt.Sprintf(
					"%s starts with a dot. %s is hidden already, and %s is the one hidden entry allowed inside it. Rename it.",
					filepath.Join(Root, name), Root, IgnoreFileName),
			})
			continue
		}
		if !entry.IsDir() {
			continue
		}
		declared, claimed := Lookup(name)
		if !claimed || owners.Owner[name] != Owner || declared.Commitment == Uncommitted {
			continue
		}
		_ = filepath.WalkDir(Path(baseDir, Root+"/"+name), func(full string, walked os.DirEntry, err error) error {
			if err != nil || !strings.HasPrefix(walked.Name(), ".") {
				return nil
			}
			problems = append(problems, Problem{
				Check: CheckHidden,
				Message: fmt.Sprintf(
					"%s starts with a dot. %s is hidden already, and %s is the one hidden entry allowed inside it. Rename it.",
					showPath(baseDir, full), Root, IgnoreFileName),
			})
			if walked.IsDir() {
				return filepath.SkipDir
			}
			return nil
		})
	}
	return problems
}

// ignoreProblems reports a derived ignore file that does not carry selfdoc's
// block as the declaration renders it, with the content it should hold.
func ignoreProblems(baseDir string) []Problem {
	current, wanted := IgnoreIsCurrent(baseDir)
	if current {
		return nil
	}
	return []Problem{{
		Check: CheckIgnore,
		Message: fmt.Sprintf(
			"%s is not what selfdoc's commitment declaration renders. Run 'selfdoc build', which rewrites it. It should hold:\n%s",
			filepath.Join(Root, IgnoreFileName), strings.TrimRight(wanted, "\n")),
	}}
}

// showPath renders an absolute path the way a diagnostic names it: relative to
// the repository root when it is inside one, in slash form.
func showPath(baseDir, full string) string {
	rel, err := filepath.Rel(baseDir, full)
	if err != nil {
		return filepath.ToSlash(full)
	}
	return filepath.ToSlash(rel)
}
