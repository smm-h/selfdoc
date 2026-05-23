---
title: llms.txt
description: "How selfdoc generates llms.txt and llms-full.txt files for AI discoverability, plus robots.txt rules that allow AI crawlers like GPTBot and ClaudeBot."
nav_group: "Guides"
nav_order: 13
---

# llms.txt

selfdoc automatically generates 2 files that make your documentation accessible to AI assistants and large language models. No configuration needed -- they appear in your build output alongside `sitemap.xml` and `robots.txt`.

## What Is llms.txt?

The `llms.txt` standard is a convention for making website content machine-readable for AI agents. Think of it as `robots.txt` for AI discovery -- instead of telling crawlers what they *can't* access, it tells them what's *worth* reading.

When an AI assistant encounters your site, it can fetch `/llms.txt` to understand what documentation is available and where to find it, without scraping every page.

## The Two Files

### llms.txt

A brief index of your entire documentation site, designed for AI agents that need to understand what content is available before deciding which pages to read in full. Each page gets one line with its title, absolute URL, and first sentence as a summary:

```
# MyProject Documentation

> Code-aware documentation site generator.

## Pages

- [Getting Started](https://myproject.pages.dev/getting-started/): Install selfdoc and create your first docs site.
- [Configuration](https://myproject.pages.dev/configuration/): All available selfdoc.json options.
```

This is lightweight enough for an AI to read in one request and decide which pages are relevant.

### llms-full.txt

The complete text of every documentation page concatenated into a single plain Markdown file with page separators. This gives AI systems the full content of your documentation in one HTTP request, useful for context-heavy tasks like answering detailed questions. Each section starts with the page title and a path comment:

```markdown
## Getting Started
<!-- path: getting-started.md -->

Install selfdoc and create your first docs site...

---

## Configuration
<!-- path: configuration.md -->

All available selfdoc.json options...
```

This gives AI systems the full content in a single fetch -- useful for context-heavy tasks like answering questions about your project or generating code that follows your conventions.

## AI Crawler Access

selfdoc's generated `robots.txt` explicitly allows 6 AI crawlers by listing each known AI user agent with `Allow: /`. This opt-in approach ensures that AI assistants and search-augmented language models can freely index your documentation, read the sitemap, and fetch the `llms.txt` files without being blocked:

- **GPTBot** and **ChatGPT-User** (OpenAI)
- **ClaudeBot** (Anthropic)
- **PerplexityBot** (Perplexity)
- **Google-Extended** and **Googlebot** (Google)
- **OAI-SearchBot** (OpenAI search)

This means AI assistants can freely crawl your docs, read the sitemap, and fetch `llms.txt` or `llms-full.txt` without being blocked.

## Why It Matters

If your project has public documentation, AI assistants are probably already trying to read it. Without `llms.txt`, they have to scrape HTML, parse navigation, and guess at structure. With it, they get a clean summary and full text in standard formats.

This is especially useful for:

- **AI coding assistants** that need to understand your API or CLI
- **Search-augmented LLMs** that retrieve docs to answer user questions
- **Chatbots** trained or grounded on your documentation

> [!TIP]
> Both files use `base_url` from your `selfdoc.json` for absolute URLs. Without `base_url`, links in `llms.txt` will be relative and may not resolve correctly for external AI agents.

Next: [Glossary Guide](glossary-guide/) -->
