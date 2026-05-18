# selfdoc

Code-aware static site generator that resolves directive blocks in Markdown templates into live content extracted from your source code.

Supports Python, Go, and TypeScript/JavaScript. Zero runtime dependencies -- pure Python stdlib.

## Install

```
pip install selfdoc
```

or via npm (delegates to Python under the hood):

```
npm install -g selfdoc
```

Requires Python 3.11+.

## Quick start

```bash
# Initialize in an existing project (auto-detects language)
selfdoc init

# Edit docs/index.md -- add directives referencing your code
# (see Directive syntax below)

# Build HTML output
selfdoc build

# Serve locally with live reload
selfdoc serve
```

## Directive syntax

Directives are inline blocks in your Markdown templates. They get replaced with content extracted from your source code at build time.

```
:-: directive-name path="arg"
```

Self-closing directives use `:-:`. Block directives that wrap a body use `:<:` to open, `:>:` to close, with `:=:` and `:::` to delimit sections inside. Directives inside fenced code blocks are ignored.

## Built-in directives

| Directive | Attributes | Description |
| --------- | ---------- | ----------- |
| `ref` | `path` | Extract module/package docstrings, exported functions, classes |
| `table-schema` | `path`, `target` | Extract dataclass fields or JSON keys as a table |
| `code-test` | `path`, `target` | Embed test source code (whole file or specific function/class) |
| `code-help` | `path` | Extract CLI help/usage text and flag definitions |
| `table-config` | `path` | Render JSON/TOML config files as key-value tables |

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

| Field | Required | Default | Description |
| ----- | -------- | ------- | ----------- |
| `language` | yes | -- | `python`, `go`, `typescript`, or `javascript` |
| `source` | yes | -- | List of source directories to scan |
| `docs` | no | `docs/` | Directory containing Markdown templates |
| `output` | no | `docs/_build/` | Directory for generated HTML output |
| `deploy` | no | -- | Deploy provider config (see Deploy below) |
| `directives` | no | `{}` | Custom directive script mappings |

`selfdoc init` auto-detects language and source paths from project files (pyproject.toml, go.mod, tsconfig.json, package.json).

## Commands

| Command | Description |
| ------- | ----------- |
| `selfdoc init` | Initialize selfdoc in the current project (creates selfdoc.json + starter template) |
| `selfdoc build` | Resolve directives and generate HTML to the output directory |
| `selfdoc serve [--port PORT]` | Serve built docs locally with SSE-based live reload (default port 8000) |
| `selfdoc deploy` | Deploy docs to the configured provider |
| `selfdoc check` | Validate all directives resolve successfully; report documentation coverage |

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
