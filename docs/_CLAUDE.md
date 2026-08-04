---
title: CLAUDE.md
---
# selfdocumenting

Code-aware static site generator. Builds full documentation sites from Markdown templates and source code, with directive-based content extraction, auto-generated API/CLI reference pages, multi-version support, localization, monorepo unified sites, faceted search, theming, SEO, and deploy to Cloudflare Pages or GitHub Pages. Supports Python, Go, and TypeScript/JavaScript.

## Conventions

- Pure Python. The `selfdoc` package depends on `strictcli` and `selfdoc-core`; `selfdoc-core` in turn depends on `strictspec` and `strictcli` (the effects chokepoint in `selfdoc_core/effects.py` mints on strictcli's `ctx.effects` handle). Nothing else is required at runtime.
- Build system: hatchling
- Development: `uv` for all Python tooling (`uv sync`, `uv run`, `uv add`)
- Local development install: `uv pip install -e .`
- npm package is a thin Node wrapper (`bin/cli.js`) that delegates to `python3 -m selfdoc`
- JS files live in `selfdoc/js/`, loaded at build time via `importlib.resources` (never inline JS in Python)
- File writes to shared state use atomic write (write to tmp, then `os.replace`)
- External calls (subprocess, network) must have timeouts

## Key concepts

### Always-prefixed URLs

Every page outputs to `/<locale>/<version>/page/`. The config MUST have `versions` and `locales` arrays -- these are required. Even a single-version, single-locale project needs them:

```json
{
  "versions": [{"version": "0.8.1", "indexed": true}],
  "locales": [{"code": "en", "label": "English", "default": true}]
}
```

### Multi-version builds

Builds documentation from git tags. Tagged versions are checked out and built from cache (`.selfdoc/cache/`), while the latest version builds from the working tree. Version/locale picker UI is auto-generated.

### Localization

Parallel `docs/<locale>/` directories with per-locale templates. Generates hreflang tags, per-locale sitemaps, and locale picker UI.

### Monorepo unified sites

`selfdoc/unified.py` orchestrates building a single documentation site from multiple constituent projects plus a docs-site's own cross-cutting content. Configured via the `unified` section in `selfdoc.json`. The unified project is effectively the (N+1)th docs-site project.

### Search filters

Faceted search with key=value syntax across 7 dimensions. Chip-based filter UI with auto-injected version default. Pages declare search metadata via frontmatter tags using bracket syntax: `tags: [a, b, c]`.

### Directives

6 marker types for embedding code-extracted content in Markdown templates:
- `:-:` -- self-closing directive
- `:<:` -- block open
- `:@:` -- block attribute
- `:=:` -- section separator
- `:::` -- section content
- `:>:` -- block close

### gen_data

Sandboxed script execution via bubblewrap (bwrap). Runs scripts in isolated environments to generate data files used by the build.

### Root file templates

`docs/_CLAUDE.md` and `docs/_README.md` are templates that generate the project root `CLAUDE.md` and `README.md` via `selfdoc gen`. They support directives like any other template.

## Release workflow

This project uses [rlsbl](https://github.com/smm-h/rlsbl) for release orchestration.

- `selfdoc check` runs during release (validates directives, coverage, lint)
- Deploy to Cloudflare Pages via post-release hook
- CI handles PyPI and npm publishing automatically
- Never publish manually -- always use `rlsbl release`
- Requires NPM_TOKEN secret on GitHub (Settings > Secrets > Actions)

## Testing

```bash
uv run pytest
```

1270+ tests in `tests/` covering config loading, directive parsing, the build pipeline, language-specific extractors (Python, Go, TypeScript), check command, gen command, gendata, unified builder, context dataclasses, search, pickers, filters, localization, and multi-version builds.

## Important config fields

- `versions` (required): array of `{version, indexed}` objects -- controls multi-version builds
- `locales` (required): array of `{code, label, default}` objects -- controls localization
- `unified`: optional, for monorepo docs-site projects -- lists constituent projects
- `gen_data`: optional sandboxed script execution config
- `root_files`: templates that generate root-level files (e.g. CLAUDE.md, README.md)
- `deploy`: Cloudflare Pages or GitHub Pages provider config

## Architecture

:-: list-modules path="selfdoc/"
