---
title: Atom Feeds
description: "How selfdoc generates an Atom feed from your documentation pages, with date handling, page exclusion, and feed size limits."
nav_group: "Guides"
nav_order: 12
---

# Atom Feeds

Every selfdoc site gets a `feed.xml` in the build output. It is a standard Atom feed that RSS readers, news aggregators, and automation tools can subscribe to. No setup required -- it happens automatically during `selfdoc build`.

## How It Works

The build pipeline collects all documentation pages, extracts their titles and first sentences, sorts them by date (most recent first), and writes a valid Atom XML file. Each page becomes one `<entry>` in the feed with a title, link, summary, and updated timestamp.

Every generated HTML page includes a `<link rel="alternate" type="application/atom+xml">` tag in the `<head>`, so browsers and feed readers can auto-discover the feed.

## Date Handling

selfdoc determines page dates from two sources, checked in order:

1. **Frontmatter fields** -- `date` and `updated` in your page's YAML frontmatter. If `updated` is present, it takes precedence. Format: `YYYY-MM-DD`.
2. **File modification time** -- if no frontmatter date is set, selfdoc falls back to the file's last-modified timestamp from git (or the filesystem if git is unavailable).

```markdown
---
title: My Page
date: 2025-03-15
updated: 2025-04-02
---
```

The feed-level `<updated>` element uses the most recent date across all pages.

## Excluding Pages from the Feed

Set `feed: false` in a page's frontmatter to keep it out of the feed. This is useful for pages that are not meaningful as feed entries -- like the glossary, changelog, or auto-generated API reference pages.

```markdown
---
title: Glossary
feed: false
---
```

Pages without this field (or with `feed: true`) are included by default.

## Limiting Feed Size

By default the feed includes all pages. For large documentation sites, you can cap it with the `feed_max_entries` config option in `selfdoc.json`:

```json
{
  "feed_max_entries": 20
}
```

This keeps only the 20 most recently updated pages in the feed. Older entries are dropped. The value must be a positive integer; omit it or set it to `null` for no limit.

## Subscribing

Point any Atom/RSS reader at `https://your-site.example.com/feed.xml`. Most readers auto-detect the feed from any page URL thanks to the `<link>` tag in the HTML head.

Common readers that work:

- **Feedly, Inoreader, NewsBlur** -- paste your site URL, they find the feed automatically
- **Thunderbird, NetNewsWire** -- add the feed URL directly
- **GitHub Actions / webhooks** -- poll `feed.xml` to trigger automations when docs update

> [!TIP]
> Make sure `base_url` is set in your `selfdoc.json`. The feed uses absolute URLs for entry links, and without `base_url` those links will be broken.

Next: [llms.txt](llms-txt/) -->
