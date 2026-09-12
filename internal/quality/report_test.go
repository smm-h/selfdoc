package quality

import "testing"

// ratioOf is the addressable ratio a result carries.
func ratioOf(value float64) *float64 { return &value }

// The three reports below were produced by the Python renderer this package
// replaces, from the same results, and are compared byte for byte.
func TestTheReportIsTheOneTheCommandAlreadyPrints(t *testing.T) {
	cases := []struct {
		name   string
		result Result
		want   string
	}{
		{
			name: "a project at the top of the ladder",
			result: Result{
				Project: "selfdoc", Path: "/p/selfdoc", Tier: 5,
				TierName: "Advanced", CodeLOC: 123456, TestLOC: 23456,
				SourceLOC: 100000, DocLOC: 33333, DocFiles: 42,
				DocRatio: ratioOf(0.3333), ContentGrade: "A",
				Selfdoc: Adoption{
					HasSelfdoc: true, AutoREADME: true, AutoCLAUDE: false,
					CustomDirectives: 0, HasPosts: true, DirectiveCount: 97,
				},
			},
			want: `selfdoc -- Tier 5 / 5 (Advanced)

100,000 source LOC | 23,456 test LOC | 33,333 doc LOC (33.3%) | 42 files | Grade: A

Selfdoc:
  Auto-generated README    yes
  Auto-generated CLAUDE    no
  Custom directives        -
  Blog posts               yes
  Directive uses           97

Completed:
  Tier 1 -- Has markdown documentation
  Tier 2 -- selfdoc.json configured
  Tier 3 -- Auto-generated root files (README/CLAUDE)
  Tier 4 -- Directives connect docs to source code
  Tier 5 -- Custom directives or blog posts

All tiers complete.`,
		},
		{
			name: "a project with nothing at all",
			result: Result{
				Project: "bare", Path: "/p/bare", Tier: 0, TierName: "None",
				ContentGrade: "-", NextStep: NextSteps[0],
			},
			want: `bare -- Tier 0 / 5 (None)

0 source LOC | 0 doc LOC (n/a) | 0 files | Grade: -

Selfdoc: not configured

To do:
  Tier 1 -- Create a README.md with project description and usage
  Tier 2 -- selfdoc.json configured
  Tier 3 -- Auto-generated root files (README/CLAUDE)
  Tier 4 -- Directives connect docs to source code
  Tier 5 -- Custom directives or blog posts`,
		},
		{
			name: "a project halfway up",
			result: Result{
				Project: "mid", Path: "/p/mid", Tier: 3, TierName: "Templates",
				CodeLOC: 900, TestLOC: 0, SourceLOC: 900, DocLOC: 45,
				DocFiles: 3, DocRatio: ratioOf(0.05), ContentGrade: "C",
				Selfdoc: Adoption{
					HasSelfdoc: true, AutoREADME: true, AutoCLAUDE: true,
					CustomDirectives: 2, HasPosts: false, DirectiveCount: 0,
				},
				NextStep: NextSteps[3],
			},
			want: `mid -- Tier 3 / 5 (Templates)

900 source LOC | 45 doc LOC (5.0%) | 3 files | Grade: C

Selfdoc:
  Auto-generated README    yes
  Auto-generated CLAUDE    yes
  Custom directives        2
  Blog posts               no
  Directive uses           -

Completed:
  Tier 1 -- Has markdown documentation
  Tier 2 -- selfdoc.json configured
  Tier 3 -- Auto-generated root files (README/CLAUDE)

To do:
  Tier 4 -- Use :-: directives in docs/ to connect docs to source code
  Tier 5 -- Custom directives or blog posts`,
		},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			if got := FormatSingleText(testCase.result); got != testCase.want {
				t.Errorf("FormatSingleText =\n%s\nwant\n%s", got, testCase.want)
			}
		})
	}
}

func TestTheReportCarriesNoTrailingNewline(t *testing.T) {
	report := FormatSingleText(Result{TierName: "None", ContentGrade: "-", NextStep: NextSteps[0]})
	if report[len(report)-1] == '\n' {
		t.Error("the report ends with a newline; the caller adds it")
	}
}
