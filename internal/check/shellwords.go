package check

import (
	"errors"
	"fmt"
	"strings"
)

// ErrShellWords is the base every refusal of a command template wraps, so one
// errors.Is check covers them.
var ErrShellWords = errors.New("command template cannot be split into words")

// ErrUnbalancedQuote reports a command template that opens a quote and never
// closes it -- one of the two conditions shlex.split refuses.
var ErrUnbalancedQuote = fmt.Errorf("%w: no closing quotation", ErrShellWords)

// ErrDanglingEscape reports a command template ending in a backslash, which
// escapes nothing -- the other condition shlex.split refuses.
var ErrDanglingEscape = fmt.Errorf("%w: no escaped character", ErrShellWords)

// SplitShellWords splits a command line into words the way Python's
// shlex.split does in POSIX mode, which is what every configured example
// validator was written against.
//
// The rules, all of them reachable from a real "examples" entry:
//
//   - Words are separated by runs of whitespace, which contribute nothing.
//   - A single-quoted run is literal: nothing inside it is special, not even
//     a backslash.
//   - A double-quoted run keeps everything literal except a backslash before
//     a double quote or another backslash.
//   - Outside quotes a backslash escapes the next character, whatever it is;
//     a backslash at the very end escapes nothing and is
//     [ErrDanglingEscape].
//   - An empty quoted run still produces a word, so `go vet ""` is three
//     words and the third is empty.
//
// An unclosed quote is [ErrUnbalancedQuote]: the template says something the
// splitter cannot honestly read, and guessing where the word ends would run a
// command nobody wrote.
func SplitShellWords(line string) ([]string, error) {
	var words []string
	var current strings.Builder
	started := false

	runes := []rune(line)
	for index := 0; index < len(runes); index++ {
		char := runes[index]
		switch {
		case isShellSpace(char):
			if started {
				words = append(words, current.String())
				current.Reset()
				started = false
			}
		case char == '\'':
			started = true
			closing := -1
			for scan := index + 1; scan < len(runes); scan++ {
				if runes[scan] == '\'' {
					closing = scan
					break
				}
			}
			if closing < 0 {
				return nil, ErrUnbalancedQuote
			}
			current.WriteString(string(runes[index+1 : closing]))
			index = closing
		case char == '"':
			started = true
			closed := false
			for scan := index + 1; scan < len(runes); scan++ {
				if runes[scan] == '\\' && scan+1 < len(runes) &&
					(runes[scan+1] == '"' || runes[scan+1] == '\\') {
					current.WriteRune(runes[scan+1])
					scan++
					continue
				}
				if runes[scan] == '"' {
					index = scan
					closed = true
					break
				}
				current.WriteRune(runes[scan])
			}
			if !closed {
				return nil, ErrUnbalancedQuote
			}
		case char == '\\':
			started = true
			if index+1 >= len(runes) {
				return nil, ErrDanglingEscape
			}
			current.WriteRune(runes[index+1])
			index++
		default:
			started = true
			current.WriteRune(char)
		}
	}
	if started {
		words = append(words, current.String())
	}
	return words, nil
}

// isShellSpace reports whether a rune separates words, which for shlex is the
// ASCII whitespace set.
func isShellSpace(char rune) bool {
	switch char {
	case ' ', '\t', '\n', '\r', '\v', '\f':
		return true
	}
	return false
}
