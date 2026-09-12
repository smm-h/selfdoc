package directives

import (
	"strings"
	"testing"
)

// A directive's attributes are reported in the order the source wrote them.
// The check report quotes a directive back to the reader, and a reader
// matching that quote against the template needs the spelling they typed --
// `ref path="." lang="go"`, not a re-alphabetized `ref lang="go" path="."`.
func TestAttrOrderFollowsTheSource(t *testing.T) {
	cases := []struct {
		name    string
		content string
		want    []string
	}{
		{
			name:    "oneliner",
			content: `:-: ref path="." lang="go"`,
			want:    []string{"path", "lang"},
		},
		{
			name:    "oneliner reversed",
			content: `:-: ref lang="go" path="."`,
			want:    []string{"lang", "path"},
		},
		{
			name: "block open line then attribute lines",
			content: strings.Join([]string{
				`:<: table-commands schema-dir="."`,
				`:@: title="Commands"`,
				`:@: group="cli"`,
				`:>:`,
			}, "\n"),
			want: []string{"schema-dir", "title", "group"},
		},
		{
			name:    "repeated key keeps its first position",
			content: `:-: ref path="a" lang="go" path="b"`,
			want:    []string{"path", "lang"},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			parsed, err := ParseDirectives(tc.content, nil)
			if err != nil {
				t.Fatalf("ParseDirectives: %v", err)
			}
			if len(parsed) != 1 {
				t.Fatalf("got %d directives, want 1", len(parsed))
			}
			got := parsed[0].AttrOrder
			if strings.Join(got, ",") != strings.Join(tc.want, ",") {
				t.Errorf("AttrOrder = %v, want %v", got, tc.want)
			}
			if len(got) != len(parsed[0].Attrs) {
				t.Errorf("AttrOrder has %d keys, Attrs has %d",
					len(got), len(parsed[0].Attrs))
			}
			for _, key := range got {
				if _, ok := parsed[0].Attrs[key]; !ok {
					t.Errorf("AttrOrder names %q, which Attrs does not carry", key)
				}
			}
		})
	}
}

// A repeated key keeps its last value, as Python's dict(findall(...)) does,
// while keeping the position of its first appearance.
func TestRepeatedAttrKeepsLastValue(t *testing.T) {
	parsed, err := ParseDirectives(`:-: ref path="a" lang="go" path="b"`, nil)
	if err != nil {
		t.Fatalf("ParseDirectives: %v", err)
	}
	if parsed[0].Attrs["path"] != "b" {
		t.Errorf(`Attrs["path"] = %q, want "b"`, parsed[0].Attrs["path"])
	}
}

// Inline directives carry the order too.
func TestInlineAttrOrder(t *testing.T) {
	found, err := FindInlineDirectives(`text :-: var key="project.version" fmt="plain" more`, 3, nil)
	if err != nil {
		t.Fatalf("FindInlineDirectives: %v", err)
	}
	if len(found) != 1 {
		t.Fatalf("got %d inline directives, want 1", len(found))
	}
	if strings.Join(found[0].AttrOrder, ",") != "key,fmt" {
		t.Errorf("AttrOrder = %v, want [key fmt]", found[0].AttrOrder)
	}
}
