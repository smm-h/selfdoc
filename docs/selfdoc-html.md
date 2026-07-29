---
title: selfdoc.html
description: "Convert Markdown files to static HTML with a built-in minimal converter -- handles headings, code blocks, tables, and inline formatting."
nav_group: "API Reference"
nav_order: 24
---

# selfdoc.html

The html module is selfdoc's built-in Markdown-to-HTML converter with zero required runtime dependencies. It handles headings (with auto-generated slug anchors and table-of-contents extraction), fenced code blocks (with optional Pygments syntax highlighting, language icons, line numbers, annotations, and run buttons), tables, ordered and unordered lists, definition lists, blockquotes, GitHub-flavored admonitions, inline formatting (bold, italic, strikethrough, code, links, images), and cross-page glossary term linking. The converter also supports higher-level structural patterns like code tabs, step guides, API entry wrapping, and diff-highlighted code blocks.

The main entry points are `generate_html()`, which takes a dict of Markdown files and produces a dict of complete HTML pages (with navigation, SEO tags, search dialog, version/locale pickers, breadcrumbs, and page footer), and `md_to_html()`, which converts a single Markdown string to an HTML fragment. The module also provides `generate_404_page()` for custom error pages, `_build_nav()` for sidebar navigation tree construction from frontmatter ordering, and `_render_seo_tags()` for structured data and OpenGraph metadata. It is called by `selfdoc.build` during site generation and by `selfdoc.check` for lint validation.

:-: ref path="selfdoc.html" lang="python"
