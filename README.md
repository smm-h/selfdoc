# selfdocumenting

Code-aware documentation site generator. Builds full static sites from Markdown templates and source code, with directive-based content extraction, auto-generated API/CLI reference pages, theming, search, SEO, and deploy to Cloudflare Pages or GitHub Pages.

Supports Python, Go, and TypeScript/JavaScript. One runtime dependency (strictcli). Pure Python.

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
selfdoc init

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

## Features

- Attribute-based directive syntax (`:-:`, `:<:`, `:>:`) for embedding code-extracted content
- Auto-generated API reference and CLI docs from source code structure (`selfdoc gen`)
- Sandboxed data generation scripts (`selfdoc gen-data`)
- Theming with dark mode, accent colors, and custom CSS overrides
- Pluggable search (builtin, Fuse.js, or MiniSearch)
- 15+ SEO lint rules, WCAG contrast validation, JSON-LD structured data
- Per-symbol documentation coverage tracking with configurable thresholds
- Build-time Pygments syntax highlighting, code tabs, sortable tables
- CSS/JS/HTML minification, critical CSS inlining, gzip and Brotli pre-compression
- Atom feed, `robots.txt` with AI crawler controls, `llms.txt` / `llms-full.txt`
- Landing page with hero section, tagline, and feature cards
- SSE-based live reload dev server
- Auto-commit of generated files (prefers safegit)

## Directive syntax

Directives are inline blocks in your Markdown templates. They get replaced with content extracted from your source code at build time.

```
:-: directive-name path="arg"
```

Self-closing directives use `:-:`. Block directives that wrap a body use `:<:` to open, `:>:` to close, with `:=:` and `:::` to delimit sections inside. Directives inside fenced code blocks are ignored.

## Built-in directives

| Directive | Description |
| --------- | ----------- |
| `ref` | Extract module/package docstrings, exported functions, classes |
| `table-schema` | Extract dataclass fields or JSON keys as a table |
| `code-test` | Embed test source code (whole file or specific function/class) |
| `code-help` | Extract CLI help/usage text and flag definitions |
| `table-config` | Render JSON/TOML config files as key-value tables |
| `callout-note` | Info callout |
| `callout-tip` | Tip callout |
| `callout-warning` | Warning callout |
| `callout-danger` | Danger callout |
| `callout-important` | Important callout |
| `list-glossary` | Glossary definition list |
| `prose-desc` | Prose description block |
| `list-tree` | Tree-structured list |
| `table-dep` | Dependency table |
| `list-features` | Feature list |

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
  "deploy": {
    "provider": "cloudflare-pages",
    "project": "my-docs"
  },
  "directives": {}
}
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `language` | yes | `python`, `go`, `typescript`, or `javascript` |
| `source` | yes | List of source directories to scan |
| `base_url` | yes | Base URL of the deployed site |
| `docs` | no | Markdown template directory (default: `docs/`) |
| `output` | no | HTML output directory (default: `docs/_build/`) |
| `deploy` | no | Deploy provider config |
| `directives` | no | Custom directive script mappings |
| `theme` | no | Theme name and accent color |
| `search_engine` | no | `builtin`, `fuse`, or `minisearch` |
| `feedback` | no | Feedback widget config (webhook, analytics) |
| `branding` | no | Landing page hero, tagline, CTA |
| `auto_detect` | no | Toggle step guides, API entries, etc. |
| `gen` | no | Page generation config (exclusion patterns) |
| `gen_data` | no | Data generation config |
| `min_coverage` | no | Minimum documentation coverage threshold |
| `lint_ignore` | no | SEO lint rules to suppress project-wide |
| `lang` | no | BCP 47 language tag |
| `author` | no | Author name for metadata |
| `repo` | no | Repository URL for edit links |

`selfdoc init` auto-detects language and source paths from project files (pyproject.toml, go.mod, tsconfig.json, package.json).

## Commands

| Command | Description |
| ------- | ----------- |
| `selfdoc init` | Initialize selfdoc in the current project |
| `selfdoc build` | Resolve directives and generate HTML |
| `selfdoc serve` | Serve locally with SSE-based live reload |
| `selfdoc deploy` | Deploy to the configured provider |
| `selfdoc check` | Validate directives, report coverage, run SEO lint |
| `selfdoc gen` | Auto-generate API and CLI reference pages from source code |
| `selfdoc gen-data` | Run sandboxed scripts to produce data files for docs |

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

## License

MIT
