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
