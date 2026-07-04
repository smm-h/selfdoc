# In-repo devlog via the posts subsystem

## Context

A consumer project wants a chronological devlog that lives inside its own repository (e.g., `docs/posts/`) and renders as a section of the project's own selfdoc site — not routed to an external assembly/posts repository. The posts subsystem exists (`selfdoc post new/list/generate/publish`, dated markdown with frontmatter); the reference deployments route posts to a separate assembly repo, so fully in-repo operation may or may not be a supported first-class path today.

## Problem

Verify and, where needed, implement first-class in-repo posts:

1. A `selfdoc.json` posts configuration that points at an in-repo directory and renders posts as pages of the project's own site (chronological index, prev/next, tags), with no assembly-repo involvement.
2. Posts included in the site's Atom feed and search index like ordinary pages.
3. `selfdoc post new` scaffolding into the in-repo directory; `publish` (assembly push) simply not configured — absence of assembly config must mean "local site only", not an error and not silent skipping of rendering.
4. Documented in the posts docs as a supported mode with a config example.

If all of this already works, this todo collapses to a documentation item (the supported-modes matrix) plus a config example.

## Solutions

- (a) **Recommended:** treat in-repo as the base mode of the posts subsystem (local rendering always; assembly push as an optional add-on when configured). Pros: simplest mental model, no external dependency for the common case. Cons: if the code currently assumes assembly, some detangling.
- (b) A separate "devlog" page-type distinct from posts. Pros: avoids touching the assembly flow. Cons: two chronological-content systems — duplication of exactly the kind selfdoc exists to avoid.

## Affected

posts subsystem modules, selfdoc.json config schema (posts section), site generator (index/feed integration), docs.

## Effort

S if in-repo rendering already works (docs + example + test); M if the assembly assumption is baked in.
