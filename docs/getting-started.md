---
title: Getting Started
description: "Install selfdoc and generate your first documentation site in minutes. Covers installation, project setup, writing directives, and local development."
order: 10
nav_group: "Getting Started"
nav_order: 1
---

# Getting Started

This guide walks you through installing selfdoc, setting up a project, writing your first directive, and previewing your documentation site locally.

## Installation

selfdoc requires **Python 3.11 or later** and has two direct runtime dependencies: `strictcli` (its CLI framework) and `selfdoc-core` (the extraction and rendering engine), which between them add `strictspec` and `tomlkit`. All four are pure Python, so there is nothing to compile -- it works on Linux, macOS, and Windows with no platform-specific setup. You can install it via pip from PyPI for direct use, or via npm as a thin Node wrapper that delegates to the Python package under the hood.

Install via pip:

```bash
pip install selfdoc
```

Or via npm (a thin wrapper that delegates to `python3 -m selfdoc`):

```bash
npm install -g selfdoc
```

Verify the installation:

```bash
selfdoc --version
```

## Initialize a Project

Navigate to the root of an existing codebase that you want to document. The `init` command detects your project language, creates the configuration file, and scaffolds a starter documentation template:

```bash
selfdoc init
```

This does three things:

1. **Detects your project language** from manifest files (`pyproject.toml` for Python, `go.mod` for Go, `tsconfig.json` or `package.json` for TypeScript/JavaScript).
2. **Creates `selfdoc.json`** with sensible defaults -- language, source directories, docs path, and output path.
3. **Creates `docs/index.md`** with a starter template that includes a `ref` directive pointing at your main module.

If language detection fails, you will see an error listing the supported manifest files. Create the appropriate one first, or write `selfdoc.json` manually.

The `init` command also auto-commits the generated files unless you pass `--no-auto-commit`.

## Project Structure

After initialization, your project will have a `selfdoc.json` configuration file at the project root and a `docs/` directory containing a starter Markdown template with a `ref` directive already pointing at your main module. Your existing source code is not modified:

```
your-project/
  selfdoc.json        # Configuration file
  docs/
    index.md          # Starter template
  src/ or lib/        # Your source code (unchanged)
```

### selfdoc.json

The configuration file controls how selfdoc finds your source code, where to look for documentation templates, and where to write the generated HTML output. Only `language` and `source` are required -- everything else has sensible defaults that work for most projects:

```json
{
  "language": "python",
  "source": ["mypackage/"],
  "docs": "docs/",
  "output": "docs/_build/"
}
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `language` | yes | One of `python`, `go`, `typescript`, or `javascript` |
| `source` | yes | List of directories containing source code to extract from |
| `docs` | no | Directory containing Markdown templates (default: `docs/`) |
| `output` | no | Directory for generated HTML output (default: `docs/_build/`) |
| `deploy` | no | Deploy provider config -- see the deployment docs |
| `directives` | no | Map of custom directive names to script paths |

### The docs directory

Every `.md` file in `docs/` is a documentation page that selfdoc will process during the build. Each file should start with YAML frontmatter containing at least a title and description for SEO metadata:

```markdown
---
title: API Reference
description: "Complete API reference for mypackage."
order: 20
---

# API Reference

Your content here...
```

- `title` -- used in the sidebar navigation and HTML `<title>`
- `description` -- used in meta tags for SEO
- `order` -- controls sidebar sort order (lower numbers appear first)

Files are organized into a flat structure. The filename (minus `.md`) becomes the URL slug: `docs/api-reference.md` becomes `/api-reference/`.

## Writing Your First Directive

Directives are the core feature of selfdoc -- inline markers in your Markdown templates that get replaced with content extracted from your source code at build time. They keep your documentation in sync with the implementation automatically.

Open `docs/index.md` (created by `selfdoc init`) and you will see something like:

```markdown
---
title: myproject
description: Documentation for myproject
---

# myproject

Welcome to the myproject documentation.

## API Reference

:-: ref path="myproject"
```

The line `:-: ref path="myproject"` is a self-closing directive. At build time, selfdoc will:

1. Look up the `myproject` module in your source directories.
2. Extract its docstring, public functions, classes, and their signatures.
3. Replace the directive line with formatted Markdown content.

### Adding more directives

selfdoc ships with 5 built-in directives for common documentation patterns, from extracting module-level API references to rendering configuration schemas as tables. Each directive uses a `path` attribute to identify the source file or module, and some accept additional attributes like `target` for specific symbols. Here are examples of each:

**Module reference** -- extract docstrings and public API:

```markdown
:-: ref path="mypackage.core"
```

**Schema table** -- render a dataclass or config structure as a table:

```markdown
:-: table-schema path="mypackage.config" target="Settings"
```

**Test code** -- embed a test function's source:

```markdown
:-: code-test path="tests/test_core.py" target="test_basic_usage"
```

**CLI help** -- extract CLI usage and flags:

```markdown
:-: code-help path="mypackage.cli"
```

**Config table** -- render a JSON or TOML config file as a key-value table:

```markdown
:-: table-config path="selfdoc.json"
```

Directives inside fenced code blocks (triple backticks) are ignored, so you can safely document directive syntax without triggering resolution.

## Building

Once you have written your Markdown templates with directive markers, generate the complete static HTML site with a single command. The build resolves all directives, converts Markdown to HTML, generates navigation and search indexes, and writes everything to the output directory:

```bash
selfdoc build
```

This resolves all directives in your `docs/` templates and writes HTML output to `docs/_build/` (or wherever `output` is configured in `selfdoc.json`).

The build output includes everything needed for a complete static site:

- HTML pages with sidebar navigation
- Syntax-highlighted code blocks
- Full-text search
- Dark mode with system preference detection
- XML sitemap and Atom feed
- Structured data (JSON-LD) for search engines
- Print stylesheet for PDF export

After building, you will see a summary like:

```
Built 5 file(s) to docs/_build/
```

Any SEO warnings or directive errors are printed after the build summary. Errors cause a non-zero exit code; warnings are informational.

## Local Development

Preview your documentation site locally with automatic live reload powered by Server-Sent Events. The development server watches the output directory for file changes and pushes reload notifications to every connected browser tab, so your pages update instantly after each build without manual refreshing or browser extensions.

:<: callout-tip
:=:
::: Run `selfdoc serve` alongside `selfdoc build` for a live preview workflow -- the browser reloads automatically via Server-Sent Events whenever the output changes.
:>:

```bash
selfdoc serve
```

This starts a local HTTP server at `http://localhost:8000/` and watches the output directory for changes. When files change, connected browsers reload automatically via Server-Sent Events (SSE).

To use a different port:

```bash
selfdoc serve --port 3000
```

The typical development workflow is:

1. Run `selfdoc serve` in one terminal.
2. Edit your Markdown templates in `docs/`.
3. Run `selfdoc build` in another terminal.
4. The browser reloads automatically with your changes.

Press `Ctrl+C` to stop the server.

## Checking Your Docs

Validate that all directives resolve correctly, review documentation coverage against your public API surface, and catch SEO issues before publishing. The check command runs three categories of analysis and reports results with file locations and actionable diagnostic codes:

```bash
selfdoc check
```

This runs three checks:

1. **Directive validation** -- attempts to resolve every directive in your templates and reports any that fail (missing modules, invalid paths, etc.).
2. **Coverage analysis** -- for Python projects, counts how many public symbols in your source are referenced by directives versus how many exist. For Go and TypeScript, coverage is reported based on exported symbols.
3. **SEO linting** -- checks frontmatter, heading structure, meta descriptions, and other best practices.

Example output:

```
Directive results:
  docs/index.md:12  ref path="mypackage"        OK
  docs/api.md:8     ref path="mypackage.core"    OK
  docs/api.md:20    table-schema path="..."      OK

Coverage: 15/23 public symbols documented (65%)

SEO: 0 warnings, 0 errors
```

To suppress specific SEO warnings, pass `--ignore` with a comma-separated list of codes:

```bash
selfdoc check --ignore SEO007,SEO008
```

For machine-readable output (useful in CI):

```bash
selfdoc check --format json
```

## Next Steps

Now that you have a working documentation site with live directives, full-text search, and dark mode, explore these topics to learn about advanced configuration, theming, deployment to production hosting, and the full directive reference:

- **[Directives Reference](directives/)** -- complete reference for all built-in directives, block syntax, and custom directives.
- **[Configuration](selfdoc-config/)** -- all `selfdoc.json` options including deploy providers, coverage thresholds, and lint suppression.
- **[CLI Reference](cli-index/)** -- detailed documentation for every CLI command and flag.
