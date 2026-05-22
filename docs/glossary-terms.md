---
title: Glossary
description: "Definitions of key terms used throughout the selfdoc documentation."
nav_group: "Reference"
nav_order: 50
---

# Glossary

:<: list-glossary
:=:
::: **Directive**: A marker in Markdown templates that selfdoc resolves into content at build time. Comes in one-liner (`:-:`) and block (`:<: ... :>:`) forms.
::: **Extractor**: A language-specific module that reads source code and extracts API information for directives. Selfdoc ships with extractors for Python, Go, and TypeScript.
::: **Frontmatter**: YAML-like metadata at the top of a Markdown file between `---` delimiters. Controls title, description, nav group, and other page settings.
::: **Resolver**: The dispatch layer that routes a parsed directive to the correct handler -- content directives, custom directives, or language extractors, in that order.
::: **Tokenizer**: A standalone module that splits Markdown into typed block tokens (headings, code blocks, tables, paragraphs, etc.) used by both the renderer and the lint system.
::: **Theme**: A set of CSS custom properties controlling colors, typography, layout, and component styling. Selfdoc ships with `minimal` and `clean` themes.
::: **Callout**: A content directive that renders a styled admonition box. Types include `callout-note`, `callout-warning`, `callout-tip`, `callout-danger`, and `callout-important`.
::: **Code block**: A fenced block of source code (triple backticks) that gets syntax-highlighted in the rendered output. Consecutive code blocks with different languages become tabbed.
::: **OG card**: An OpenGraph image generated for each page, used as the preview image when a link is shared on social media or messaging platforms.
::: **Sitemap**: An XML file (`sitemap.xml`) listing all page URLs and their last-modified dates, used by search engines for indexing.
::: **Atom feed**: An XML feed (`feed.xml`) that allows RSS readers to subscribe to documentation updates. Pages can opt out with `feed: false` in frontmatter.
::: **Canonical URL**: The definitive URL for a page, set via the `base_url` config field. Used in `<link rel="canonical">` tags and sitemaps to avoid duplicate content in search engines.
::: **JSON-LD**: Structured data embedded in each HTML page as a `<script type="application/ld+json">` block. Provides search engines with machine-readable metadata about the page.
::: **Lint rule**: An SEO or content quality check run by `selfdoc check`. Each rule has a code (e.g., SEO001) and produces warnings or errors with file locations.
::: **Coverage**: The percentage of public symbols in your source code that are referenced by at least one directive. Reported by `selfdoc check` and configurable via `min_coverage`.
::: **Staleness**: When a page's content has changed since the last build but its frontmatter description has not been updated. Detected by comparing content and description hashes.
::: **Build pipeline**: The seven-stage process that transforms Markdown templates into a static HTML site: scan, resolve, tokenize, render, post-process, generate HTML, auxiliary output.
::: **Nav group**: A frontmatter field (`nav_group`) that controls which section of the sidebar navigation a page appears in. Pages with the same nav group are grouped together.
::: **Slug**: The URL-friendly identifier derived from a page's filename. For example, `getting-started.md` becomes the slug `getting-started`, served at `/getting-started/`.
::: **Search index**: A JSON file (`search-index.json`) built from page headings and content, powering the client-side full-text search feature in the rendered site.
::: **Post-processor**: A regex-based transform that runs after block rendering to detect cross-block patterns like consecutive code blocks (code tabs) or ordered lists after tutorial headings (step guides).
::: **Custom directive**: A project-specific directive defined in `selfdoc.json` that points to a Python script implementing `resolve(attrs, config, body)`. Takes priority over built-in directives.
::: **Content directive**: A directive that transforms body content into styled HTML without needing source code access. Includes callouts and `list-glossary`.
:>:
