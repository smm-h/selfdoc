package check

import (
	"encoding/json"
	"errors"
	"os/exec"
	"reflect"
	"strings"
	"testing"
)

// shellWordsCorpus are the command templates the splitter is measured against
// shlex on. Every configured example validator is one of these shapes.
var shellWordsCorpus = []string{
	`go vet {file}`,
	`python3 -m mypy --strict {file}`,
	`  spaced   out   {file}  `,
	`sh -c "echo {file}"`,
	`sh -c 'echo {file}'`,
	`tool --flag="a b" {file}`,
	`tool --flag='a b' {file}`,
	`tool "" {file}`,
	`tool '' {file}`,
	`tool a\ b {file}`,
	`tool "a\"b" {file}`,
	`tool "a\\b" {file}`,
	`tool 'a\b' {file}`,
	`tool "it's" {file}`,
	`tool 'say "hi"' {file}`,
	`tool	tabbed	{file}`,
	"tool\nnewline\n{file}",
	`tool a"b"c {file}`,
	`tool a'b'c {file}`,
	``,
	`   `,
	`tool \{file\}`,
	`tool "unterminated`,
	`tool 'unterminated`,
	`tool \`,
}

// shlexDriver splits each template with shlex and prints the results as JSON,
// with a null standing for a template shlex refused.
const shlexDriver = `
import json, shlex, sys

templates = json.loads(sys.stdin.read())
results = []
for template in templates:
    try:
        results.append(shlex.split(template))
    except ValueError:
        results.append(None)
sys.stdout.write(json.dumps(results))
`

// TestSplitShellWordsMatchesShlex measures the splitter against the one the
// Python passed every examples command through.
func TestSplitShellWordsMatchesShlex(t *testing.T) {
	requirePython(t)

	encoded, err := json.Marshal(shellWordsCorpus)
	if err != nil {
		t.Fatalf("encode corpus: %v", err)
	}
	command := exec.Command("python3", "-c", shlexDriver)
	command.Stdin = strings.NewReader(string(encoded))
	output, err := command.Output()
	if err != nil {
		t.Fatalf("python3 driver: %v", err)
	}
	var expected [][]string
	if err := json.Unmarshal(output, &expected); err != nil {
		t.Fatalf("decode results: %v", err)
	}
	if len(expected) != len(shellWordsCorpus) {
		t.Fatalf("results = %d, want %d", len(expected), len(shellWordsCorpus))
	}

	for index, template := range shellWordsCorpus {
		words, err := SplitShellWords(template)
		if expected[index] == nil {
			if err == nil {
				t.Errorf("template %d (%q): split into %q, shlex refused it",
					index, template, words)
			} else if !errors.Is(err, ErrShellWords) {
				t.Errorf("template %d (%q): refused with %v, want a refusal this package declares",
					index, template, err)
			}
			continue
		}
		if err != nil {
			t.Errorf("template %d (%q): refused with %v, shlex split it into %q",
				index, template, err, expected[index])
			continue
		}
		want := expected[index]
		if len(want) == 0 && len(words) == 0 {
			continue
		}
		if !reflect.DeepEqual(words, want) {
			t.Errorf("template %d (%q): split into %q, shlex said %q",
				index, template, words, want)
		}
	}
}
