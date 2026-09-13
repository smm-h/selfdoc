# Undistort the Python port into idiomatic Go

## Context

selfdoc was rewritten from Python into one Go module under a ruling that
favored reproducing the Python tool's output and messages first, then
diffing every consumer's build to decide where identity was worth keeping.
The diff came back clean, which means the port carries every shape the
Python implementation had, including the ones that exist only because
Python's standard library behaves a certain way. None of those shapes is
needed by a consumer: consumers read built sites, generated pages, the
manifest, the hash store and the check payload, and every one of those can
be kept stable while the code behind it becomes ordinary Go.

This todo lists each distortion with what it costs, what a Go design would
do instead, what output or contract it touches, and how to verify a
rework. Items are independent unless a dependency is stated. Each one is a
candidate for its own campaign or for grouping; the order below is by cost
of the distortion, not by the order to do them.

Two rules that bound the work:

- Every persisted contract keeps its bytes unless the item says how the
  change is versioned: the hash store version, the manifest schema version,
  the files record version, the root-file header, the machine-description
  templates the ownership predicate compares by equality, the search facet
  attributes, the `<selfdoc-region>` element, the pagefind index layout.
- Every user-visible change rides a release with a changelog entry. A
  rework that changes rendered HTML is verified with the browser suite in
  `internal/e2e` and a before/after build of at least the three fixture
  checkouts that suite writes, and preferably with a consumer build.

## D1. The hand-written Markdown converter instead of goldmark

**What exists.** `internal/html` is a line-for-line port of a hand-written
converter: a block tokenizer in `internal/tokenizer` that recognizes only
flat lists (no nesting, no lazy continuation, no multi-paragraph items),
no HTML blocks (a raw HTML line becomes a paragraph wrapped in `<p>`), no
setext headings, no tilde fences, tables that require leading and trailing
pipes, blockquotes joined into one paragraph, and a private frontmatter
dialect; then a renderer that emits HTML strings and runs post-passes over
the joined HTML string with regular expressions: code-tab grouping, step
guides, API entry cards, glossary term linking, cross-page term linking,
first-image priority, internal link rewriting, minification. Several of
those passes depend on each code figure occupying one output line and on
the exact heading anchor markup, so a renderer change silently disables a
pass instead of failing. The TOC, the SEO tags and the page metadata read
facts back out of the rendered HTML with regexes (language classes, list
and paragraph counts, the CV person payload, `<dfn>` scraping, a
`class="cv-updated"` probe).

**Why it is a distortion.** Go has goldmark, a CommonMark-compliant parser
with an AST, extensions for tables and task lists, and a renderer registry
where each node kind has its own renderer function. Everything the
post-passes do is an AST transformation or a custom renderer in that
model, and every fact the SEO layer scrapes is available from the AST
before rendering.

**What changes for users.** Nested lists render as lists instead of
paragraphs, raw HTML blocks are emitted as blocks, setext headings and
tilde fences work. Those are corrections. Everything the theme contract
depends on (class names, ARIA attributes, table wrapper and caption, the
callout markup, the code figure, the heading anchor link, definition lists
and `term-` ids) is produced by custom renderers and stays identical.

**How to do it.**

- Parse with goldmark plus `extension.Table`, `extension.TaskList`, and a
  small custom block parser for the `[!NOTE]`-style admonitions and the
  definition-list syntax, and a custom inline parser for `==mark==`.
- Register renderers for heading, fenced code (chroma, diff detection,
  line numbers, annotations, the info-string vocabulary), table, list,
  blockquote, definition list, image, link, emphasis, and the `<data>`
  mark, each emitting exactly the markup `internal/html` emits today.
- Move each post-pass to an AST transformer: code tabs from consecutive
  fenced blocks with labels, step guides from an ordered list following a
  heading whose text starts with the guide words, API entry cards from the
  heading plus short code plus paragraph shape, glossary and cross-page
  terms from a text-node walk with a skip set of ancestor kinds, first
  image priority from the first image node.
- Give the page layer a typed `Page` result (title, headings with levels
  and anchors, declared terms, image count, list and paragraph counts,
  languages used, the CV person if any) so `internal/page` stops parsing
  its own output.
- Keep the frontmatter dialect as an explicit parser in `internal/util`
  with a documented grammar; do not swap in YAML, since consumer pages
  depend on the dialect's scalar coercions.
- Replace the string minifier with an HTML-aware minifier over the final
  document or keep it as a final pass; it is the one string pass that is
  legitimately a post-process.

**Verification.** The recorded reference corpus under `internal/page`
and `internal/html` `testdata/` becomes a set of golden files regenerated
deliberately with an `-update` flag; the browser suite passes; a consumer
build before and after differs only in the corrected constructs above,
each diff read and explained in the changelog entry.

## D2. Python-compatible JSON, string and date helpers in `internal/util`

**What exists.** `PythonJSON`, `PythonJSONIndent2`, `PythonJSONString`,
`PythonFloatRepr` reproduce `json.dumps` with `ensure_ascii` escaping and
Python float formatting; `PythonRepr`, `PythonStr`, `PythonStrip`,
`PythonSplitLines`, `PythonFields`, `IsPythonSpace`, the `Python*Class`
regex fragments reproduce Python's Unicode string semantics; `TitleCase`
reproduces `str.title()` including its odd capitalization after
apostrophes; `FormatDateLong` reproduces a glibc-only `strftime` form;
`PathJoin` reproduces `posixpath.join` including the absolute-tail rule.
Several packages hand-roll insertion-ordered JSON encoders because
`json.dumps` without `sort_keys` kept dict order.

**Why it is a distortion.** Each exists so an emitted byte matches the
Python implementation. Three kinds of consumer read those bytes: the hash
store compares hashes computed over canonical JSON; the manifest, files
record, projects record, revisions sidecar and outbound cache are read
back by selfdoc itself and by the assembly deploy; error messages are read
by people.

**What to do, per consumer.**

- Hash inputs: switch `ComputeSchemaHash` and the store writer to Go's
  `encoding/json` with sorted keys and bump the hash store version to 4.
  A version mismatch discards the store and re-baselines on the next `gen`
  and `check`, which every release runs, so the fleet re-baselines once
  with no manual step. The em-dash template strings the ownership
  predicate compares stay as they are; they are content, not encoding.
- Persisted documents: define Go structs with `json` tags for the
  manifest, the files record, the projects record, the revisions sidecar,
  the outbound cache and the listing sidecar, and encode with
  `encoding/json` (`MarshalIndent` where the file was indented). Key order
  becomes struct field order, which is stable and documented, and unknown
  keys are refused on read where the Python tolerated them (the manifest's
  tolerant reader stays tolerant only if a consumer needs it; the assembly
  is the only reader and it is this binary). Bump `schema_version` where a
  reader could see a difference.
- Messages: reword every error and refusal that interpolates a value with
  Python `repr` quoting to Go `%q`, and delete `PythonRepr`,
  `PythonStr`, `PythonTypeName`. Pin the new wording in the same tests.
- Strings: replace `PythonStrip`, `PythonSplitLines`, `PythonFields` and
  the `Python*Class` fragments with `strings` and `unicode` functions and
  `\p{L}\p{N}` classes where Unicode awareness is wanted; delete the
  helpers. `TitleCase` has one caller in navigation labels; use
  `cases.Title` from `golang.org/x/text` and accept the label change.
  `FormatDateLong` becomes `time.Format` with a Go layout; the visible
  form ("September 13, 2026") does not change.
- Paths: audit every `util.PathJoin` call; where both operands are
  repository-relative, `path.Join` is correct; where a directive attribute
  may be absolute, decide explicitly whether an absolute path is allowed
  (see D9) and then use `path.Join` or refuse.

## D3. Insertion-ordered containers standing in for Python dicts

**What exists.** `extractors.JSONObject` (an ordered JSON object used for
config tables, the strictcli schema and OpenAPI documents),
`identity.Entity` (an ordered property list for JSON-LD), `page.SourceFile`
slices in place of a map, `Directive.AttrOrder` beside `Directive.Attrs`,
`Post.FrontmatterKeys` beside `Post.Frontmatter`, the process-wide picker
id counter behind a mutex, `SiteTerms` with insertion order, and sorted
iteration everywhere a Python dict's order leaked into output.

**Why it is a distortion.** Order is a property of the source document, not
of a container. The config table and the schema page legitimately follow
document order; JSON-LD property order is a struct's field order; a
directive's attribute order and a post's frontmatter key order are the
author's and belong to a parsed representation that records positions.

**What to do.** Keep `JSONObject` as the one ordered JSON type, but make
it the decoder's output for documents whose order is meaningful and use
plain structs everywhere else. Replace `identity.Entity` with a struct
marshaled by `encoding/json` in field order. Replace `Directive.Attrs`
plus `AttrOrder` with `[]Attr{Key, Value}` and a lookup method. Replace
`Post.Frontmatter` plus `FrontmatterKeys` with an ordered frontmatter type
produced by the frontmatter parser and used by every writer of
frontmatter. Replace the picker counter with ids derived from the page
path and picker kind, which makes the same page render the same ids in
every process.

## D4. Regular expressions rewritten as hand scanners to match Python

**What exists.** The backtick-span scanner in `internal/directives` with a
differential corpus generated from Python's backtracking regex, the
trailing-comment stripper in the JS minifier, the code-label and
class-less `<ol>` checks, the unescaped-pipe table splitter, the TOC
heading pair scanner, the spelling marker mask, the word-locator with
Unicode word boundaries, and the dart, kotlin and sql lookaround
replacements.

**Why it is a distortion.** Half of these disappear with D1 (everything
that scans rendered HTML). The backtick scanner should implement the
CommonMark code-span rule directly rather than reproduce a regex's
backtracking; the two are the same for valid input and differ only on
malformed runs, where CommonMark is the specification. The spelling mask
should tokenize the document once with the tokenizer and mask code spans
from the AST rather than by regex over raw lines.

**What to do.** After D1, delete every scanner over HTML. Rewrite the
backtick scanner to the CommonMark rule and regenerate its corpus from a
CommonMark reference implementation instead of from Python. Feed the
spelling engine the block tokens' text with code spans already removed.
Keep the extractor scanners until D6 replaces them.

## D5. Message-text parity and the sentinel protocol

**What exists.** Error and refusal messages were kept byte for byte,
including Python names that were later swept; the check command detects a
failed directive by the resolved text starting with `> *[selfdoc:` and
recovers the message by stripping a character class from both ends, which
mangles messages ending in certain characters; post lint codes are chosen
by substring-matching a post error's message text; the check exit code is
one shared function but the report format is a fixed set of printf lines
with colour chosen per call.

**What to do.** Give directive resolution a structured result:
`Resolution{Markdown string; Failure *DirectiveFailure}` where the failure
carries the directive name, the file and line, and a typed cause; the
check reads the struct and the build renders the placeholder text from it.
Give `posts.PostError` a `Code` field set at the raise site so the lint
code never depends on message wording. Turn the check report into a
renderer over `CheckResult` with a `Reporter` interface (text, JSON) and
delete the colour flag from the render call in favor of a writer that
knows whether it is a terminal. Reword messages freely once nothing
matches on them.

## D6. Regex line scanners as language extractors

**What exists.** Eight extractors are faithful ports of regex line
scanners: Go, TypeScript and JavaScript, Svelte, Zig, Dart, Kotlin, Swift,
SQL. Their known defects were kept on purpose: the Go scanner counts
capitalized composite-literal keys inside `var (...)` blocks as exported
symbols, reads a generated-file header separated from `package` by a blank
line as the package doc, and cannot resolve an unexported `target=`; the
Svelte scanner cuts `<script>` blocks with a regex that a `<script>` string
in markup defeats; the TypeScript scanner's two extension lists disagree.
The Python extractor already parses in-process through gotreesitter.

**What to do, in this order.**

- Go: `go/parser`, `go/ast`, `go/doc` from the standard library. The
  package doc follows Go's own rule (no blank line before `package`),
  composite-literal keys are not declarations, unexported targets resolve
  because the AST holds every declaration, generics and multi-line
  signatures work, and `go/printer` renders signatures. Output changes:
  `go/doc` sorts by kind then name and prints signatures its own way. Ship
  as its own release with a before/after diff of the Go consumers, and
  close the open todos that describe these defects.
- The other six on gotreesitter with one shared query layer: a grammar per
  language, a declaration query per language, and one docstring and
  signature model feeding the shared Markdown renderer in
  `internal/extractors`. The SQL scanner is the exception: it is a
  purpose-built PostgreSQL DDL reader and gotreesitter's SQL grammars are
  dialect-inconsistent, so it stays hand-written but should move from
  regex to a real tokenizer.
- Contribute a per-grammar package to gotreesitter or vendor the grammar
  tables selfdoc uses so `go install` builds stop embedding every grammar;
  the release archives already build with the Python-only tags.

## D7. `map[string]any` configuration

**What exists.** `config.Config` is `map[string]any` shaped like the Python
dict, validated by a table of field specs reproducing the Python
validation order and messages, and read by key in every package
(`cfg["versions"]`, `cfg["topology"].(map[string]any)["slug"]`). The
required-ness of `versions` and `locales` lives in the build, not the
loader. `strict_keys` is inconsistent across nested tables. The `directives`
and `schema_types` values are unvalidated. A runtime-only
`_version_override` key is injected into the map.

**What to do.** Define a `Config` struct with typed fields (`Versions
[]Version`, `Locales []Locale`, `Source []SourceEntry`, `Topology
*Topology`, `Assembly *Assembly`, `Posts *Posts`, `Directives
map[string]string`, and so on), decode `selfdoc.json` with
`encoding/json` into it with `DisallowUnknownFields`, and validate with a
strictspec-generated validator so the schema is a document
(`selfdoc.schema.toml`) that also renders the configuration reference page
through `table-config-schema`, replacing the hand-written field-spec table.
Move `versions`/`locales` required-ness into the schema. Make every nested
table strict. Replace the injected `_version_override` key with a field on
the build and gen options. Every package then takes `*config.Config` and
reads fields; the `map[string]any` accessors and the per-package type
assertions go.

## D8. The effects layer and process-wide state

**What exists.** `effects.Handle` is threaded explicitly, which is right,
but the timeout, cwd, env, capture and read options are per-call
functional options rather than a `context.Context`, and three servers
(`serve`, `assembly preview`, `blog editor serve`) install their own
signal handling and stop channels. `deploy.ResolveCloudflareEnv` mutates
the process environment. The editor's publish lock is a package-level
mutex.

**What to do.** Give every effects call a `context.Context` for deadline
and cancellation and derive the per-call timeout from it; the servers take
a context from the command and stop when it is cancelled, with one signal
handler in `cmd/selfdoc`. Pass credentials as explicit values on the
deploy and assembly options instead of writing them into the environment.
Move the publish lock into the editor `State`.

## D9. Path handling and filesystem access

**What exists.** Content directives resolve `path=` with a plain join and
no containment check, so a directive can read anywhere on the filesystem;
the reserved-name guard test exists only because a file named `aux.go`
broke `go install`; several packages take a directory string where an
`fs.FS` would express read-only access; the themes and the editor UI are
already served from `embed.FS`, but the docs walk, the built-tree walks in
`resolution`, `verify` and `chrome`, and the source-file readers in the
extractors take paths.

**What to do.** Decide and enforce one rule for directive paths (inside
the project root, or explicitly allowed absolute paths) in one resolver.
Take `fs.FS` for every reader of a tree the command does not mutate (the
docs directory during resolution, the source tree for extractors, the
built output for `check`, `verify` and `chrome`), which also lets tests
use `fstest.MapFS` instead of `t.TempDir()` for pure readers.

## D10. Package layout by Python module rather than by domain

**What exists.** One Go package per Python module: `html` and `page` split
one former file; `docs`, `render`, `build` and `unified` share the page
pipeline; `site`, `assembly`, `verify`, `sitedirectives`, `shared`,
`chrome`, `listing`, `preview` and `serving` are one domain cut nine ways
because Python had an import cycle to break; `check`, `lints`,
`resolution`, `staleness`, `ownership`, `spelling`, `spellcorpus` and
`quality` are the checking domain cut eight ways; `strictclisupport` and
`gen` are one feature.

**What to do.** Regroup by domain with fewer, larger packages: `render`
(tokenizer, converter, page chrome, themes, js), `project` (config,
address, urls, manifest, docs walk, posts), `extract` (the extractor
protocol and languages as subpackages), `build` (build, render in memory,
unified, gen, root files, strictcli pages), `check` (lints, coverage,
staleness, ownership, resolution, spelling, quality), `assembly` (site
model, operations, verify, shared pages, chrome, listing, site
directives, preview, serving), `editor`, `cli`. Do this after D1 and D7,
since both change the types those packages exchange, and do it as file
moves with `go fmt` and import rewrites, one domain per commit.

## D11. Tests recorded from the Python implementation

**What exists.** Many packages carry `testdata/` files recorded by running
the Python implementation and assert byte equality, with the recorder
scripts deleted since the Python is gone; the differential corpora for the
backtick scanner and the tokenizer were generated from Python; several
tests skip when a reference tree is absent; the browser suite and the
build tests shim pagefind onto PATH.

**What to do.** Convert every recorded reference into a golden file owned
by the Go implementation, regenerated with a `-update` flag and reviewed
in the diff, so a deliberate output change is a one-flag operation instead
of a hand edit of recorded bytes. Delete the skip branches that guarded
absent Python trees. Keep the pagefind shim, since the indexer is a real
external binary.

## D12. Shape of the CLI layer

**What exists.** Every optional boolean and scalar flag resolves its
default in the handler because strictcli bans defaults on mutating
commands, so each default is stated in the help text and again in code;
the build's lint pass reruns the check; `--json` is accepted by every
command but only three declare a payload; closed value sets such as
`--target` and `--scope` are validated in handlers rather than declared as
strictcli choices.

**What to do.** Declare choices for every closed value set so `--help`
and the generated CLI pages state them. Declare a payload schema for every
reporting command or make `--json` refuse on the ones without one. Decide
whether `build` lints at all or leaves that to `check`. Keep the
absent-means-default idiom where strictcli requires it, but generate the
help-text default from one constant so the two cannot disagree.

## Dependencies between items

- D4 and D5 shrink once D1 lands; do D1 first among the rendering items.
- D3's directive attribute change and D5's structured resolution touch
  the same types; do them together.
- D7 before D10, since the regrouping moves the types D7 introduces.
- D6's Go extractor is independent and is the next campaign already
  decided.
- D2's hash store bump is independent and cheap; it can ride any release.

## Affected files

Everything under `internal/`; the recorded `testdata/` trees; the
configuration reference pages under `docs/`; `.strictspec/` if D7 adds a
configuration schema; `cmd/selfdoc`.

## Effort

Each of D1, D6, D7 and D10 is a campaign of its own. D2, D3, D4, D5, D8,
D9, D11 and D12 are each a few days of focused work and can be folded into
whichever campaign touches their files.
