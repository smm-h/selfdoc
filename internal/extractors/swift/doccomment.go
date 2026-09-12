package swift

import (
	"regexp"
	"strings"
)

// calloutKeywords are the callout labels a Swift doc comment can open a list
// item with. Every one of them renders as a bold label; a list item whose
// keyword is not among them stays a list item.
var calloutKeywords = map[string]bool{
	"Note": true, "Warning": true, "Important": true, "Precondition": true,
	"Postcondition": true, "Complexity": true, "SeeAlso": true, "Remark": true,
	"Requires": true, "Version": true, "Author": true, "Since": true,
	"Attention": true, "Bug": true, "Experiment": true, "TODO": true,
}

// The doc-comment patterns: the items Swift documents a function with, and the
// double-backtick symbol reference.
var (
	// doubleBacktickRe matches Swift's own symbol reference, ``Symbol``, which
	// renders as the one code span every other language writes.
	doubleBacktickRe = regexp.MustCompile("``(" + wordClass + "+)``")

	// singleParamRe matches the individual parameter syntax.
	singleParamRe = regexp.MustCompile(`^-` + spaceClass + `+Parameter` + spaceClass +
		`+(` + wordClass + `+)` + spaceClass + `*:` + spaceClass + `*(.*)`)

	// parametersBlockRe matches the header of the block parameter syntax.
	parametersBlockRe = regexp.MustCompile(`^-` + spaceClass + `+Parameters` + spaceClass + `*:`)

	// listItemRe matches a "- name: text" list item, which is what a block
	// parameter sub-item and every callout are.
	listItemRe = regexp.MustCompile(`^-` + spaceClass + `+(` + wordClass + `+)` +
		spaceClass + `*:` + spaceClass + `*(.*)`)

	// returnsRe and throwsRe match the two items that render a bold label of
	// their own.
	returnsRe = regexp.MustCompile(`^-` + spaceClass + `+Returns` + spaceClass +
		`*:` + spaceClass + `*(.*)`)
	throwsRe = regexp.MustCompile(`^-` + spaceClass + `+Throws` + spaceClass +
		`*:` + spaceClass + `*(.*)`)

	// The two patterns the parameter-coverage scanner asks with, which read
	// only the names and not the descriptions.
	singleParamNameRe = regexp.MustCompile(`^-` + spaceClass + `+Parameter` + spaceClass +
		`+(` + wordClass + `+)` + spaceClass + `*:`)
	parametersBlockNameRe = regexp.MustCompile(`^-` + spaceClass + `+Parameters` +
		spaceClass + `*:`)
	listItemNameRe = regexp.MustCompile(`^-` + spaceClass + `+(` + wordClass + `+)` +
		spaceClass + `*:`)

	// returnDocRe is the presence test the quality measurement asks: does this
	// doc comment say what the function returns.
	returnDocRe = regexp.MustCompile(`(?m)^-` + spaceClass + `+Returns` + spaceClass + `*:`)
)

// docScanner walks a doc comment's lines, so the items that continue onto the
// lines below them share one implementation.
type docScanner struct {
	lines []string
	i     int
}

// continuation appends the indented lines that continue the current item's
// text. A blank line and a new list item both end it, and so does a line that
// is not indented.
func (s *docScanner) continuation(text string) string {
	s.i++
	for s.i < len(s.lines) {
		nextStripped := strip(s.lines[s.i])
		if nextStripped == "" || strings.HasPrefix(nextStripped, "- ") {
			break
		}
		if lstripLen(s.lines[s.i]) == 0 {
			break
		}
		text += " " + nextStripped
		s.i++
	}
	return text
}

// parametersBlock reads the indented sub-items under a "- Parameters:" header
// into params. A blank line inside the block does not end it; an unindented or
// unmatched line does.
func (s *docScanner) parametersBlock(params *[][2]string) {
	s.i++
	for s.i < len(s.lines) {
		nextStripped := strip(s.lines[s.i])
		subMatch := listItemRe.FindStringSubmatch(nextStripped)
		if subMatch != nil && lstripLen(s.lines[s.i]) > 0 {
			desc := s.continuation(strip(subMatch[2]))
			*params = append(*params, [2]string{subMatch[1], desc})
			continue
		}
		if nextStripped == "" {
			s.i++
			continue
		}
		return
	}
}

// parseDocComment renders a Swift doc comment as Markdown.
//
// The parameter items -- both the individual "- Parameter name:" syntax and the
// "- Parameters:" block with its indented sub-items -- accumulate into one
// section; "- Returns:" and "- Throws:" and every callout keyword render a bold
// label; a double-backtick symbol reference becomes a code span; and every
// other line passes through.
func parseDocComment(text string) string {
	if text == "" {
		return ""
	}

	text = doubleBacktickRe.ReplaceAllString(text, "`${1}`")

	scanner := &docScanner{lines: strings.Split(text, "\n")}
	var out []string
	var params [][2]string

	flush := func() {
		if len(params) > 0 {
			flushParams(&out, params)
			params = nil
		}
	}

	for scanner.i < len(scanner.lines) {
		line := scanner.lines[scanner.i]
		stripped := strip(line)

		if m := singleParamRe.FindStringSubmatch(stripped); m != nil {
			desc := scanner.continuation(strip(m[2]))
			params = append(params, [2]string{m[1], desc})
			continue
		}

		if parametersBlockRe.MatchString(stripped) {
			scanner.parametersBlock(&params)
			continue
		}

		if m := returnsRe.FindStringSubmatch(stripped); m != nil {
			flush()
			desc := scanner.continuation(strip(m[1]))
			out = append(out, "**Returns:** "+desc)
			continue
		}

		if m := throwsRe.FindStringSubmatch(stripped); m != nil {
			flush()
			desc := scanner.continuation(strip(m[1]))
			out = append(out, "**Throws:** "+desc)
			continue
		}

		if m := listItemRe.FindStringSubmatch(stripped); m != nil && calloutKeywords[m[1]] {
			flush()
			keyword := m[1]
			content := scanner.continuation(strip(m[2]))
			out = append(out, "**"+keyword+":** "+content)
			continue
		}

		flush()
		out = append(out, line)
		scanner.i++
	}

	flush()

	return strings.Join(out, "\n")
}

// flushParams emits the accumulated parameter items as a bold label and a
// bullet list.
func flushParams(out *[]string, params [][2]string) {
	if len(*out) > 0 && (*out)[len(*out)-1] != "" {
		*out = append(*out, "")
	}
	*out = append(*out, "**Parameters:**", "")
	for _, param := range params {
		if param[1] != "" {
			*out = append(*out, "- `"+param[0]+"`: "+param[1])
		} else {
			*out = append(*out, "- `"+param[0]+"`")
		}
	}
	*out = append(*out, "")
}

// docParamNames lists the parameters a doc comment documents, through either
// syntax.
func docParamNames(docText string) map[string]bool {
	names := map[string]bool{}
	if docText == "" {
		return names
	}

	lines := strings.Split(docText, "\n")
	i := 0
	for i < len(lines) {
		stripped := strip(lines[i])

		if m := singleParamNameRe.FindStringSubmatch(stripped); m != nil {
			names[m[1]] = true
			i++
			continue
		}

		if parametersBlockNameRe.MatchString(stripped) {
			i++
			for i < len(lines) {
				subStripped := strip(lines[i])
				subMatch := listItemNameRe.FindStringSubmatch(subStripped)
				if subMatch != nil && lstripLen(lines[i]) > 0 {
					names[subMatch[1]] = true
					i++
				} else if subStripped == "" {
					i++
				} else {
					break
				}
			}
			continue
		}

		i++
	}

	return names
}

// hasReturnDoc reports whether a doc comment carries a "- Returns:" item.
func hasReturnDoc(docText string) bool {
	if docText == "" {
		return false
	}
	return returnDocRe.MatchString(docText)
}
