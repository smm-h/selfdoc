---
title: Blog Posts
description: "How to create, manage, and publish blog posts in selfdoc, including frontmatter format, release-generated posts, revision tracking, and integration with the unified documentation assembly."
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
    "slug": "myproject",
    "assembly": "owner/assembly-repo"
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

3. **Shared regeneration**: The assembly workflow runs `selfblog assembly generate-shared`, which reads all per-project manifests and post overlays to produce:
   - A blog index page listing all posts across all projects, sorted newest-first
   - An Atom RSS feed aggregating posts from every project
   - An XML sitemap including all post URLs
   - A navigation JSON file with project and blog links
   - A homepage listing all projects

4. **Post overlay merging**: Post-manifest files (`*-posts.json`) act as overlays. When the shared elements generator finds a post overlay for a project, it replaces that project's posts in the base manifest with the overlay's posts. This lets posts be updated independently of full documentation rebuilds.

### Post URLs in the unified site

Posts are served at `/{project-slug}/posts/{post-slug}/` in the assembled site. For example, a post with slug `widget-support` in a project with slug `myproject` is available at `/myproject/posts/widget-support/`.

### Posts-only vs full builds

The assembly workflow distinguishes between posts-only and full documentation dispatches:

- **Posts-only** (`scope: "posts"`): rebuilds only the posts subtree, preserving the rest of the project's documentation. Uses `selfblog build --target posts`.
- **Full build**: rebuilds all documentation including posts. Removes any post overlay since the full manifest replaces it.
- **Shared-only** (`scope: "shared-only"`): regenerates only cross-project elements (blog index, feed, sitemap) without rebuilding any project's documentation. Used after post publishes.

## Building Posts Locally

Preview posts locally before publishing:

```bash
# Build posts only (no versioned docs)
selfblog build --target posts

# Include draft posts in the build
selfblog build --target posts --drafts
```

Built HTML is written to the configured output directory (typically `docs/_build/posts/`).
