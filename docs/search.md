---
title: Search
description: "Configure search engines, UI modes, keyboard shortcuts, filters, and tags in selfdoc to help users find content across your documentation site."
nav_group: "Guides"
nav_order: 6
---

# Search

Every selfdoc site ships with full-text search out of the box. No external services, no API keys -- just a static JSON index that gets built alongside your HTML pages. Users can search from any page via the keyboard shortcut or the UI widget.

## Search Engines

selfdoc offers 3 search engine backends with different tradeoffs between simplicity, fuzzy matching, and relevance scoring. All three use the same JSON index file and the same search dialog UI, so you can switch engines without rebuilding content or changing templates. Set `search_engine` in your `selfdoc.json` to pick one:

```json
{
  "search_engine": "builtin"
}
```

| Engine | Description | Best for |
| ------ | ----------- | -------- |
| `builtin` | Simple scoring based on title and body matches. No dependencies. | Small to medium sites where fuzzy matching is not needed |
| `fuse` | Fuzzy matching via Fuse.js. Tolerates typos and partial matches. | Sites where users might not know exact terminology |
| `minisearch` | Full-text search with TF-IDF scoring via MiniSearch. | Larger sites that need relevance-ranked results |

The default is `builtin`. All three engines use the same `search-index.json` file and the same UI -- switching engines does not require rebuilding your content.

## UI Modes

The search widget has 3 display modes that control how users access search on your site. All modes support the Cmd/Ctrl+K keyboard shortcut and open the same full-screen dialog with real-time results as you type. The only difference is the visible entry point in the topbar. Set the mode with the `search` config key:

```json
{
  "search": "icon"
}
```

- **`icon`** (default) -- a magnifying glass button in the topbar. Click it or press Cmd/Ctrl+K to open the search dialog.
- **`bar`** -- a visible text input in the topbar. Always ready for typing without an extra click.
- **`hidden`** -- no visible widget. Search is still accessible via the Cmd/Ctrl+K keyboard shortcut.

> [!TIP]
> The keyboard shortcut **Cmd+K** (macOS) or **Ctrl+K** (Windows/Linux) works in all three modes. It opens a full-screen search dialog with real-time results as you type.

## How the Index Works

During `selfdoc build`, the build pipeline splits each page into sections based on headings. Each section becomes one entry in `search-index.json`, enabling sub-page search granularity so users land directly on the relevant heading rather than the top of the page. Each entry includes:

- **title** -- the heading text
- **path** -- the URL path including an anchor fragment (e.g., `/getting-started/#installation`)
- **body** -- the first 500 characters of section content (stripped of Markdown formatting)
- **metadata** -- version, locale, nav group, page type, project name, and tags

The search dialog fetches this index on first open and runs queries entirely client-side. No server round-trips, no loading spinners for repeat searches.

## Search Filters

The search box supports structured filters across 7 dimensions using `key=value` syntax, giving users precise control over which pages appear in results. Filters can be combined with free-text queries, negated with a dash prefix, and combined using OR within a single key using the pipe character. Type a filter alongside your search terms to narrow results:

```
build key=value config type=guide
```

### Available filter dimensions

| Key | Values | Description |
| --- | ------ | ----------- |
| `version` | version strings (e.g., `1.0.0`) | Filter by documentation version |
| `locale` | locale codes (e.g., `en`, `pt-BR`) | Filter by language/locale |
| `group` | nav group names (e.g., `Guides`, `API Reference`) | Filter by navigation section |
| `type` | `guide`, `api`, `cli`, `changelog`, `glossary` | Filter by page type |
| `target` | target identifiers | Filter by deploy target |
| `project` | project names | Filter by project (in unified/monorepo builds) |
| `tags` | tag strings | Filter by page tags |

### Filter syntax

- **AND** between different keys: `type=guide group=Guides` returns only guide pages in the Guides nav group.
- **OR** within a key using `|`: `type=guide|api` returns guide or API pages.
- **NOT** with a `-` prefix: `-type=changelog` excludes changelog pages.

### Auto-injected version filter

When your site has versioned documentation, the search dialog automatically injects a `version=<latest>` filter so users see results from the current version by default. To search across all versions, explicitly set `version=` with the desired value, or remove the version chip from the filter bar.

### Filter chips

Active filters appear as removable chips below the search input, providing a visual summary of the current filter state. Click any chip to remove that filter from the query and update results immediately. The version filter chip is visually distinguished from user-added chips since it was auto-injected by the search dialog to scope results to the latest documentation version.

## Adding Tags to Pages

Add a `tags` field to your page frontmatter to make pages discoverable via the `tags=` filter in the search dialog. Tags are indexed into `search-index.json` alongside title, body, and metadata, so users can filter results by topic, category, or any grouping you define. Use arrays for multiple tags per page:

```markdown
---
title: Deployment
description: "Deploy your documentation site to Cloudflare Pages or GitHub Pages."
tags: [deploy, cloudflare, hosting]
---
```

Tags are indexed in `search-index.json` and can be filtered with `tags=deploy` or `tags=deploy|hosting` in the search box.

Next: [SEO](../seo/) -->
