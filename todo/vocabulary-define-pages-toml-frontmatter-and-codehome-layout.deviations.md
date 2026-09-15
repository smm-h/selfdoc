# Deviations from the vocabulary, term pages, frontmatter and layout plan

Companion to `vocabulary-define-pages-toml-frontmatter-and-codehome-layout.md`.
Each entry records what the plan says, what changed, and what is built
instead. Entries are appended, never rewritten. The plan file stays as
written.

## Term pages are served under `/glossary/`, not `/define/`

- The plan says: one page per defined term at the site root under
  `/define/<slug>/`, with one `/define/` index at the root, and every
  mention of the root term directory uses that path.
- What changed: a web research pass found no ranking signal in any path
  segment, so the choice is precedent only, and documentation sites use a
  glossary directory (MDN's per-term glossary pages, ethereum.org's proposal
  to split its glossary into per-term URLs). The owner ruled for the
  documentation precedent.
- Built instead: `/glossary/<slug>/` for the term pages and `/glossary/` for
  the merged root index. Everything else in the term-page design is
  unchanged: one page per term, one sense per defining project, merge at
  assembly, aliases resolved at link time, no per-project index.

## The per-repository directory is `.stricttools/`, not `.codehome/`

- The plan says: selfdoc's function directories move under `.codehome/`,
  ownership is declared in `.codehome/OWNERS.csv`, the derived ignore file
  is `.codehome/.gitignore`, and the layout description names
  `.codehome/` throughout.
- What changed: the owner does not hold the codehome.com domain and judged
  the name a poor description of the directory (it is not a home for code;
  it holds tool-owned data about the code). The docs site is moving to
  stricttools.com with strict.tools as its shortener, so the directory, the
  domain and the tool family now share one name.
- Built instead: `.stricttools/` everywhere the plan says `.codehome/`:
  `.stricttools/OWNERS.csv`, `.stricttools/.gitignore`, and the function
  directories under it. The sibling repository's program and rulings files
  are not edited; a note beside them records the rename.

## No accept-list bridge into the assembly repository, and no merged word list for CI

- The plan says: a derived copy of the machine-level accept list is pushed
  into the assembly repository as a bridge until the vocabulary system
  ships, and the vocabulary system's third layer is a generated,
  normalized word-per-line file in the assembly repository, merged from
  every roster project's files, which the CI runner reads.
- What changed: the premise was measured against the retired Python
  surface. The Go assembly deploy builds pages through the build package
  and never runs the lint pass, so no spelling check runs on the CI runner
  and no run since the Go deploy started shows a spelling failure (the
  spelling failures in the record come from the last Python-surface run).
  The spell check runs where the docs are built and pushed: the developer
  machine at release time, where the accept list exists. The deploy
  workflow also clones every roster project's source, so any future
  runner-side lint could read the per-project vocabulary files directly.
- Built instead: nothing for the bridge. The third layer is not built; the
  accepted vocabulary has the shipped baseline and the per-project files.
  Cross-project term linking at assembly reads the roster projects' cloned
  vocabulary files. If the assembly ever gains a lint step, it reads those
  same files rather than a merged copy.

## Open points ruled after the plan was written

- The initial rejected baseline shipped inside the binary is seeded from the
  owner's prose bans (the banned words and phrases in the owner's
  instructions file), each with a reason. Ruled by the owner.
- `<dfn>` tags are removed with the scrape: a `<dfn>` left in a page body is
  a VOCAB lint error whose remedy names the vocabulary accept command and
  tells the author to drop the tag. Ruled by the owner.
- The per-page auto-link opt-out key is `glossary_links = false`. Ruled by
  the owner.
- The slug rule for terms containing characters other than letters, digits,
  spaces and hyphens is still open. The owner rejected collapsing such
  characters to hyphens because `C++` would become `c`; the candidate under
  consideration keeps every character legal in a URL path segment as
  written (`c++`, `uv.lock`, `.strictcli`), percent-encodes only the rest,
  and refuses two terms that produce one slug.

## The nav_order collapse reorders root pages that declared only nav_order

- The plan says: `order` collapses into `nav_order`; the converter rewrites
  existing `order` values and the schema refuses `order`.
- What changed: before the collapse, `order` governed the docs root and
  `nav_order` governed inside a group, so a root page's `nav_order` was
  inert. After the collapse a root page that declared only `nav_order` is
  honoured, which is a visible sidebar reorder (in this repository's own
  corpus fixture one page moved from seventh to third).
- Built instead: the collapse as planned, honouring the authored value. The
  alternative, dropping the inert key on conversion to preserve the old
  order, was not taken because it discards authored intent. Awaiting the
  owner's ruling; reversible by having the converter drop a root page's
  `nav_order` when no `order` was declared.

## Ownership is a manifest.toml per directory, not OWNERS.csv

- The plan says: ownership is declared in a single two-column file at the
  layout root, and a row there is the permission to create a directory.
- What changed: the owner rejected the single file (its name and its
  inflexible format) in favour of a `manifest.toml` inside each function
  directory, carrying `owner` only for now; function-level facts stay in the
  tool's layout declaration so nothing is copied into every repository.
- Built instead: `.stricttools/<dir>/manifest.toml`, strictspec-validated;
  the manifest is the permission to create and is what makes an empty
  function directory exist in git.

## Glossary slugs keep the term's written casing

- The plan says: the slug is the case-folded word with phrases hyphenated.
- What changed: the owner ruled that folding makes proper nouns, acronyms
  and constants look wrong (`C++`, `UUID`, `GENERATED_BY`) and that each
  term has exactly one canonical casing instead.
- Built instead: the slug is the word as written, spaces to hyphens, every
  path-legal character kept literally, the rest percent-encoded; two
  accepted terms or aliases that fold to the same string are a VOCAB error
  naming both, so one page per term holds without lowercasing.

## Titles are written, never derived

- The plan said nothing about titles; a search-surface change made after
  it derived a project's index title from its description.
- What changed: the owner ruled that titles are authored text, never
  composed from another field.
- Built instead: every page title composes written values only, page then
  project then site name; the index page's title is its own frontmatter
  title plus the site name; the description-derived title and its lint are
  gone.
