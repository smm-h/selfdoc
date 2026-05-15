# selfdoc

Code-aware static site generator that resolves `:::directive` blocks in Markdown templates into content extracted from source code. Supports Python, Go, and TypeScript/JavaScript.

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

- **Directive parser** (`selfdoc/directives.py`): state machine that tracks fenced code blocks and `:::name arg` / `:::` pairs. Two entry points: `parse_directives` (extract) and `resolve_directives` (replace in-place with resolver output).
- **Resolver** (`selfdoc/resolver.py`): factory that returns a `(name, arg, body) -> str` callable. Custom directives (from `selfdoc.json`) are checked first; otherwise dispatches to the language-specific extractor.
- **Extractors** (`selfdoc/extractors/`): per-language modules (`python.py`, `go.py`, `typescript.py`). Python uses `ast`; Go and TypeScript use regex-based parsing. Each extractor handles all 5 built-in directives (module, schema, test, cli, config).
- **Build** (`selfdoc/build.py`): scans `docs/` for `.md` templates, runs `resolve_directives` on each, converts to HTML, writes to output directory.
- **HTML** (`selfdoc/html.py`): built-in Markdown-to-HTML converter (no dependencies). Uses a tokenize -> render -> post-process pipeline: the tokenizer splits Markdown into block tokens, each token is rendered to HTML, then post-processing passes apply code tabs, step guides, API entry cards, and definitions. Produces a static site with sidebar navigation and responsive CSS.
- **Tokenizer** (`selfdoc/tokenizer.py`): standalone Markdown block tokenizer with zero selfdoc imports, 10 token types (CodeBlock, Heading, Table, UnorderedList, OrderedList, Blockquote, DefinitionList, ThematicBreak, BlankLine, Paragraph). Used by both the HTML converter and the lint/check system.
- **Config** (`selfdoc/config.py`): loads and validates `selfdoc.json`. Valid languages: python, go, typescript, javascript. Valid deploy providers: cloudflare-pages, github-pages.
- **Deploy** (`selfdoc/deploy.py`): Cloudflare Pages (via wrangler CLI) and GitHub Pages (force-push to gh-pages branch).
- **Check** (`selfdoc/check.py`): validates all directives resolve without error; computes documentation coverage (language-agnostic via extractor protocol: public/exported symbol count vs. documented symbols). Includes lint diagnostics (SEO, contrast, etc.).
- **Auto-commit** (`selfdoc/git.py`): centralized git commit helper with safegit preference, used by CLI commands (build, init, gen, gen-data) to auto-commit generated files.
- **CLI** (`selfdoc/cli.py`): uses `strictcli`, subcommands: init, build, serve, deploy, check, gen, gen-data. Serve uses SSE-based live reload with mtime polling.
