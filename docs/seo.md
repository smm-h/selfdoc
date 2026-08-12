---
title: SEO
description: "How selfdoc generates meta tags, Open Graph cards, JSON-LD structured data, sitemaps, robots.txt, and llms.txt for search engine and AI discoverability."
nav_group: "Guides"
nav_order: 7
---

# SEO

selfdoc generates a full suite of SEO artifacts automatically during every build. You get meta tags, structured data, sitemaps, social cards, and AI discoverability files without writing any HTML or config beyond what you already have.

## What Gets Generated Automatically

Every `selfdoc build` produces a comprehensive set of SEO artifacts for each page without any additional configuration beyond your existing `selfdoc.json`. These cover search engine indexing, social sharing previews, structured data for rich results, and AI discoverability:

- **Meta tags** -- `<title>`, `<meta name="description">`, and `<meta name="robots">` are set from frontmatter or auto-extracted from page content.
- **Canonical URLs** -- `<link rel="canonical">` on every page, derived from `base_url` in your config.
- **Open Graph tags** -- `og:title`, `og:description`, `og:url`, `og:type`, `og:image`, and `og:locale` for rich link previews on social platforms.
- **Twitter card tags** -- `twitter:card`, `twitter:title`, `twitter:description`, and `twitter:site` for Twitter/X previews.
- **JSON-LD structured data** -- `TechArticle` schema on content pages, `BreadcrumbList` on non-index pages, a `WebSite` node on the homepage, and a standalone `Organization` or `Person` entity on the homepage. The `WebSite` node carries no `SearchAction`: that advertised a `?q=` URL pattern which renders the same page for every query, so it published a duplicate-content address per search term. Search here is client-side and has no crawlable result URL.
- **sitemap.xml** -- auto-generated from all indexed HTML pages, with `<lastmod>` timestamps when git dates are available. Multi-locale builds get per-locale sitemaps plus a sitemap index.
- **robots.txt** -- allows all crawlers (including AI bots like GPTBot and ClaudeBot) and points to the sitemap.
- **OG social cards** -- a 1200x630 PNG image generated per page with the project name and page title. Uses predraw + cairosvg when available, otherwise falls back to a basic gradient card.

## What You Can Control

### Frontmatter description

The most impactful thing you can set is `description` in your frontmatter. This single string feeds into four different outputs: `<meta name="description">` for search engines, `og:description` for social cards, `twitter:description` for Twitter/X previews, and the search index summary. Aim for 120-155 characters that accurately describe the page content:

```markdown
---
title: Deployment
description: "Deploy your selfdoc site to Cloudflare Pages or GitHub Pages with a single command."
---
```

If you omit `description`, selfdoc auto-extracts the first sentence from the page body. The `selfdoc check` command will emit an SEO006 warning for missing descriptions and SEO009/SEO010 for descriptions that are too short or too long (aim for 120-155 characters).

### Author metadata

Every page carries structured data naming who wrote it, so `selfdoc.json` must declare an `author`. It is required: a config without one is refused at load, naming the key. `name` and `url` are both mandatory, and `same_as` optionally lists the author's external identities:

```json
{
  "author": {
    "name": "Your Name",
    "url": "https://you.example",
    "same_as": [
      "https://github.com/you",
      "https://fosstodon.org/@you"
    ]
  }
}
```

One `Person` is built from that block and used everywhere an identity is named: the `author` and `publisher` of every page's article, and the standalone entity on the front page. There is no type to choose and no inferred author -- a config with no block used to make the build mint an `Organization` named after the project's directory, publishing a legal entity nobody had declared, which is exactly what the requirement removes.

### Twitter handle

Set `twitter` at the top level of `selfdoc.json` to fill the `twitter:site` meta tag on every page, which Twitter/X uses to attribute the content when someone shares a link. The value must start with `@`. It is a meta tag's value, not part of the author's identity -- an author's profiles belong in `author.same_as`:

```json
{
  "twitter": "@yourhandle"
}
```

### Language tag

Set `lang` in your config for the HTML `lang` attribute and `og:locale` meta tag. This tells search engines and screen readers what language your documentation is written in, improving both search ranking for locale-specific queries and accessibility for assistive technology users:

```json
{
  "lang": "en"
}
```

This accepts any BCP 47 tag (e.g., `en`, `en-US`, `pt-BR`).

## Lint Rules

`selfdoc check` runs 15 SEO lint rules that cover heading structure, meta descriptions, image alt text, contrast ratios, title lengths, content density, and accessibility. Each rule has a code, severity level, and actionable fix suggestion. See the [Check Guide](../check-guide/) for the full list with fix suggestions.

## llms.txt and llms-full.txt

selfdoc generates two files for AI discoverability, placed in the build output root alongside `sitemap.xml` and `robots.txt`. These follow the emerging `llms.txt` convention that AI crawlers and language models use to understand site structure and content without scraping HTML:

- **llms.txt** -- a brief index listing every page with its title and URL. Follows the emerging `llms.txt` convention that AI crawlers use to understand site structure.
- **llms-full.txt** -- the full text of all pages concatenated as plain Markdown. Gives AI systems the complete content in a single request.

Both files are placed in the build output root alongside `sitemap.xml` and `robots.txt`. The `robots.txt` explicitly allows AI crawler user-agents (GPTBot, ClaudeBot, etc.) and points them to the sitemap.

> [!TIP]
> Make sure `base_url` is set in your `selfdoc.json`. Without it, canonical URLs, sitemap entries, and OG tags will be missing or relative, which hurts SEO significantly.

Next: [Code Blocks](../code-blocks/) -->
