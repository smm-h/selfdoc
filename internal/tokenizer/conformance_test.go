package tokenizer

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"strings"
	"testing"
)

// The corpus fixture holds one Markdown document per part, parts separated by
// a line reading "@@@". Both this test and the probe that produced
// pythonCorpusDigest read the same file, so neither language carries its own
// copy of the documents.
const (
	corpusPath      = "testdata/corpus.txt"
	corpusSeparator = "\n@@@\n"
)

// unitSep and recordSep separate the items of a token's list-valued fields in
// the rendering below. Neither appears in the corpus, so the rendering is
// unambiguous without any escaping -- which is what lets two languages
// produce it byte for byte.
const (
	unitSep   = "\x1f"
	recordSep = "\x1e"
)

// pythonCorpusDigest is the SHA-256 of the rendered token stream of every
// corpus document as the Python tokenizer produced it.
//
// It is the differential check on the whole port: the dispatch order, every
// span, every parsed field, the info-string vocabulary, the annotation lines
// and their order, the admonition detection, the definition-list blank-line
// handling, and both text-bearing surfaces. A single divergence anywhere moves
// the digest.
const pythonCorpusDigest = "77e6db14b87557a980118cc99b0cec410317450c04a5cbe3a644848505eddddc"

// pyBool renders a Go bool the way Python's str() renders one, because the
// rendering the digest is computed over came from Python.
func pyBool(b bool) string {
	if b {
		return "True"
	}
	return "False"
}

// renderToken renders one token as a single tab-separated line: the type name,
// the span, the type's own fields in declaration order, the token's text lines
// and whether it bears text.
func renderToken(tok Token) string {
	parts := []string{tokenTypeName(tok), fmt.Sprint(tok.Start()), fmt.Sprint(tok.End())}
	switch t := tok.(type) {
	case CodeBlock:
		annotations := make([]string, 0, len(t.Annotations))
		for _, a := range t.Annotations {
			annotations = append(annotations, a.Key+"="+a.Note)
		}
		parts = append(parts,
			t.Lang,
			strings.Join(t.Lines, unitSep),
			strings.Join(annotations, unitSep),
			pyBool(t.Run), pyBool(t.LineNumbers), fmt.Sprint(t.LineStart),
			pyBool(t.Validate),
		)
	case Heading:
		parts = append(parts, fmt.Sprint(t.Level), t.Text)
	case Table:
		parts = append(parts, strings.Join(t.Rows, unitSep))
	case UnorderedList:
		parts = append(parts, strings.Join(t.Items, unitSep))
	case OrderedList:
		parts = append(parts, strings.Join(t.Items, unitSep))
	case Blockquote:
		parts = append(parts, strings.Join(t.Lines, unitSep), t.AdmonitionType)
	case DefinitionList:
		entries := make([]string, 0, len(t.Entries))
		for _, entry := range t.Entries {
			entries = append(entries,
				entry.Term+unitSep+strings.Join(entry.Definitions, unitSep))
		}
		parts = append(parts, strings.Join(entries, recordSep))
	case Directive:
		parts = append(parts, t.Name, t.Arg, strings.Join(t.Body, unitSep))
	case Paragraph:
		parts = append(parts, strings.Join(t.Lines, unitSep))
	}
	parts = append(parts, strings.Join(TokenTextLines(tok), unitSep))
	if IsTextBearing(tok) {
		parts = append(parts, "text")
	} else {
		parts = append(parts, "plain")
	}
	return strings.Join(parts, "\t")
}

// tokenTypeName is the token's Python class name, which the rendering names.
func tokenTypeName(tok Token) string {
	switch tok.(type) {
	case CodeBlock:
		return "CodeBlock"
	case Heading:
		return "Heading"
	case Table:
		return "Table"
	case UnorderedList:
		return "UnorderedList"
	case OrderedList:
		return "OrderedList"
	case Blockquote:
		return "Blockquote"
	case DefinitionList:
		return "DefinitionList"
	case ThematicBreak:
		return "ThematicBreak"
	case BlankLine:
		return "BlankLine"
	case Directive:
		return "Directive"
	case Paragraph:
		return "Paragraph"
	}
	return fmt.Sprintf("%T", tok)
}

// corpusDocuments reads the fixture and returns its documents.
func corpusDocuments(t *testing.T) []string {
	t.Helper()
	blob, err := os.ReadFile(corpusPath)
	if err != nil {
		t.Fatalf("reading %s: %v", corpusPath, err)
	}
	return strings.Split(string(blob), corpusSeparator)
}

// renderCorpus renders every document's token stream, the text the digest is
// taken over.
func renderCorpus(t *testing.T) string {
	t.Helper()
	var out []string
	for idx, doc := range corpusDocuments(t) {
		out = append(out, fmt.Sprintf("=== %d", idx))
		for _, tok := range Tokenize(doc) {
			out = append(out, renderToken(tok))
		}
	}
	return strings.Join(out, "\n") + "\n"
}

// TestCorpusMatchesPython is the differential assertion over the whole corpus.
func TestCorpusMatchesPython(t *testing.T) {
	t.Parallel()
	sum := sha256.Sum256([]byte(renderCorpus(t)))
	if got := hex.EncodeToString(sum[:]); got != pythonCorpusDigest {
		t.Errorf("corpus digest = %s, want %s\nrendered stream:\n%s",
			got, pythonCorpusDigest, renderCorpus(t))
	}
}

// TestCorpusIsTabFree guards the rendering's one premise: a tab anywhere in a
// document would make the tab-separated line ambiguous, and the digest would
// stop meaning what it claims.
func TestCorpusIsTabFree(t *testing.T) {
	t.Parallel()
	for idx, doc := range corpusDocuments(t) {
		if strings.ContainsAny(doc, "\t"+unitSep+recordSep) {
			t.Errorf("document %d carries a tab or a separator character", idx)
		}
	}
}

// TestCorpusLineCoverage runs the gapless-coverage property over every corpus
// document, not just the handful the Python suite listed.
func TestCorpusLineCoverage(t *testing.T) {
	t.Parallel()
	for idx, doc := range corpusDocuments(t) {
		assertLineCoverage(t, fmt.Sprintf("document %d", idx), doc)
	}
}

// assertLineCoverage checks that every source line of content is covered by
// one token's span, and by no more than one.
func assertLineCoverage(t *testing.T, label, content string) {
	t.Helper()
	n := len(strings.Split(content, "\n"))
	covered := make([]bool, n+1) // 1-based
	for _, tok := range Tokenize(content) {
		if tok.Start() < 1 || tok.End() > n {
			t.Errorf("%s: token span %d-%d is outside 1-%d",
				label, tok.Start(), tok.End(), n)
			continue
		}
		for line := tok.Start(); line <= tok.End(); line++ {
			if covered[line] {
				t.Errorf("%s: line %d covered by more than one token", label, line)
			}
			covered[line] = true
		}
	}
	for line := 1; line <= n; line++ {
		if !covered[line] {
			t.Errorf("%s: line %d covered by no token", label, line)
		}
	}
}
