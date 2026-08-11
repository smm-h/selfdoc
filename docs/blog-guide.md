---
title: Blog Posts
description: "How to create, manage, and publish blog posts in selfdoc, covering frontmatter, release-generated posts, revision tracking, assembly integration, publishing documentation without a release, the declared roster and project retirement, the canonical blog URL, and the portfolio canonical."
nav_group: "Guides"
nav_order: 19
---

# Blog Posts

selfdoc includes a blog system for publishing chronological content alongside your documentation. Blog posts are Markdown files with YAML frontmatter, stored in a dedicated directory within your project. Posts are unversioned -- they exist outside the multi-version docs system -- and are published to the unified documentation assembly alongside your API reference and guides.

The blog system is part of the `selfblog` package, which provides the CLI commands (`selfblog post new`, `selfblog post list`, `selfblog post publish`, etc.) and the assembly infrastructure for multi-project documentation sites.

## Configuration

Blog posts require a `posts` section in your `selfdoc.json`:

```json
{
  "posts": {
    "dir": ".selfdoc/posts/",
    "repo": "owner/posts-archive"
  }
}
```

- `dir` -- directory where post Markdown files live (defaults to `.selfdoc/posts/` if omitted)
- `repo` -- optional GitHub repository for archiving resolved post content

You also need `topology.slug` configured so that posts are attributed to your project in the unified site:

```json
{
  "topology": {
    "slug": "myproject"
  },
  "assembly": {
    "repo": "owner/assembly-repo"
  }
}
```

## Creating Posts

### Manual creation

Use `selfblog post new` to scaffold a new post file:

```bash
selfblog post new --title "My First Post"
```

This creates a file like `.selfdoc/posts/2026-07-29-my-first-post.md` with a frontmatter template:

```yaml
---
title: My First Post
date: 2026-07-29
slug: my-first-post
tags: []
draft: true
project: myproject
---
```

The filename is date-prefixed (`YYYY-MM-DD-slug.md`). The command errors if a file with that name already exists.

### Release-generated posts

`selfblog post generate` creates posts automatically from release metadata. This is typically called by release tooling (e.g., rlsbl post-release hooks) rather than manually:

```bash
selfblog post generate \
  --from-release \
  --version 1.2.0 \
  --prev-version 1.1.0 \
  --bump-type minor \
  --description "Added widget support" \
  --project-name "My Project" \
  --changelog-file .rlsbl/changes/1.2.0.md \
  --release-url "https://github.com/owner/repo/releases/tag/v1.2.0" \
  --registry-url "https://pypi.org/project/myproject/1.2.0/"
```

Generated release posts are created with `draft: false` and include release-specific frontmatter fields (`version`, `prev_version`, `bump_type`, `release_url`, `registry_urls`). The command also updates the project manifest with the new post entry.

Use `--dry-run` to preview the generated content without writing files.

## Frontmatter Format

Every post requires YAML frontmatter delimited by `---`. Required and optional fields:

### Required fields

| Field | Type | Description |
| --- | --- | --- |
| `title` | string | Post title. Must be non-empty. |
| `date` | string | Publication date in `YYYY-MM-DD` format. |

### Optional fields

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `slug` | string | derived from title | URL-safe identifier. Auto-generated from the title using kebab-case if omitted. |
| `tags` | list | `[]` | List of tag strings for categorization and search filtering. |
| `draft` | boolean | `false` | When `true`, the post is excluded from publishing and the unified site. |
| `project` | string | from config | Project slug for attribution in the unified site. |
| `locale` | string | none | Locale code for localized posts. |

### Release-specific fields

These fields are set by `selfblog post generate --from-release` and are not typically written by hand:

| Field | Type | Description |
| --- | --- | --- |
| `version` | string | The released version number. |
| `prev_version` | string | Previous version for upgrade context. |
| `bump_type` | string | Semver bump type (`patch`, `minor`, `major`). |
| `release_url` | string | URL to the GitHub release page. |
| `registry_urls` | list | Package registry URLs (PyPI, npm, etc.). |

### Slug immutability

Once a post is published (appears in the manifest), its slug cannot change. The `selfblog check` command enforces this: if a post file's slug differs from what was recorded in the manifest, it raises a `POST005` error. This prevents broken URLs in the unified site.

## Listing Posts

View all discovered posts with:

```bash
selfblog post list
```

Output shows each post's date, title, slug, and draft status:

```
2026-07-29  Widget Support  (widget-support)
2026-07-15  Getting Started  (getting-started)  [DRAFT]

2 post(s) found.
```

Posts are sorted newest-first, with same-date posts sorted alphabetically by slug.

## Publishing Posts

`selfblog post publish` pushes non-draft posts to the documentation assembly:

```bash
selfblog post publish
```

The publish flow:

1. Discovers all posts in the configured posts directory
2. Filters out drafts (only non-draft posts are published)
3. Records content revisions for each post (see Revision Tracking below)
4. Builds post HTML locally using selfdoc's build pipeline
5. Pushes built HTML and the post-manifest to the assembly repo via the GitHub Git Data API (atomic commit, no clone required)
6. Dispatches a `shared-only` rebuild to regenerate cross-project elements (blog index, RSS feed, sitemap)
7. Optionally archives resolved Markdown to a separate posts repository (if `posts.repo` is configured)

Publishing is separate from a full documentation release. You can publish new posts without releasing a new version of your software -- the assembly workflow rebuilds only the posts subtree and shared elements.

## Revision Tracking

selfdoc tracks content revisions for blog posts via a sidecar file at `.selfdoc/revisions.json`. Revision tracking is automatic -- it happens during `selfblog post publish`.

### How it works

Each post's body content (with frontmatter stripped) is hashed using SHA-256. Whitespace is normalized before hashing so that insignificant formatting changes do not trigger false revisions. A new revision entry is appended only when the content hash changes compared to the most recent revision.

Each revision records:

- `content_hash` -- SHA-256 of the normalized body text
- `timestamp` -- UTC ISO-8601 timestamp of when the revision was recorded
- `summary` -- optional human-readable description of the change

The revisions file structure:

```json
{
  "posts": {
    "my-first-post": {
      "revisions": [
        {
          "content_hash": "a1b2c3...",
          "timestamp": "2026-07-29T12:00:00+00:00",
          "summary": "Initial publish"
        },
        {
          "content_hash": "d4e5f6...",
          "timestamp": "2026-08-05T09:30:00+00:00"
        }
      ]
    }
  }
}
```

The revisions sidecar is published to the assembly alongside the post-manifest, stored as `manifests/{slug}-revisions.json`.

## Post Validation

`selfblog check` runs five post-specific validation checks:

| Code | Description |
| --- | --- |
| `POST001` | Missing `date` field in frontmatter |
| `POST002` | Missing or empty `title` field |
| `POST003` | `date` field is not in `YYYY-MM-DD` format |
| `POST004` | Duplicate slug across posts |
| `POST005` | Slug changed after publication (immutability violation) |

These checks run as part of `selfblog check` for standalone blog projects. For unified docs-site projects, post checks run alongside the full documentation validation suite.

Suppress specific checks with `--ignore`:

```bash
selfblog check --ignore POST003
```

## Integration with the Assembly

Blog posts integrate into the unified multi-project documentation site through the assembly system. The assembly is a GitHub repository that collects built documentation from multiple projects and deploys the combined site.

### How posts reach the unified site

1. **Per-project build**: `selfblog build --target posts` builds post HTML and generates a `post-manifest.json` containing metadata for all non-draft posts.

2. **Assembly push**: `selfblog post publish` pushes built HTML into `site/{slug}/posts/` in the assembly repo and the post-manifest into `manifests/{slug}-posts.json`.

3. **Shared regeneration**: The assembly workflow runs `selfblog assembly integrate`, which grafts the dispatched build into the assembly tree and then regenerates the shared cross-project elements from all per-project manifests and post overlays:
   - A blog index page listing all posts across all projects, sorted newest-first
   - An Atom RSS feed aggregating posts from every project
   - An XML sitemap including all post URLs
   - A navigation JSON file with project and blog links
   - A homepage listing all projects

4. **Post overlay merging**: Post-manifest files (`*-posts.json`) act as overlays. When the shared elements generator finds a post overlay for a project, it replaces that project's posts in the base manifest with the overlay's posts, which is why deleting a post and republishing removes it from the site. A full build does not delete the overlay -- it folds its own posts into it, so a release's posts appear without the overlay's out-of-band posts being lost.

### Post URLs in the unified site

Posts are served at `/{project-slug}/posts/{post-slug}/` in the assembled site. For example, a post with slug `widget-support` in a project with slug `myproject` is available at `/myproject/posts/widget-support/`.

### The canonical blog URL

A Cloudflare Pages project can carry several custom domains, and all of them serve the same site. Left alone that means the blog index is reachable at more than one address, which splits ranking signals between duplicates. The assembly resolves this to one address.

The canonical blog URL is `<topology.docs_base>/blog/`. Everything else redirects to it:

| Request | Result |
| --- | --- |
| `<docs_base>/blog/` | served (canonical) |
| `<topology.legacy_blog_host>/<path>` | `301` to `<docs_base>/blog/<path>` |
| any other host bound to the project, path under `/blog` | `301` to `<docs_base>/blog...` |

Both redirects are single-hop and are implemented in the `_worker.js` that the shared-element generator writes into the site output (`selfblog assembly integrate` during a deploy, `selfblog assembly generate-shared` when run by hand). The worker takes its target from `--canonical-base` (the generated deploy workflow passes `topology.docs_base` to `integrate`) and its retired-subdomain rule from `--legacy-blog-host` (`topology.legacy_blog_host`, omitted when no such subdomain exists). Nothing is hardcoded, and `--canonical-base` has no default -- generate-shared fails without it.

The shared homepage and blog index also carry a `rel="canonical"` link pointing at the canonical host, so a crawler that reaches them through a non-canonical domain still records the canonical address.

Set `topology.posts_base` to the same canonical blog URL. It is a path on the docs site, not a separate host.

### The portfolio canonical

An assembly may serve a hand-authored portfolio page as its site root (`portfolio/index.html` in the assembly repo; `integrate` picks it up when it exists, and `generate-shared` takes it as `--portfolio-file`). That page is the *apex*, not a docs page, so its canonical is **not** `topology.docs_base` -- the same bytes are served on every host bound to the Pages project, and one of them has to be named.

Set `assembly.portfolio_canonical` to that apex URL. The generated deploy workflow passes it as `--portfolio-canonical`, and the shared-element generator splices a `rel="canonical"` link into the portfolio's `<head>` (rewriting one that is already there). There is no default: supplying a portfolio file without `--portfolio-canonical` is a hard error, as is a portfolio document with no `<head>` to splice into.

#### Operator steps (outside selfblog)

Two pieces of this topology live on platform dashboards and are not automated:

1. **Custom domains.** Every hostname the worker redirects *from* must be attached to the assembly's Cloudflare Pages project, otherwise the worker never runs for it and the request does not reach the redirect. Add them under the Pages project's *Custom domains* tab.
2. **Search Console.** Register a **Domain property** for the root domain rather than one URL-prefix property per subdomain. A Domain property covers the canonical host, the retired blog subdomain, and the apex in a single property, so the consolidation is visible as redirects instead of appearing as unrelated sites competing with each other.

### The deploy workflow is a generated artifact

The assembly repo's `.github/workflows/deploy.yml` is generated from the
project's `selfdoc.json`, not hand-written. It is deliberately thin: check
out the assembly, install the toolchain, clone the dispatched project, run
`selfblog assembly integrate`, deploy the result to Cloudflare Pages. Every
decision the deploy makes lives in the command, so it can be tested without
dispatching a real deploy.

`selfblog assembly init` writes that file when the assembly repo is created,
and **`selfblog assembly sync-workflow` rewrites it afterwards**. Run it (or
let the release path run it) whenever selfblog changes: it regenerates the
workflow, compares it against the deployed copy, and pushes only when the
bytes differ. Without it the deployed workflow stays frozen at whatever the
template said the day the repo was created.

The workflow's install line pins **every** tool it installs -- selfdoc,
selfblog and pagefind. Each pin is rewritten by every `sync-workflow` run, so
they track releases rather than capping them, and a deploy can never pick up a
tool whose behavior the deployed workflow does not know about. selfblog is
pinned to the selfblog that generated the file and selfdoc to the selfdoc
installed alongside it; pagefind is a CI-only tool that nothing here installs,
so its pin is PyPI's current release at sync time. `--pin-version`,
`--pin-selfdoc` and `--pin-pagefind` name any of them explicitly.

Before writing anything, `sync-workflow` asks PyPI whether each pinned version
is actually published, and refuses the whole run when one is not. The default
selfblog pin is the *running* selfblog, which in a checkout is an editable
install sitting ahead of the registry -- writing that pin would produce a
workflow whose `pip install` cannot resolve, and the failure would surface on
the assembly repository at the next dispatch instead of here.

### Posts-only vs full builds

The assembly workflow distinguishes between posts-only and full documentation dispatches:

- **Posts-only** (`scope: "posts"`): rebuilds only the posts subtree, preserving the rest of the project's documentation. Uses `selfblog build --target posts`.
- **Full build**: rebuilds all documentation including posts, and folds its posts into the post overlay.
- **Shared-only** (`scope: "shared-only"`): regenerates only cross-project elements (blog index, feed, sitemap) without rebuilding any project's documentation. Used after post publishes, documentation publishes and retirements.

Every scope reconciles membership first: whatever else a dispatch is doing, it makes the tree match `roster.toml` before it makes it match the build.

## Publishing Without a Release

Two commands put content on the live site with no tag and no release. Both build locally, push straight into the assembly repository through the Git Data API, and then dispatch a shared-only rebuild.

```bash
selfblog post publish    # non-draft posts
selfblog docs publish    # the project's documentation
```

`docs publish` builds the docs the same way the deploy does, applies the same deploy-artifact exclusions (`_headers`, `_redirects`, `_worker.js`, `.gz`, `.br`), and pushes the project's subtree, its manifest, its published-file record and its membership entry in one commit. Content travels as bytes, so images and fonts survive intact. Deletions travel with it: a page the project published before and no longer builds is removed in the same commit.

Both commands are consequential -- they make locally-authored writing publicly readable -- so they prompt unless `--approve-consequential` is passed. Neither can create membership: publishing into a slug `roster.toml` does not declare is a hard error naming the block that would have to exist.

### What a build owns

A full build used to replace `site/{slug}/` wholesale, which meant a release destroyed anything published into that subtree since the last one. It prunes to its own output instead.

Every publisher -- the release-time integrate, `docs publish`, `post publish` -- records the paths it produced in `manifests/{slug}-files.json`:

```json
{
  "schema_version": 1,
  "slug": "myproject",
  "owners": {
    "release": ["index.html", "reference/index.html"],
    "docs": ["index.html", "hotfix/index.html"],
    "posts": ["posts/widget-support/index.html"]
  }
}
```

A publisher removes a path only when it produced that path before and does not produce it now, and never when another publisher currently claims it. So:

| Situation | Outcome |
| --- | --- |
| A page the new build dropped | Pruned |
| A page published between releases that the build never produced | Kept |
| A page both a release and a documentation publish produce | Refreshed by whichever ran last |
| A post published out of band, on a release that does not carry it | Kept |

An absent record means nobody has published anything for that project yet, so nothing is removed -- a publisher never deletes what it cannot show it wrote.

## Membership: the Roster

The projects the unified site serves are declared in `roster.toml`, hand-edited and committed in the assembly repository:

```toml
[[project]]
slug = "myproject"
repo = "owner/myproject"

[[project]]
slug = "otherproject"
repo = "owner/otherproject"
```

`slug` and `repo` are both required, unknown keys are a hard error, a duplicate slug is a hard error, and a slug that collides with one of the assembly's own directories (`blog`, `projects`, `pagefind`) is a hard error. A missing file is a hard error too: membership has no empty default, because a deploy that guessed at it would be accumulating membership again.

`projects.json` beside it is **derived** state, rewritten by every deploy: it records what each declared project last deployed (`repo`, `ref`, `version`) and is what `selfblog assembly rebuild` replays. It cannot gain a key on its own -- a dispatch for a slug the roster does not declare is refused, and a slug the roster declares under a different repository is refused too.

Every deploy reconciles the tree to the declaration. A project that is no longer declared loses its site subtree, all of its manifest kinds, its `projects.json` record, and -- because the search index is rebuilt from scratch whenever anything went -- its entries in the index.

### Retiring a project

```bash
selfblog assembly retire --slug oldproject
```

One operation: the `[[project]]` block leaves the roster and, in the same commit, every path the project owns is deleted; the shared-only dispatch that follows regenerates the listing, blog index, feed, sitemap and search index without it. It is consequential -- the only command in either CLI that removes published content -- and retiring a slug the roster does not declare is a hard error naming the ones it does.

## Building Posts Locally

Preview posts locally before publishing:

```bash
# Build posts only (no versioned docs)
selfblog build --target posts

# Include draft posts in the build
selfblog build --target posts --drafts
```

Built HTML is written to the configured output directory (typically `docs/_build/posts/`).
