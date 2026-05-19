---
title: CLAUDE.md
---
# selfdocumenting

Code-aware documentation site generator. Builds full static sites from Markdown templates and source code, with directive-based content extraction, auto-generated API/CLI reference pages, theming, search, SEO, and deploy to Cloudflare Pages or GitHub Pages. Supports Python, Go, and TypeScript/JavaScript.

## Conventions

- Pure Python, one runtime dependency (`strictcli>=0.2.0`)
- Build system: hatchling
- Development: `uv` for all Python tooling (`uv sync`, `uv run`, `uv add`)
- Local development install: `uv pip install -e .`
- npm package is a thin Node wrapper (`bin/cli.js`) that delegates to `python3 -m selfdoc`
- File writes to shared state use atomic write (write to tmp, then `os.replace`)
- External calls (subprocess, network) must have timeouts

## Release workflow

This project uses [rlsbl](https://github.com/smm-h/rlsbl) for release orchestration.

- Update CHANGELOG.md with a `## X.Y.Z` entry describing changes
- Run `rlsbl release [patch|minor|major]` to bump version and create a GitHub Release
- CI handles publishing automatically via the publish workflow
- Never publish manually -- always use `rlsbl release`
- Requires NPM_TOKEN secret on GitHub (Settings > Secrets > Actions)
- Use `rlsbl release --dry-run` to preview a release without making changes

## Testing

```bash
uv run pytest
```

Tests live in `tests/` and cover config loading, directive parsing, the build pipeline, and language-specific extractors (Python, Go).

## Architecture

:-: list-modules path="selfdoc/"
