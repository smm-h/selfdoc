package directives

import (
	"encoding/json"
	"os"
	"reflect"
	"strings"
	"testing"
)

// spanCase is one entry of the differential corpus in
// testdata/backtick_spans.json: an input line and the verdicts the Python
// regex this scanner replaces produced for it.
//
// The regex used a backreference and lookaround, which the Go regexp engine
// cannot express, so the port is a hand scanner and this corpus is how it is
// held to the original's behavior -- including the retry-with-a-shorter-opening
// -delimiter effect a regex engine gets for free by advancing its start
// position into a backtick run. Regenerate with
// scripts/backtick_span_corpus.py.
//
// Every line is ASCII on purpose: the Python blanker wrote one space per
// CHARACTER while this one writes one per BYTE, so a non-ASCII span is the one
// place the two deliberately disagree.
type spanCase struct {
	Line         string       `json:"line"`
	Spans        []corpusSpan `json:"spans"`
	Masked       string       `json:"masked"`
	Placeholders []string     `json:"placeholders"`
	Blanked      string       `json:"blanked"`
}

type corpusSpan struct {
	Start        int `json:"start"`
	End          int `json:"end"`
	ContentStart int `json:"content_start"`
	ContentEnd   int `json:"content_end"`
	Fence        int `json:"fence"`
}

func loadSpanCorpus(t *testing.T) []spanCase {
	t.Helper()
	raw, err := os.ReadFile("testdata/backtick_spans.json")
	if err != nil {
		t.Fatalf("reading the backtick-span corpus: %v", err)
	}
	var cases []spanCase
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatalf("decoding the backtick-span corpus: %v", err)
	}
	if len(cases) == 0 {
		t.Fatal("the backtick-span corpus is empty")
	}
	return cases
}

func TestFindBacktickSpansMatchesCorpus(t *testing.T) {
	for _, tc := range loadSpanCorpus(t) {
		t.Run(caseName(tc.Line), func(t *testing.T) {
			got := FindBacktickSpans(tc.Line)
			want := make([]BacktickSpan, 0, len(tc.Spans))
			for _, s := range tc.Spans {
				want = append(want, BacktickSpan{
					Start:        s.Start,
					End:          s.End,
					ContentStart: s.ContentStart,
					ContentEnd:   s.ContentEnd,
					Fence:        s.Fence,
				})
			}
			if len(got) == 0 && len(want) == 0 {
				return
			}
			if !reflect.DeepEqual(got, want) {
				t.Fatalf("FindBacktickSpans(%q) = %#v, want %#v", tc.Line, got, want)
			}
		})
	}
}

func TestMaskAndBlankBacktickSpansMatchCorpus(t *testing.T) {
	for _, tc := range loadSpanCorpus(t) {
		t.Run(caseName(tc.Line), func(t *testing.T) {
			masked, placeholders := MaskBacktickSpans(tc.Line)
			if masked != tc.Masked {
				t.Errorf("MaskBacktickSpans(%q) masked = %q, want %q",
					tc.Line, masked, tc.Masked)
			}
			if len(placeholders) != len(tc.Placeholders) {
				t.Fatalf("MaskBacktickSpans(%q) placeholders = %#v, want %#v",
					tc.Line, placeholders, tc.Placeholders)
			}
			for i := range placeholders {
				if placeholders[i] != tc.Placeholders[i] {
					t.Errorf("placeholder %d = %q, want %q",
						i, placeholders[i], tc.Placeholders[i])
				}
			}
			if restored := UnmaskBacktickSpans(masked, placeholders); restored != tc.Line {
				t.Errorf("UnmaskBacktickSpans round trip = %q, want %q", restored, tc.Line)
			}
			if blanked := BlankBacktickSpans(tc.Line); blanked != tc.Blanked {
				t.Errorf("BlankBacktickSpans(%q) = %q, want %q",
					tc.Line, blanked, tc.Blanked)
			}
		})
	}
}

func TestBlankBacktickSpansPreservesByteOffsets(t *testing.T) {
	// A span holding multi-byte characters is blanked byte for byte, so a
	// position found in the result addresses the same byte of the original.
	// This is where the Go scanner deliberately parts from the Python one,
	// whose spaces counted characters.
	line := "prose `héllo` more"
	blanked := BlankBacktickSpans(line)
	if len(blanked) != len(line) {
		t.Fatalf("blanked length %d, want %d", len(blanked), len(line))
	}
	idx := strings.Index(blanked, "more")
	if idx < 0 || line[idx:idx+4] != "more" {
		t.Fatalf("byte offset %d of %q does not address \"more\" in %q", idx, blanked, line)
	}
	if strings.Contains(blanked, "héllo") {
		t.Fatalf("span content survived blanking: %q", blanked)
	}
}

// caseName renders a corpus line as a readable subtest name.
func caseName(line string) string {
	if line == "" {
		return "empty"
	}
	return strings.NewReplacer("`", "T", " ", "_", "\n", "N").Replace(line)
}
