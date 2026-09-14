# Vocabulary system, define pages, TOML frontmatter, and selfdoc's part of the `.codehome/` layout

This file records a design ruled by the owner over two long sessions. Every
item under "Rulings" is decided; items under "Open points" are not. Counts
are a snapshot measured against the tree on the date given beside them and
must be re-measured before a plan relies on them. Nothing here launches on
this file's authority.

## Context

The unified docs site stopped rebuilding in mid-August. Two defects stacked:
first a strictspec runtime pairing mismatch in the published Python packages,
then, once that was cleared, the spell check. selfdoc's spelling engine
accepts words from a vendored English list, a built-in renderer vocabulary,
and one machine-level accept list at a fixed path in the owner's home
directory. The CI runner has no such file, so every project-specific word
(`claudewheel`, `UUID`, `symlink`, the project's own name) is an error there
while passing locally. The spelling lint is error severity and error-severity
codes cannot be suppressed, so no project can opt out. A derived copy of the
machine list pushed into the assembly repository is approved as a bridge
until this design ships; it is deleted when the vocabulary system replaces
it.

The glossary mechanism the Go port carried over is a build-time scrape:
terms come from `<dfn>` tags, Markdown definition lists, and the
`list-glossary` directive in page bodies; the renderer collects them into an
in-memory map, synthesizes a per-project glossary page, auto-links the first
occurrence of each other-page term, and emits DefinedTerm JSON-LD. The map is
never exported, never merged across projects, never seen by the spelling
engine, and has no lint codes. Duplicate declarations resolve silently by
navigation order.

Page frontmatter is a hand-parsed `---` block (`key: value`, flat bracket
lists), with no key registry: unknown keys are silently ignored and values
are untyped.

## Rulings

### Vocabulary data

- Two hand-authored TOML files per project, in one function directory:
  `vocabulary/accepted.toml` and `vocabulary/rejected.toml`. Accepted entries
  are `[[term]]` tables with `word`, `meaning`, optional `aliases`. Rejected
  entries are `[[term]]` tables with `pattern`, `kind` (one of `word`,
  `phrase`, `suffix`, `prefix`), and `reason`. Matching is case-insensitive
  on word boundaries. Both files are strictspec-validated. Entries are kept
  sorted by word; a lint enforces the order.
- Acceptance is project-wide. Pages do not declare the words they use. The
  accepted file is the single authority for a project's vocabulary; the
  rejected file is the single authority for what its pages may not say.
- Three layers for each list: a baseline shipped inside the selfdoc binary
  (general technical vocabulary and third-party product names, not this
  ecosystem's own terms); the per-project files; and a generated, committed,
  normalized word-per-line text file in the assembly repository, merged from
  every roster project's files by `assembly integrate`, which the CI runner
  reads. The machine-level accept list is retired by a one-time split into
  baseline and per-project files; the split is shipped as generated and the
  owner reviews the committed files afterwards, moving misfiled words as
  noticed. Words the split finds used by no project are dropped.
- A word present in both an accepted and a rejected list, in any layer, is a
  load-time hard error naming both files.
- Editing commands: `selfdoc vocabulary accept <word> --meaning <text>`,
  `selfdoc vocabulary reject <pattern> --kind <kind> --reason <text>`, and
  `selfdoc vocabulary remove <word>`, editing the files through go-toml-edit
  so comments and order are preserved, refusing duplicates and conflicts.
  Every lint remedy that tells the author to add or remove a term names one
  of these commands, and each remedy is executed once in a test.

### Lints

- `SPELL001` (unrecognized word) stays, with its remedy rewritten to name the
  accept command and the project's accepted file.
- One new family, `VOCAB`: an accepted word no page in the project uses
  (unused definition); a duplicate entry in a list; a word present in both an
  accepted and a rejected list; a rejected term found in a page. All error
  severity. Registered in `lints.toml`, mirrored wherever the registry is
  pinned (the payload schema enum, the check guide table).

### Define pages

- One page per defined term at the site root, `/define/<slug>/`, replacing
  per-project glossary pages entirely. The slug is the case-folded word with
  phrases hyphenated; aliases and plural forms resolve to the canonical slug
  at link time, so no redirect pages exist.
- A page carries one sense per defining project: the meaning with the
  project's name and a link into the project, the aliases, the pages across
  the site where the term occurs with an excerpt per page, and the other
  terms the same project defines. Several projects defining one word produce
  one page with several senses; a merge never drops a sense. Each sense emits
  DefinedTerm JSON-LD.
- Only terms with a meaning get pages. Baseline words and rejected terms get
  none.
- Each project build emits its own define pages under its own root with its
  own senses, so a standalone build is complete and its clickable links
  resolve inside the tree it built. `assembly integrate` lifts every project's
  define pages into the root `/define/`, merges same-slug pages into
  multi-sense pages, and rewrites the relative links in its resolution pass.
- No per-project term index. One `/define/` index at the root, grouped by
  letter and by project, owned by the home project like the rest of the root.
- Auto-linking: a project build links the first occurrence of its own terms
  on each page; the assembly pass additionally links occurrences of every
  roster project's terms. The two outputs differ by declared build mode.
- A per-page frontmatter key opts a single page out of auto-links (a dense
  reference table, for example); the project-level `glossary` flag turns the
  feature off for the project, and off means no define pages and no links.
- The old declaration forms (`<dfn>` scraping, definition-list scraping, the
  `list-glossary` directive as a declaration) are removed, not extended. A
  `<dfn>` in a page may remain as presentation and must correspond to an
  accepted term.

### Defects to fix in the same work, because they sit where this lands

- The glossary page's JSON-LD is corrupted by the auto-linker, which links
  inside script text; `script` and `style` join the linker's skip set and
  JSON-LD is appended after linking.
- `glossary: false` disables only the synthesized page today; it must disable
  collection and linking too.
- The glossary guide describes a `glossary-terms.md` template merge and a
  unified-build merge with project attribution; neither exists (the merge
  functions had no callers). The claims go, and the define pages replace
  them.
- The auto-linker matches substrings with no word boundaries; it must match
  whole words, sharing the spelling engine's tokenizer.
- The project's own term page hand-types the number of terms it defines.

### TOML frontmatter

- Every page and post carries TOML frontmatter between `+++` fences. A `---`
  block is refused as the old format after conversion; there is no dual
  reading.
- A strictspec-generated validator governs the block: a declared key
  registry, unknown keys refused, typed values (dates as dates, tags as
  arrays), two document kinds (page and post) in one schema. The post lints
  that check presence and date format today derive from the schema.
- `order` collapses into `nav_order`; the converter rewrites existing `order`
  values and the schema refuses `order`. The key `project` (present in two
  posts, read by nothing) is refused.
- The registry declares every key the code reads, including the ones no file
  uses yet: the release-post keys written by `blog post generate`, and the
  documented per-page switches (`auto_steps`, `auto_api`, `schema`,
  `updated`, `versioned`, `feed`, `type`), plus the new auto-link opt-out.
- Emitters (generated API pages, CLI reference pages, scaffolds, release
  posts) write TOML through go-toml-edit's canonical renderers so their
  escaping matches the library's.
- Conversion of existing pages is not a tool feature. Generated pages are
  regenerated after the emitters switch. Hand-authored pages are converted
  by a dry-run-capable script under `scripts/`, run per project by hand, with
  the occurrence count asserted and the diff reviewed. The known hard cases
  are values containing a colon, values containing a double quote, and the
  bracket lists in posts.
- The three independent frontmatter readers (the parser, the staleness
  body-stripper, and the generated-marker string match in `gen`) become one.

### selfdoc's part of the `.codehome/` layout

The owner's `.codehome/` program (recorded in a sibling repository's todo,
with a superseding-rulings file beside it) moves every tool's per-repo state
into one `.codehome/` directory of function-named directories. selfdoc goes
first, and its whole part goes at once, page content included.

- Function directories selfdoc claims: `docs/` (handwritten: docs
  configuration, the pages, the underscore templates), `docs-state/`
  (generated, committed: manifests, hashes, revisions, generated read-only
  pages), `docs-cache/` (generated, uncommitted), `posts/` (handwritten), and
  `vocabulary/` (handwritten, this design's files).
- Ownership: one owner tool per directory, declared in `.codehome/OWNERS.csv`
  (two columns: directory name, owner tool). All directories present are
  named and everything named exists. A row is the permission to create the
  directory; a tool creating a directory under `.codehome/` without a row is a
  hard error. Anyone may read or write; the owner validates. selfdoc exposes
  a framework-owned layout dump (which directories it claims, their side and
  commitment, deprecated former names) and a validate command per claimed
  directory, so a fleet check can verify: every directory is bijected with
  the file; every owner is an installed tool; every owner still claims its
  directories; every owner's validator passes; then each tool's own checks.
- No hidden entries inside `.codehome/` other than git's own ignore file,
  which is derived once at `.codehome/.gitignore` from the tools' commitment
  declarations rather than one per directory.
- No migrator. The tool flips its read paths in one release and refuses the
  old layout with an error naming the new path. Repositories are moved by
  hand: a dry-run-capable script under `scripts/` performs the pure move with
  `safegit mv` as one commit and the content rewrites as a second commit.
  `.codehome/` itself is created by the person running the script.
- URL preservation for the page-content move: page URLs derive from the
  path relative to the configured docs root, so a docs root of
  `.codehome/docs/` keeps every URL. The build merges two roots (handwritten
  `docs/`, generated `docs-state/`) into one URL namespace and refuses
  collisions. Before the move each project's sitemap is captured; after the
  move the build must produce the identical URL set, and a check fails on any
  difference. The existing emitted-reference lint covers links that reach
  outside the docs tree.

## Open points

- The exact slug rule for terms containing characters other than letters,
  digits, spaces and hyphens.
- The initial content of the rejected baseline (the owner's own prose bans
  are one candidate source; whether they apply to documentation is the
  owner's call).
- Whether `<dfn>` presentation in pages is kept at all, or removed with the
  scrape.
- The name of the per-page auto-link opt-out key.

## Head count (measured 2026-09-12 against the Python tree; re-measure)

Reproducible with `scripts/frontmatter-census.py` for the frontmatter
figures; the rest came from the commands named in the survey that produced
them and must be re-run against the Go tree.

- Projects with a `selfdoc.json` in scope: 29 (two archived).
- Pages with a frontmatter block: 2421, of which 2108 generated and 313
  hand-authored; posts: 4.
- Distinct frontmatter keys present in files: 15; keys read by code: 25;
  union to declare: 26.
- Values needing non-mechanical conversion: 10.
- Real term declarations fleet-wide: 23, all in one page of this project.
- Machine accept-list words: 1339; used by no project 29, by one project
  796, by two or more 514; baseline candidates by the survey's
  classification about 486, of which about 28 are this ecosystem's own
  project names and belong per project.
- Lint registry entries: 46; pin sites a new code must touch: 6.
- Assembly roster: 17 projects; three more approved to join (dirstat,
  reposummary, strictspec).

## Affected areas (Go tree)

- `internal/spelling`, `internal/spellcorpus`: the three-layer accepted
  vocabulary, rejected matching, the tokenizer shared with the linker.
- `internal/html`: glossary scrape removal, define-page rendering,
  word-aware auto-linking, JSON-LD emission after linking, the skip set.
- `internal/util`, `internal/page`, `internal/build`: the TOML frontmatter
  reader and validator, the key registry, the two-root merge, the sitemap
  equality check.
- `internal/blog/assembly`, `internal/resolution`: lifting and merging
  define pages, the root index, cross-project linking, the merged word
  lists as build inputs.
- `internal/cli`: the `vocabulary` command group, the layout dump and
  validate commands.
- `lints.toml` and its pin sites; `strictspec.toml` and the generated
  validators (frontmatter, accepted, rejected, OWNERS is CSV and needs no
  validator).
- `docs/`: the glossary guide rewritten around define pages, the check guide
  table, the frontmatter documentation, the layout documentation.
- `scripts/`: the frontmatter converter and the layout move script, both
  dry-run capable.

## Effort

A campaign. Dependency order: the frontmatter reader and registry first
(everything else reads frontmatter); the layout move next (the vocabulary
files are born in their final directory); the vocabulary data, lints and
commands; the define pages and the assembly merge; the site-side merged word
lists and the removal of the bridge copy; the baseline split last, since it
is generated from the fleet's pages once the lints exist to check it.
