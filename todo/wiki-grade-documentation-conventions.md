# Wiki-grade documentation conventions, without a wiki

## Context

A thought experiment about integrating deeply with MediaWiki, or emitting
its formats, was taken apart into the things a wiki is good at. None of them
needs wikitext or a wiki server; each maps to a small addition on the
existing design: Markdown pages with TOML frontmatter under the
`.stricttools/` layout, the vocabulary files, the glossary pages, the
assembly of many projects into one site, and the verification that runs
over the assembled tree. What follows is the full list, so it can be built
piece by piece as goodies the site should have regardless of where the
ideas came from. Where an item touches the assembly, "the site" means the
unified site the assembly serves, and "a project" means one roster project.

The wiki's own information architecture is the model: one page per concept
under a canonical title, alternate names redirecting to it, one
disambiguation page when a word means several things, a definition in the
first sentence, an infobox of facts, categories, backlinks ("what links
here"), page history and attribution, a place to discuss, a feed of recent
changes, a queryable API, and export for other systems. Answer engines cite
Wikipedia because of that architecture and because every page is a node in
a public entity graph; the markup has nothing to do with it.

## Items

### Readers and search

- **Alias and rename redirects.** Glossary aliases already resolve at link
  time; nothing serves a reader who arrives at `/glossary/<alias>/` or at a
  page's old address after a rename. Generate static redirects (a Cloudflare
  Pages `_redirects` file at assembly, or stub pages carrying a canonical
  link where the host cannot redirect) from two sources: the alias table of
  every project's accepted vocabulary, and the move records that the layout
  move script and `safegit mv --moved` write. Verification: every alias and
  every recorded old address answers with a redirect to an emitted page.
  Small.
- **Sense anchors on glossary pages.** A term page carries one sense per
  defining project; give each sense a stable anchor (`#<slug>` of the
  project) so a cross-project link can point at the sense it means, and let
  the auto-linker use the anchor when the linking page belongs to one of the
  defining projects. Small.
- **Definition-first lint for term pages.** Every glossary page opens with
  one sentence that defines the term, rendered from the entry's `meaning`;
  a lint (VOCAB family) refuses a meaning that is not a single sentence, or
  that repeats the word without defining it. Small.
- **Fact box on every project index.** A rendered box with what the project
  is (its description), language, license, latest released version, the
  install command, the repository, the changelog and the issues link, fed
  from selfdoc.json and the project's release record, and mirrored into the
  SoftwareSourceCode JSON-LD so the same facts are machine-readable in the
  same place a reader sees them. Medium; the JSON-LD emitter exists, the
  box and its data plumbing do not.
- **Category pages.** Tags and nav groups get generated index pages
  (`/tags/<tag>/` per project and site-wide at assembly) and a category line
  at the foot of each page; the JSON-LD gains `keywords` from the same tags.
  The sibling block stays the site-level "same category" navigation.
  Medium.
- **Backlinks ("what links here").** The assembly already extracts every
  internal reference for verification; keep that graph and render a
  backlinks section on glossary pages (the design's "pages where the term
  occurs") and on every page behind a frontmatter switch. The same graph
  makes an orphan report (pages nothing links) a one-line query. Medium.
- **Entity linking.** Accepted vocabulary entries gain an optional
  `wikidata` key (the Wikipedia article URL derives from it); the glossary
  renderer emits both as `sameAs` on the DefinedTerm, the Organization or
  Person node carries its own `sameAs`, and SoftwareSourceCode's
  `programmingLanguage` points at the language's Wikidata item. The shipped
  baseline vocabulary is seeded with identifiers by one lookup pass; the
  fleet's own terms have none, which is honest. No items are created on
  Wikidata for the tools themselves: its notability rules require outside
  coverage. Medium; this is the one structured-data practice with a
  measured effect on entity recognition.
- **Interlanguage verification.** Locales already emit alternates; add an
  assembly verification that every localized page carries hreflang
  alternates that resolve, and an `x-default`. Small.

### Authors and agents

- **Wikilink authoring.** A goldmark extension resolving `[[Term]]` and
  `[[Term|shown text]]` to the glossary page through the alias table, case
  as declared, refusing an unknown term with the accept command named. It is
  also the Obsidian convention, so notes written elsewhere paste in
  unchanged; ordinary Markdown links keep working. Small.
- **Prose transclusion.** Directives already transclude from code; add a
  parameterized `include` directive for prose snippets kept under the
  handwritten docs directory (a shared install warning, a shared support
  paragraph), so one block renders in many pages from one source. A missing
  snippet or an unknown parameter is a resolution error. Small.
- **History, attribution and freshness from git.** Every page gets "edit
  this page", "history" and "last changed" links and a byline, derived from
  the page's source file in git and the author block, rendered in the page
  chrome; the byline is the authorship signal the search research asked
  for. Generated pages link to the source they were generated from instead
  of to themselves. Small; the repository URL and edit-link plumbing exist.
- **A place to discuss.** A per-page "discuss" link to a GitHub Discussions
  category or an issue template pre-filled with the page path, configured
  per project in selfdoc.json; absent configuration means no link, never a
  default target. Small.
- **Recent changes feed.** A site-wide Atom feed of documentation changes
  generated at assembly from the git log of each project's documentation
  sources (page, change summary from the commit subject, project), beside
  the existing per-project feeds; a reader subscribes instead of watching.
  Medium.
- **Generated-page marker.** The authorship axiom keeps generated and
  handwritten directories apart; render a visible line on generated pages
  naming the source they come from and that edits belong there. This is
  also the generation disclosure line the search research recommends.
  Small.
- **A queryable page index.** Emit `/api/pages.json` at assembly (every
  page with title, description, tags, project, source path, last change)
  and a `.json` beside each page's `.html` with the same fields plus the
  rendered text, so an agent can query the site without scraping HTML.
  An MCP server over that index is a follow-on outside this todo. Medium.

### Interoperability and preservation

- **MediaWiki XML export.** Emit a MediaWiki export document per project
  and for the whole site (`<mediawiki><page><title/><revision><text/>`),
  bodies converted from Markdown to wikitext by a goldmark renderer that
  writes wikitext and falls back to inline HTML for output wikitext cannot
  express (directive tables, highlighted code). Anyone can import the docs
  into a wiki of their own. Medium; nothing reads it until someone asks.
- **Offline bundle.** Kiwix reads ZIM files and `zimwriterfs` builds one
  from a static site; add an assembly step that emits a ZIM of the whole
  site as a release asset of the assembly. Small, given the tool.
- **Outbound links and references.** Outbound link verification exists but
  is unconfigured, and every deploy prints that it was not checked. Turn it
  on with an `outbound.toml` naming the pages to check, and adopt a
  references section convention (a `references` directive rendering a
  numbered list from the page's frontmatter) for pages that cite. Small.
- **Print and document exports.** A print stylesheet ships per theme; PDF
  and EPUB exports are a pandoc pass over the same Markdown, exposed as
  `selfdoc export --format pdf|epub`, and refused rather than degraded when
  pandoc is absent. Small.

## Solutions

### Build them as independent items, each with its own lint or verification (recommended)

Every item above is self-contained; none changes the authoring format or
the layout. Order by dependency: entity linking and sense anchors after the
glossary pages exist; backlinks and category pages after the assembly keeps
its link graph; redirects after the alias table and move records are
readable; everything else in any order.

- Pros: each item ships in its own release with its own tests; nothing
  waits on a design round.
- Cons: none identified.

### Adopt MediaWiki itself

Rejected. It moves the pages out of the repository into a database, needs a
server the static host cannot provide, splits editing into a browser path
and a generated path, and its markup has no grammar any checker can hold
strictly. The upsides are all reachable as listed.

## Affected files

- `internal/blog/assembly`, `internal/blog/verify`, `internal/blog/shared`:
  redirects, backlinks graph, category and tag indexes, the page index, the
  recent-changes feed, the XML export and ZIM steps, the hreflang and
  outbound verifications.
- `internal/html` and the goldmark extensions: wikilinks, the `include`
  and `references` directives, the generated-page marker.
- `internal/page`: the fact box, the byline and git-derived links, the
  discuss link, `sameAs` emission in the JSON-LD.
- `internal/spelling` and the vocabulary schema: the `wikidata` key, the
  definition-first lint, sense anchors.
- `internal/cli`: `export`, and the configuration keys for discussion
  targets and outbound checking.
- `docs/`: one page per item as it ships, and the glossary guide.

## Effort

Several small items and a handful of medium ones; no single item is a
campaign, and each is independently releasable.
