---
title: Architecture
description: "Internal architecture of selfdoc: the Markdown tokenizer, rendering pipeline, language extractors, directive resolver, and build system."
order: 60
---

# Architecture

This page documents the internal design of selfdoc for contributors and anyone interested in extending or debugging the system.

## Overview

The build pipeline transforms Markdown templates into a static HTML site through a sequence of well-separated stages:

1. **Scan** -- walk `docs/` for `.md` files, parse frontmatter
2. **Resolve directives** -- replace directive markers with generated Markdown content (from source code or content transforms)
3. **Tokenize** -- split the resolved Markdown into typed block tokens
4. **Render** -- dispatch each token to a block-level HTML renderer
5. **Post-process** -- apply heuristic transforms (code tabs, step guides, API entries, definitions, LCP promotion)
6. **Generate HTML** -- wrap rendered content in a full page shell with navigation, metadata, and styles
7. **Auxiliary output** -- generate sitemap, Atom feed, search index, OG images, `llms.txt`, and compressed companions

Each stage is a pure function of its input, making the system easy to test and reason about. There is no shared mutable state between stages.

## Tokenizer

**Module:** `selfdoc/tokenizer.py`

The tokenizer is a standalone, zero-dependency module that splits Markdown source into a flat list of typed block tokens. It has no imports from selfdoc -- it is designed for reuse outside the project.

### Token types

The tokenizer produces 11 token types, each a `@dataclass` with `start` and `end` line numbers (1-based):

| Token | Represents |
|-------|-----------|
| `Heading` | ATX heading (`#` through `######`) with level and text |
| `CodeBlock` | Fenced code block with language, content lines, and annotations |
| `Table` | Pipe-delimited table rows |
| `UnorderedList` | Items starting with `-` or `*` |
| `OrderedList` | Items starting with `1.`, `2.`, etc. |
| `Blockquote` | `>` prefixed lines, with optional admonition type |
| `DefinitionList` | Term/definition pairs (DL/DT/DD) |
| `ThematicBreak` | `---`, `***`, or `___` |
| `BlankLine` | Empty separator lines |
| `Directive` | The legacy `:::name arg` / `:::` syntax (tokenizer-level) |
| `Paragraph` | Everything else -- contiguous non-blank lines |

All tokens are combined into a `Block` union type. The tokenizer guarantees full coverage: every source line belongs to exactly one token, with no gaps or overlaps.

### Design rationale

The tokenizer exists as a separate module (rather than inline parsing within the renderer) for two reasons:

- **Dual consumers:** both the rendering pipeline and the lint system operate on tokens. The lint system needs line numbers for diagnostics, and the renderer needs structured data for dispatch.
- **Testability:** tokenization can be tested in isolation without invoking HTML generation or directive resolution.

## Rendering Pipeline

**Module:** `selfdoc/html.py`, function `md_to_html`

The rendering pipeline converts resolved Markdown to HTML through a three-phase process:

### Phase 1: Tokenize and render blocks

`md_to_html` calls the tokenizer, then iterates over the resulting tokens, dispatching each to `_render_block`. This function pattern-matches on token type and delegates to specialized renderers (`_render_heading`, `_render_code_block`, `_render_table`, `_render_definition_list`, etc.). The first H1 heading is consumed for use as the page title and not rendered inline.

### Phase 2: Post-processors

After block rendering produces a joined HTML string, a series of regex-based post-processors transform the output:

- **Code tabs** (`_group_code_tabs`): consecutive code blocks with different languages are wrapped in a tabbed interface
- **Step guides** (`_apply_step_guides`): ordered lists following headings containing "step", "guide", or "tutorial" receive a `class="steps"` for special styling
- **API entries** (`_wrap_api_entries`): sequences of h3/h4 + code block + description paragraph are wrapped in `<div class="api-entry">` cards
- **Definitions** (`_apply_definitions`): definitional patterns after headings get `<dfn>` wrapping for semantic markup and glossary cross-linking
- **LCP promotion**: the first image in the page is promoted from `loading="lazy"` to `fetchpriority="high" loading="eager"` for faster Largest Contentful Paint

### Phase 3: Page assembly

`generate_html` wraps the per-page HTML in a full document shell: sidebar navigation, breadcrumbs, canonical URLs, OpenGraph tags, structured data, theme CSS, and JavaScript for code tabs and search.

### Why post-processors operate on HTML strings

Post-processors run after block rendering rather than on tokens because they detect cross-block patterns (e.g., "three consecutive code blocks" or "a heading followed by an ordered list"). The token stream is flat, making it natural to detect these patterns with regex on the rendered output. This keeps the renderer simple (one token in, one HTML fragment out) and moves heuristic logic to an explicit post-processing phase.

## Directive System

**Modules:** `selfdoc/directives.py` (parser), `selfdoc/resolver.py` (dispatch), `selfdoc/content.py` (content directives)

Directives are the core mechanism for pulling live information from source code into documentation.

### Syntax

The directive parser recognizes a structured marker syntax:

| Marker | Purpose |
|--------|---------|
| `:-: name key="value"` | One-liner directive |
| `:<: name [attrs]` | Block open |
| `:@: key="value"` | Additional attribute line |
| `:=:` | Body separator |
| `::: content` | Body line |
| `:>:` | Block close |

Directives inside fenced code blocks are ignored. Unclosed block directives at EOF produce a `DirectiveError`.

### Resolver dispatch chain

When a directive is encountered during the build, the resolver (`make_resolver`) processes it through a three-level dispatch chain:

1. **Content directives** -- `resolve_content` handles callouts (`callout-note`, `callout-warning`, etc.) and `list-glossary`. These transform body content into styled HTML without needing source code access. If the directive matches a content type, resolution stops here.

2. **Custom directives** -- if the project's `selfdoc.json` declares a `"directives"` map, the resolver loads the referenced Python script and calls its `resolve(attrs, config, body)` function. This allows project-specific extraction logic.

3. **Language extractor** -- the built-in extractor for the project's configured language handles the directive. This is the most common path for code-aware directives (`ref`, `table-schema`, `code-test`, `code-help`, `table-config`).

If none of these can handle the directive, the resolver emits an inline error marker (`> *[selfdoc: ...]*`) that is visible in the rendered output.

### Built-in directives

The directive catalog (`selfdoc/catalog.py`) defines two categories:

- **Core directives** (shipped and functional): `ref`, `table-schema`, `code-test`, `code-help`, `table-config`, callouts, and `list-glossary`
- **Future directives** (declared, parse-valid, not yet implemented): a large set organized by prefix -- `table-*`, `code-*`, `list-*`, `callout-*`, `prose-*`

Declaring future directives means the parser accepts them without error, allowing documentation authors to mark intent before extraction logic exists.

## Language Extractors

**Module:** `selfdoc/extractors/`

Each language has a dedicated extractor implementing the `LanguageExtractor` protocol:

### The protocol

```python
class LanguageExtractor(Protocol):
    @property
    def name(self) -> str: ...
    def detect(self, dir_path: str) -> bool: ...
    def resolve_path(self, path_arg, source_paths, base_dir) -> str | None: ...
    def extract(self, directive_name, attrs, body, source_paths, base_dir) -> str: ...
    def file_extensions(self) -> list[str]: ...
    def public_symbols(self, file_path: str) -> list[str]: ...
```

The protocol is `runtime_checkable`, allowing the registry to validate extractors at import time.

### Implementations

| Extractor | Language | Parsing strategy |
|-----------|----------|-----------------|
| `PythonExtractor` | Python | `ast` module -- full AST parsing for accurate symbol extraction |
| `GoExtractor` | Go | Regex-based -- matches exported identifiers, struct fields, function signatures |
| `TypeScriptExtractor` | TypeScript, JavaScript | Regex-based -- matches exports, interfaces, type aliases |

The Python extractor uses the `ast` module because Python's grammar makes regex-based extraction unreliable (decorators, multiline signatures, nested classes). Go and TypeScript have simpler export conventions (capitalized names in Go, explicit `export` keywords in TypeScript) that regex handles reliably.

### What each directive extracts

| Directive | Extraction target |
|-----------|------------------|
| `ref` | Module docstring, exported functions, classes with their signatures and docs |
| `table-schema` | Dataclass/struct/interface fields rendered as a Markdown table |
| `code-test` | Test function source code (whole file or specific function) |
| `code-help` | CLI argument parser definitions and help text |
| `table-config` | Configuration keys with types and descriptions |

### Language detection

The extractor registry also provides auto-detection: `detect_language` probes for marker files (`pyproject.toml` for Python, `go.mod` for Go, `package.json`/`tsconfig.json` for TypeScript) in priority order. This powers the `selfdoc init` command.

## Build Pipeline

**Module:** `selfdoc/build.py`, function `build`

The `build` function orchestrates the full site generation:

### Main pipeline

1. Load config from `selfdoc.json`
2. Walk `docs/` for `.md` templates (skipping the output directory)
3. Parse frontmatter from each file (YAML between `---` fences)
4. Resolve directives using the project's configured language extractor
5. Pass resolved Markdown through `generate_html` (which tokenizes, renders, and post-processes)
6. Copy non-Markdown assets (images, CSS, scripts) to the output directory

### Auxiliary file generation

After the main pipeline completes, the build generates:

- **Sitemap** (`sitemap.xml`): standard sitemap with page URLs and last-modified dates
- **Atom feed** (`feed.xml`): full Atom feed for RSS readers, respecting per-page `feed: false` frontmatter
- **Search index** (`search-index.json`): JSON index built from headings and content for client-side search
- **OG images**: OpenGraph card PNGs for social sharing (uses predraw if available, falls back to pure-Python PNG generation)
- **`llms.txt`**: a structured plain-text index of the site for LLM consumption, plus an `llms-full.txt` with all content
- **Compressed companions**: gzip (and brotli if available) pre-compressed versions of text-based output files for efficient serving

### Staleness tracking

The build computes content hashes for each page and persists them. The check command later uses these hashes to detect when page content has changed but its description has not been updated -- a common source of stale SEO metadata.

### Atomic writes and concurrency

File writes to shared state use atomic write patterns (write to a temporary file, then `os.replace`). This prevents partial reads if another process accesses the output directory during a build.

## Lint System

**Module:** `selfdoc/check.py`

The `check` command validates documentation quality across three dimensions: directive correctness, documentation coverage, and SEO best practices.

### Directive validation

For every directive in every docs template, the checker:

1. Parses the directive (validating syntax and name against the catalog)
2. Attempts full resolution using the project's extractor
3. Reports OK or FAILED with the specific error

This catches broken paths, missing symbols, and malformed attributes before they reach production.

### Coverage analysis

Coverage measures how many public symbols in the source code are referenced by at least one directive. The analysis uses each extractor's `public_symbols` method to enumerate exported symbols, then cross-references against successfully resolved directives.

### SEO lint checks

The lint system operates on tokens (not raw Markdown), which gives it access to structured information like heading levels, image alt text, and link targets. There are 14 checks:

| Code | Check |
|------|-------|
| SEO001 | Multiple H1 headings |
| SEO002 | Heading level gaps (e.g., H2 followed by H4) |
| SEO003 | Empty image alt text |
| SEO004 | Title too long for search results |
| SEO006 | Missing meta description |
| SEO007-008 | Link and structural diagnostics |
| SEO009 | Description too short |
| SEO010 | Description too long |
| SEO011-012 | Content quality signals |
| SEO013 | No title source (no frontmatter title and no H1) |
| SEO014 | Meaningless alt text (e.g., "image", "screenshot") |
| SEO015 | Generic anchor text (e.g., "click here", "link") |

### Staleness detection

When a page's content hash differs from the last build but its description hash is unchanged, the checker flags it as potentially stale. This catches the common case where documentation content is updated but the frontmatter description (used in search results and social cards) still describes the old content.

### Why tokens, not raw Markdown

Operating on tokens rather than raw text means the lint system gets pre-parsed structure for free. It does not need to re-implement heading detection, code block boundaries, or list parsing. It can reliably distinguish "an image inside a code block" (should not trigger SEO003) from "an image in body text" (should trigger it).
