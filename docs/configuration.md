---
title: Configuration
description: "Complete reference for selfdoc.json configuration options including project settings, themes, SEO, deployment, and branding."
order: 20
---

# Configuration

selfdoc is configured via a `selfdoc.json` file in your project root. Run `selfdoc init` to generate a starter config interactively, or create one manually.

Three fields are required: `language`, `source`, and `base_url`. Everything else is optional and has sensible defaults.

## Config Reference

The table below lists every field recognized by `selfdoc.json`, including the field type, whether it is required, and a description of what it controls. Required fields have no default and must be provided explicitly.

:-: config-schema

## Common Configurations

### Minimal Python project

```json
{
  "language": "python",
  "source": ["src/"],
  "base_url": "https://myproject.pages.dev"
}
```

### Go project with deployment

```json
{
  "language": "go",
  "source": ["pkg/", "internal/"],
  "base_url": "https://myproject.pages.dev",
  "repo": "https://github.com/user/myproject",
  "branch": "main",
  "deploy": {
    "provider": "cloudflare-pages",
    "project": "myproject"
  }
}
```

### Full-featured project with branding

```json
{
  "language": "python",
  "source": ["mylib/"],
  "base_url": "https://mylib.dev",
  "docs": "docs/",
  "output": "docs/_build/",
  "description": "A toolkit for building great things.",
  "repo": "https://github.com/user/mylib",
  "branch": "main",
  "lang": "en",
  "theme": "minimal",
  "search": "bar",
  "search_engine": "minisearch",
  "min_coverage": 80,
  "author": {
    "name": "Jane Doe",
    "type": "Person",
    "twitter": "@janedoe"
  },
  "deploy": {
    "provider": "cloudflare-pages",
    "project": "mylib"
  },
  "branding": {
    "tagline": "Build great things.",
    "cta_text": "Get Started",
    "cta_link": "getting-started/",
    "features": [
      {
        "title": "Fast",
        "description": "Blazing fast builds with zero dependencies."
      },
      {
        "title": "Flexible",
        "description": "Works with Python, Go, and TypeScript projects."
      }
    ]
  },
  "directives": {
    "changelog": "scripts/changelog-directive.py"
  }
}
```
