---
title: selfdoc
description: "Code-aware static site generator that resolves directive blocks in Markdown templates into live content extracted from source code."
---

## Quick Start

Install selfdoc from PyPI and generate your first documentation site in three commands. The `init` command detects your project language automatically from manifest files and scaffolds a starter Markdown template with a directive pointing at your main module:

```bash
pip install selfdoc
selfdoc init
selfdoc build
selfdoc serve
```

## How It Works

Write Markdown templates with directive blocks that reference your source code by module path, function name, or config key. selfdoc resolves these directives at build time by extracting live content directly from your codebase:

```markdown
## API Reference

:-: ref path="mypackage.core"

## CLI Usage

:-: code-help path="mypackage.cli"

## Configuration Schema

:-: code-schema path="mypackage.config" target="Settings"
```

Directives pull docstrings, function signatures, CLI help text, dataclass schemas, and test cases directly from your codebase. When your code changes, your docs update automatically on the next build.

## What You Get

Every selfdoc site includes the following features out of the box, with no additional configuration, no runtime dependencies, and no third-party services required beyond the base install. The generated output is a self-contained static site:

- Full-text search with keyboard navigation
- Dark mode with system preference detection
- Responsive layout for mobile and desktop
- Print stylesheet for clean PDF export
- Atom feed for documentation updates
- XML sitemap for search engine indexing
- Structured data (JSON-LD) for rich snippets
- llms.txt for AI agent discoverability
- Sidebar navigation generated from file structure
- Syntax-highlighted code blocks
