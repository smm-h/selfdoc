package zig

import (
	"regexp"
	"strings"
)

// testBlock is one test block in a Zig source file.
type testBlock struct {
	Name   string
	Source string
}

// namedTest matches any test block's opening line, capturing its name.
var namedTest = regexp.MustCompile(`^test` + pySpace + `+"([^"]+)"` + pySpace + `*\{`)

// testPattern matches the opening line of the test block named testName.
func testPattern(testName string) *regexp.Regexp {
	return regexp.MustCompile(
		`^test` + pySpace + `+"` + regexp.QuoteMeta(testName) + `"` + pySpace + `*\{`)
}

// extractTestBlock is the source of the test block named testName, from its
// opening line to the line that closes its body. It reports false when the
// file has no such block.
func extractTestBlock(source, testName string) (string, bool) {
	lines := strings.Split(source, "\n")
	pattern := testPattern(testName)

	for i, line := range lines {
		if !pattern.MatchString(pyStrip(line)) {
			continue
		}
		if end, ok := blockEnd(lines, i); ok {
			return strings.Join(lines[i:end+1], "\n"), true
		}
	}

	return "", false
}

// extractAllTestBlocks lists every test block in a Zig source file, in source
// order.
func extractAllTestBlocks(source string) []testBlock {
	lines := strings.Split(source, "\n")
	var tests []testBlock

	i := 0
	for i < len(lines) {
		match := namedTest.FindStringSubmatch(pyStrip(lines[i]))
		if match == nil {
			i++
			continue
		}
		end, ok := blockEnd(lines, i)
		if !ok {
			i++
			continue
		}
		tests = append(tests, testBlock{
			Name:   match[1],
			Source: strings.Join(lines[i:end+1], "\n"),
		})
		i = end + 1
	}

	return tests
}

// blockEnd is the index of the line that closes the brace-delimited block
// starting at startIdx, counting braces. It reports false when the block is
// never closed.
func blockEnd(lines []string, startIdx int) (int, bool) {
	braceCount := 0
	started := false
	for k := startIdx; k < len(lines); k++ {
		for _, ch := range lines[k] {
			switch ch {
			case '{':
				braceCount++
				started = true
			case '}':
				braceCount--
			}
		}
		if started && braceCount == 0 {
			return k, true
		}
	}
	return 0, false
}
