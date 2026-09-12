// Package directives is selfdoc's structured-marker parser.
//
// Directive syntax:
//
//	One-liner:   :-: name key="value" ...
//	Block open:  :<: name [key="value" ...]
//	Attr line:   :@: key="value"
//	Body sep:    :=:
//	Body line:   ::: content
//	Block close: :>:
//
// Directives inside fenced code blocks (``` or ~~~) are ignored. An unclosed
// block directive at EOF is a [DirectiveError].
//
// # Offsets are bytes, columns are characters
//
// Every index this package computes internally is a byte offset, because that
// is what Go's regexp reports. The one index it publishes -- [Directive.Column]
// -- is a CHARACTER offset, so a rendered "file:line:column" reads the same as
// the Python surface this package replaces. [BlankBacktickSpans] is the
// exception that proves the rule: it preserves byte length, so a caller that
// matched against its output must convert the byte offset it found into a
// character column against the ORIGINAL line, never against the blanked one.
package directives

import (
	"fmt"
	"strings"
)

// BacktickSpan is one CommonMark code span located in a line.
//
// Start and End bound the whole span including both delimiters; ContentStart
// and ContentEnd bound the text between them. All four are byte offsets into
// the string the span was found in. Fence is the number of backticks in each
// delimiter.
type BacktickSpan struct {
	Start        int
	End          int
	ContentStart int
	ContentEnd   int
	Fence        int
}

// FindBacktickSpans locates every backtick code span in text, in document
// order and without overlap.
//
// This is the one definition of where a code span begins and ends, shared
// deliberately: the directive scanner skips what is inside a span, the spell
// mask refuses to read it, and the renderer marks it as code. Three readers,
// one scanner -- otherwise one of them decides a stretch of text is code while
// another decides it is prose, which is how a masked span came to be rendered
// as unmarked prose.
//
// The rules are CommonMark's, and reproduce the Python surface's
// backreference-and-lookaround regex (`(`+)(?!`)(.+?)(?<!`)\1(?!`)`) including
// its backtracking:
//
//   - An opening delimiter is a run of N backticks taken whole, so the
//     character after it is never a backtick.
//   - The closing delimiter is the first later run of EXACTLY N backticks --
//     a run of a different length closes nothing.
//   - The content is at least one character and carries no newline, because
//     the Python pattern's "." never matched one.
//   - When a run of N backticks closes nothing, the scan retries at the next
//     position, which inside that run means retrying with a shorter opening
//     delimiter -- the exact effect of the regex engine advancing its start
//     position into the run.
func FindBacktickSpans(text string) []BacktickSpan {
	var out []BacktickSpan
	n := len(text)
	pos := 0
	for pos < n {
		if text[pos] != '`' {
			pos++
			continue
		}
		runEnd := pos
		for runEnd < n && text[runEnd] == '`' {
			runEnd++
		}
		fence := runEnd - pos
		contentStart := runEnd
		// The content may not cross a newline, so the closing delimiter must
		// stand before the next one.
		limit := n
		if i := strings.IndexByte(text[contentStart:], '\n'); i >= 0 {
			limit = contentStart + i
		}
		closeStart := -1
		// The content is at least one character, so the earliest closing
		// delimiter starts one past the opening one.
		for q := contentStart + 1; q < limit; {
			if text[q] != '`' {
				q++
				continue
			}
			e := q
			for e < n && text[e] == '`' {
				e++
			}
			if e-q == fence {
				closeStart = q
				break
			}
			q = e
		}
		if closeStart < 0 {
			pos++
			continue
		}
		out = append(out, BacktickSpan{
			Start:        pos,
			End:          closeStart + fence,
			ContentStart: contentStart,
			ContentEnd:   closeStart,
			Fence:        fence,
		})
		pos = closeStart + fence
	}
	return out
}

// placeholderText renders the null-byte placeholder that masks span i.
func placeholderText(i int) string {
	return fmt.Sprintf("\x00BTCK%d\x00", i)
}

// MaskBacktickSpans replaces every backtick code span in line with a null-byte
// placeholder, returning the masked line and the original text of each span in
// document order.
//
// This is the masking for REWRITING a line: the placeholder is shorter than
// what it replaces, so every offset after a span shifts. Restore the line with
// [UnmaskBacktickSpans]. A rule that reports a column must use
// [BlankBacktickSpans] instead.
func MaskBacktickSpans(line string) (string, []string) {
	spans := FindBacktickSpans(line)
	if len(spans) == 0 {
		return line, nil
	}
	placeholders := make([]string, len(spans))
	var b strings.Builder
	prev := 0
	for i, sp := range spans {
		placeholders[i] = line[sp.Start:sp.End]
		b.WriteString(line[prev:sp.Start])
		b.WriteString(placeholderText(i))
		prev = sp.End
	}
	b.WriteString(line[prev:])
	return b.String(), placeholders
}

// UnmaskBacktickSpans restores the placeholders [MaskBacktickSpans] wrote to
// the original span text.
func UnmaskBacktickSpans(line string, placeholders []string) string {
	for i, original := range placeholders {
		line = strings.ReplaceAll(line, placeholderText(i), original)
	}
	return line
}

// BlankBacktickSpans replaces every backtick code span in line with spaces,
// one per byte, so the result has the same length and every byte offset in it
// addresses the same byte in line.
//
// This is the variant for a rule that reports a position: what is inside a
// code span is code, and no prose rule should read it, but blanking it must
// not move anything after it. A caller that wants a character column converts
// the byte offset it found against the ORIGINAL line.
func BlankBacktickSpans(line string) string {
	spans := FindBacktickSpans(line)
	if len(spans) == 0 {
		return line
	}
	b := []byte(line)
	for _, sp := range spans {
		for i := sp.Start; i < sp.End; i++ {
			b[i] = ' '
		}
	}
	return string(b)
}
