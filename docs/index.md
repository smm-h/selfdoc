---
title: selfdoc
description: "Code-aware static site generator that resolves directive blocks in Markdown templates into live content extracted from source code."
---

## Quick Start

Install selfdoc and generate your first documentation site in three commands:

```bash
pip install selfdoc
selfdoc init
selfdoc build
selfdoc serve
```

## How It Works

Write Markdown templates with directive blocks that reference your source code. selfdoc resolves them at build time into live content:

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

Every selfdoc site includes — with zero configuration:

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
