---
title: SEO
description: "How selfdoc generates meta tags, Open Graph cards, JSON-LD structured data, sitemaps, robots.txt, and llms.txt for search engine and AI discoverability."
nav_group: "Guides"
nav_order: 7
---

# SEO

selfdoc generates a full suite of SEO artifacts automatically during every build. You get meta tags, structured data, sitemaps, social cards, and AI discoverability files without writing any HTML or config beyond what you already have.

## What Gets Generated Automatically

Every `selfdoc build` produces the following for each page:

- **Meta tags** -- `<title>`, `<meta name="description">`, and `<meta name="robots">` are set from frontmatter or auto-extracted from page content.
- **Canonical URLs** -- `<link rel="canonical">` on every page, derived from `base_url` in your config.
- **Open Graph tags** -- `og:title`, `og:description`, `og:url`, `og:type`, `og:image`, and `og:locale` for rich link previews on social platforms.
- **Twitter card tags** -- `twitter:card`, `twitter:title`, `twitter:description`, and `twitter:site` for Twitter/X previews.
- **JSON-LD structured data** -- `TechArticle` schema on content pages, `BreadcrumbList` on non-index pages, `WebSite` with `SearchAction` on the homepage, and a standalone `Organization` or `Person` entity on the homepage.
- **sitemap.xml** -- auto-generated from all indexed HTML pages, with `<lastmod>` timestamps when git dates are available. Multi-locale builds get per-locale sitemaps plus a sitemap index.
- **robots.txt** -- allows all crawlers (including AI bots like GPTBot and ClaudeBot) and points to the sitemap.
- **OG social cards** -- a 1200x630 PNG image generated per page with the project name and page title. Uses predraw + cairosvg when available, otherwise falls back to a basic gradient card.

## What You Can Control

### Frontmatter description

The most impactful thing you can set is `description` in your frontmatter. It feeds into `<meta name="description">`, `og:description`, and `twitter:description`:

```markdown
---
title: Deployment
description: "Deploy your selfdoc site to Cloudflare Pages or GitHub Pages with a single command."
---
```

If you omit `description`, selfdoc auto-extracts the first sentence from the page body. The `selfdoc check` command will emit an SEO006 warning for missing descriptions and SEO009/SEO010 for descriptions that are too short or too long (aim for 120-155 characters).

### Author metadata

Set the `author` object in `selfdoc.json` to populate the `TechArticle` author field and the homepage Organization/Person entity:

```json
{
  "author": {
    "name": "Your Name",
    "type": "Person",
    "twitter": "@yourhandle"
  }
}
```

If `type` is `"Person"`, the homepage JSON-LD emits a `Person` entity. Otherwise it defaults to `Organization`. The `twitter` field (starting with `@`) sets the `twitter:site` meta tag.

### Top-level twitter config

Alternatively, set `twitter` at the top level of `selfdoc.json`:

```json
{
  "twitter": "@yourhandle"
}
```

If both `author.twitter` and `twitter` are set, `author.twitter` takes precedence.

### Language tag

Set `lang` in your config for the HTML `lang` attribute and `og:locale`:

```json
{
  "lang": "en"
}
```

This accepts any BCP 47 tag (e.g., `en`, `en-US`, `pt-BR`).

## Lint Rules

`selfdoc check` runs 15 SEO lint rules. See the [Check Guide](check-guide/) for the full list with fix suggestions.

## llms.txt and llms-full.txt

selfdoc generates two files for AI discoverability:

- **llms.txt** -- a brief index listing every page with its title and URL. Follows the emerging `llms.txt` convention that AI crawlers use to understand site structure.
- **llms-full.txt** -- the full text of all pages concatenated as plain Markdown. Gives AI systems the complete content in a single request.

Both files are placed in the build output root alongside `sitemap.xml` and `robots.txt`. The `robots.txt` explicitly allows AI crawler user-agents (GPTBot, ClaudeBot, etc.) and points them to the sitemap.

> [!TIP]
> Make sure `base_url` is set in your `selfdoc.json`. Without it, canonical URLs, sitemap entries, and OG tags will be missing or relative, which hurts SEO significantly.

Next: [Code Blocks](code-blocks/) -->
