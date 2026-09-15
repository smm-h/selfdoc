package layout

import (
	"errors"
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
// The rules: every directory under [Root] carries a [ManifestFileName] naming
// a tool this machine has, and every directory selfdoc claims that exists
// names selfdoc; every directory selfdoc owns holds only what its side allows;
// nothing under [Root] starts with a dot except the derived ignore file; and
// that file's selfdoc block is what the declaration says it should be.
//
// A missing [Root] is returned as an error rather than a problem: the rest of
// the rules are unanswerable without it.
func Validate(baseDir string) ([]Problem, error) {
	rootPath := Path(baseDir, Root)
	info, err := os.Stat(rootPath)
	if err != nil || !info.IsDir() {
		return nil, fmt.Errorf(
			"%s is missing. selfdoc never creates it: make the directory yourself, and give each directory inside it a %s naming its owner -- %s holding:\n%s",
			Root, ManifestFileName, DirectoryManifestRel(DocsName),
			strings.TrimRight(DirectoryManifestContent(Owner), "\n"))
	}

	owners, problems := ownershipProblems(baseDir)
	problems = append(problems, sideProblems(baseDir, owners)...)
	problems = append(problems, hiddenProblems(baseDir, owners)...)
	problems = append(problems, ignoreProblems(baseDir)...)
	return problems, nil
}

// ownershipProblems reads every directory's manifest under [Root] and reports
// the ones that declare nothing, declare a tool this machine does not have, or
// declare another tool for a directory selfdoc claims.
//
// It returns the owner each directory declares, which is what the side and
// hidden rules read to decide whose directory they are looking at. A dotted
// entry is left to [hiddenProblems], which is the rule it breaks.
func ownershipProblems(baseDir string) (map[string]string, []Problem) {
	owners := map[string]string{}
	entries, err := os.ReadDir(Path(baseDir, Root))
	if err != nil {
		return owners, []Problem{{Check: CheckOwnership, Message: err.Error()}}
	}
	var problems []Problem
	for _, entry := range entries {
		name := entry.Name()
		if name == IgnoreFileName || strings.HasPrefix(name, ".") {
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
		manifest, readErr := ReadDirectoryManifest(baseDir, name)
		if errors.Is(readErr, os.ErrNotExist) {
			suggested := Owner
			if _, claimed := Lookup(name); !claimed {
				suggested = "<tool>"
			}
			problems = append(problems, Problem{
				Check: CheckOwnership,
				Message: fmt.Sprintf(
					"%s carries no %s, so nothing declares who owns it. Create %s holding this line:\n%s",
					filepath.Join(Root, name), ManifestFileName, DirectoryManifestRel(name),
					strings.TrimRight(DirectoryManifestContent(suggested), "\n")),
			})
			continue
		}
		if readErr != nil {
			problems = append(problems, Problem{Check: CheckOwnership, Message: readErr.Error()})
			continue
		}
		owners[name] = manifest.Owner
		if !KnownOwner(manifest.Owner) {
			problems = append(problems, Problem{
				Check: CheckOwnership,
				Message: fmt.Sprintf(
					"%s declares %q as the owner of %s, and this machine has no such tool. An owner is %q itself, or a name PATH answers with an executable.",
					DirectoryManifestRel(name), manifest.Owner, filepath.Join(Root, name), Owner),
			})
		}
		if _, claimed := Lookup(name); claimed && manifest.Owner != Owner {
			problems = append(problems, Problem{
				Check: CheckOwnership,
				Message: fmt.Sprintf(
					"%s is a directory selfdoc claims, and %s declares %q as its owner. Write this line instead, or rename the directory to one selfdoc does not claim:\n%s",
					filepath.Join(Root, name), DirectoryManifestRel(name), manifest.Owner,
					strings.TrimRight(DirectoryManifestContent(Owner), "\n")),
			})
		}
	}
	return owners, problems
}

// sideProblems reports the files sitting on the wrong side of the authorship
// line in the directories selfdoc owns.
//
// A Markdown file carrying selfdoc's generated-page marker belongs in the
// generated pages directory; one without it belongs in the handwritten docs
// directory. The uncommitted cache is not checked: it holds extracted
// checkouts and built output, which carry whatever the source tree carries.
func sideProblems(baseDir string, owners map[string]string) []Problem {
	var problems []Problem
	for _, dir := range Declared() {
		if owners[dir.Name] != Owner || dir.Commitment == Uncommitted {
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
func hiddenProblems(baseDir string, owners map[string]string) []Problem {
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
		if !claimed || owners[name] != Owner || declared.Commitment == Uncommitted {
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
