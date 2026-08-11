---
title: README.md
---
# selfdocumenting

Code-aware documentation site generator. Builds full static sites from Markdown templates and source code. Your code is the documentation -- directives in Markdown pull live content from your codebase at build time.

Supports Python, Go, and TypeScript/JavaScript. Pure Python: two direct runtime dependencies, `strictcli` and `selfdoc-core` (which brings `strictspec` and shares the same `strictcli`). Nothing to compile.

## Install

```
pip install selfdocumenting
```

or via npm (delegates to Python under the hood):

```
npm install -g selfdocumenting
```

Requires Python 3.11+.

The npm package is named `selfdocumenting` (npm blocks `selfdoc` due to name similarity). The CLI command remains `selfdoc`.

## Quick start

```bash
# Initialize in an existing project (auto-detects language)
selfdoc init --base-url https://myproject.pages.dev

# Auto-generate API and CLI reference pages
selfdoc gen

# Edit docs/ pages -- add directives referencing your code

# Build HTML output
selfdoc build

# Validate directives, coverage, and SEO lint
selfdoc check

# Serve locally with live reload
selfdoc serve
```

Your `selfdoc.json` needs `versions` and `locales` -- even for a single-version, single-locale project:

```json
{
  "language": "python",
  "source": ["src/"],
  "base_url": "https://my-project.example.com",
  "versions": [{"version": "1.0.0", "indexed": true}],
  "locales": [{"code": "en", "label": "English", "default": true}]
}
```

## Features

- **Directive syntax** -- embed live API references, schemas, tests, and CLI help directly from source code (`:-:`, `:<:`, `:>:`)
- **Auto-generated pages** -- API reference and CLI docs from source code structure (`selfdoc gen`)
- **Multi-version docs** -- build from git tags, cached builds, version picker UI
- **Localization** -- parallel locale directories, hreflang tags, locale picker, per-locale sitemaps
- **Monorepo support** -- unified site builder combines multiple projects into one docs site
- **Faceted search** -- key=value filter syntax, 7 dimensions, chip UI, auto-injected version default
- **Sandboxed data generation** -- run scripts in bubblewrap isolation (`selfdoc gen-data`)
- **Theming** -- dark mode, accent colors, custom CSS overrides
- **Search engines** -- builtin, Fuse.js, or MiniSearch
- **SEO** -- 15+ lint rules, WCAG contrast validation, JSON-LD structured data, sitemaps
- **Coverage tracking** -- per-symbol documentation coverage with configurable thresholds
- **Syntax highlighting** -- build-time Pygments, code tabs, sortable tables
- **Performance** -- CSS/JS/HTML minification, critical CSS inlining, gzip and Brotli pre-compression
- **Feeds and AI** -- Atom feed, `robots.txt` with AI crawler controls, `llms.txt` / `llms-full.txt`
- **Landing page** -- hero section, tagline, and feature cards
- **Live reload** -- SSE-based dev server
- **Auto-commit** -- generated files committed automatically (prefers safegit)

## Directive syntax

Directives are inline blocks in your Markdown templates. They get replaced with content extracted from your source code at build time.

```
:-: directive-name path="arg"
```

Self-closing directives use `:-:`. Block directives that wrap a body use `:<:` to open, `:>:` to close, with `:=:` and `:::` to delimit sections inside. Directives inside fenced code blocks are ignored.

## Built-in directives

:-: table-directives

Example -- embed the API docs for a Python module:

```markdown
## API Reference

:-: ref path="selfdoc.config"
```

Example -- show a JSON schema as a table:

```markdown
:-: table-schema path="selfdoc.json"
```

## Custom directives

Register custom directives in `selfdoc.json` under the `directives` key. Each entry maps a directive name to a Python script (relative to project root) that exports a `resolve(attrs, config, body)` function returning a Markdown string.

```json
{
  "directives": {
    "changelog": "scripts/changelog_directive.py"
  }
}
```

Script interface:

```python
def resolve(attrs: dict, config: dict, body: list) -> str:
    """Return Markdown string to replace the directive block.

    attrs  -- directive attributes as str->str dict (e.g. {"path": "v1.0.0"})
    config -- the full selfdoc.json config dict
    body   -- body lines from the directive block (empty list for one-liners)
    """
    version = attrs.get("path")
    ...
```

Use in templates:

```markdown
:-: changelog path="v1.0.0"
```

Custom directives take priority over built-in names.

## Configuration

`selfdoc.json` at the project root:

```json
{
  "language": "python",
  "source": ["selfdoc/"],
  "docs": "docs/",
  "output": "docs/_build/",
  "base_url": "https://my-project.example.com",
  "versions": [{"version": "1.0.0", "indexed": true}],
  "locales": [{"code": "en", "label": "English", "default": true}],
  "deploy": {
    "provider": "cloudflare-pages",
    "project": "my-docs"
  },
  "directives": {}
}
```

:-: table-config-schema

`selfdoc init` auto-detects language and source paths from project files (pyproject.toml, go.mod, tsconfig.json, package.json), and takes the site's own address as `--base-url`. A project with no detectable language is initialized as a codeless project: no `source` key, and no code-extraction directive in the starter page.

## Commands

:-: table-commands schema-dir="."

## Blog and multi-project assembly

Blog posts and the unified multi-project documentation assembly live in **selfblog**, a sibling package built on `selfdoc-core`. Install it with `pip install selfblog`, then use `selfblog post ...` to manage posts and `selfblog assembly ...` to manage the assembly.

## Deploy

### Cloudflare Pages

Requires the [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/) installed and authenticated.

```json
{
  "deploy": {
    "provider": "cloudflare-pages",
    "project": "my-docs-project"
  }
}
```

```bash
selfdoc build && selfdoc deploy
```

### GitHub Pages

Pushes the output directory to the `gh-pages` branch via force-push.

```json
{
  "deploy": {
    "provider": "github-pages"
  }
}
```

Enable GitHub Pages in your repo settings (source: `gh-pages` branch).

## Integration with rlsbl

When [rlsbl](https://github.com/smm-h/rlsbl) detects a `selfdoc.json` in the project, it can trigger `selfdoc build` and `selfdoc deploy` as part of the release lifecycle via the `.rlsbl/hooks/post-release.sh` hook.

## Documentation

Full documentation at [selfdoc.smmh.dev](https://selfdoc.smmh.dev).

## License

MIT
