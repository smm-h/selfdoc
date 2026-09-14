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
