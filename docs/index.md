---
title: selfdoc
description: "Build documentation sites from Markdown and source code. Directives pull live content from your codebase so docs stay in sync automatically."
order: 0
feed: false
---

selfdoc builds documentation websites from your Markdown files and source code. Write docs in Markdown, reference your actual code with directives, and selfdoc keeps everything in sync -- when your code changes, your docs update automatically.

## How it works

### 1. Write Markdown with directives

Create a Markdown file in your `docs/` folder. Use directive markers to reference modules, functions, classes, schemas, and CLI definitions in your source code. selfdoc resolves each directive at build time, extracting live content so your documentation always matches the actual implementation:

```markdown
# API Reference

:-: ref path="mypackage.core"
```

That `:-: ref` line tells selfdoc to grab the docstrings and signatures from `mypackage.core` and drop them right into your page. No copy-pasting, no manual updates.

### 2. Configure with selfdoc.json

A minimal config file tells selfdoc your project's language, which directories contain source code, where your docs templates live, and where to write the built output. selfdoc infers everything else -- navigation, theming, search, SEO metadata, and deploy settings all have sensible defaults:

```json
{
  "language": "python",
  "source": ["mypackage/"],
  "docs": "docs/",
  "output": "docs/_build/"
}
```

selfdoc figures out the rest. It detects your project structure, builds navigation from your file layout, and applies a clean default theme.

### 3. Build and deploy

Run `selfdoc build` and you get a full static site -- HTML, CSS, search index, sitemap, the works. Serve it locally with `selfdoc serve`, or deploy anywhere that hosts static files.

```bash
pip install selfdoc
selfdoc init
selfdoc build
```

## Before and after

Here is what a typical docs template looks like before the build, and what selfdoc turns it into after directive resolution. The Markdown file stays clean and readable while the rendered output contains the full extracted content from your source code.

Your Markdown file:

```markdown
# User Guide

Welcome to mypackage. Here is the full API:

:-: ref path="mypackage.core"

And the CLI usage:

:-: code-help path="mypackage.cli"
```

The rendered output: a styled HTML page with your welcome text, followed by a complete API reference (every public function, class, and docstring from `mypackage.core`), then a formatted CLI help section showing every command and flag from `mypackage.cli`. All extracted live from your source code.

:<: callout-tip
:=:
::: You never edit the generated output. Change your code, rebuild, and the docs reflect reality.
:>:

## Features

selfdoc ships with everything you need to build, check, and deploy a documentation site from a single tool with a handful of pure-Python dependencies. Here are the core capabilities that work out of the box.

:<: callout-note
:=:
::: All of these work out of the box with zero configuration beyond the basic selfdoc.json.
:>:

- **Code-aware directives** -- Embed live API references, schemas, tests, and CLI help directly from source code. Content stays in sync automatically.
- **Multi-language support** -- 3 language extractors (Python, Go, TypeScript) handle all 20 built-in directive types out of the box.
- **Zero dependencies** -- Pure Python with one lightweight dependency. No JavaScript frameworks, no build tools, no configuration overhead.
- **SEO and AI optimized** -- Structured data, meta tags, sitemaps, llms.txt, Atom feeds, and 50+ SEO best practices built into every generated page.
- **Themeable and accessible** -- Two built-in themes with dark mode, WCAG AA contrast, print stylesheets, and full keyboard navigation.

## Get started

Ready to try it? Head over to the [Getting Started](getting-started/) guide for installation, project initialization, and your first documentation build. The guide walks you through creating a `selfdoc.json`, writing your first template with directives, and previewing the output locally with live reload.
