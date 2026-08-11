---
title: Internals
description: "Developer internals: tokenizer design, extractor protocol, resolver dispatch, rendering pipeline, and lint system architecture."
nav_group: "Contributing"
nav_order: 1
---

# Internals

This page documents selfdoc's internal design for contributors and anyone extending or debugging the system. For the user-facing overview, see [Architecture](architecture/).

## Tokenizer

**Module:** `selfdoc/tokenizer.py` -- a standalone, zero-dependency module that splits Markdown source into a flat list of typed block tokens. It has no imports from selfdoc and is designed for reuse outside the project. The tokenizer guarantees that every source line belongs to exactly one token, with no gaps or overlaps.

### Token types

The tokenizer produces 11 token types, each a Python `@dataclass` with `start` and `end` line numbers (1-based, inclusive). These types are combined into a `Block` union type that the renderer and lint system pattern-match against. Each token carries enough structure for both rendering and diagnostics:

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

All tokens are combined into a `Block` union type.

### Design rationale

The tokenizer exists as a standalone zero-dependency module rather than being inline parsing logic in the renderer, and this separation is deliberate. There are two reasons it is factored out:

- **Dual consumers:** both the rendering pipeline and the lint system operate on tokens. Lint needs line numbers for diagnostics; the renderer needs structured data for dispatch.
- **Testability:** tokenization can be tested in isolation without invoking HTML generation or directive resolution.

## Rendering Pipeline

**Module:** `selfdoc/html.py`, function `md_to_html` -- converts resolved Markdown to HTML through a three-phase process involving tokenization, block-level dispatch rendering, and regex-based post-processing for cross-block patterns like code tabs and API entry cards.

### Phase 1: Tokenize and render blocks

`md_to_html` calls the tokenizer, then iterates over tokens, dispatching each to `_render_block`. This function pattern-matches on token type and delegates to specialized renderers (`_render_heading`, `_render_code_block`, `_render_table`, `_render_definition_list`, etc.). The first H1 heading is consumed for use as the page title and not rendered inline.

### Phase 2: Post-processors

After block rendering produces a joined HTML string, five regex-based post-processors scan for cross-block patterns that cannot be detected at the individual token level. Each post-processor modifies the HTML in place and passes the result to the next:

- **Code tabs** (`_group_code_tabs`): consecutive code blocks with different languages become a tabbed interface
- **Step guides** (`_apply_step_guides`): ordered lists after headings containing "step", "guide", or "tutorial" get `class="steps"`
- **API entries** (`_wrap_api_entries`): h3/h4 + code block + description are wrapped in `<div class="api-entry">` cards
- **Definitions** (`_apply_definitions`): definitional patterns get `<dfn>` wrapping for glossary cross-linking
- **LCP promotion**: first image promoted from `loading="lazy"` to `fetchpriority="high" loading="eager"`

### Phase 3: Page assembly

`generate_html` wraps per-page HTML in a full document shell with sidebar navigation, breadcrumbs, canonical URLs, OpenGraph tags, JSON-LD structured data, theme CSS, and JavaScript for interactive features like code tabs and client-side search. Every relative reference in that shell comes from the page's `PageAddress` (see `selfdoc_core.address`), which turns the mount coordinates plus the page path into the output key and the hops back to the mount root, the version-free mount, and the output root.

### Why post-processors operate on HTML strings

Post-processors detect cross-block patterns (e.g., "three consecutive code blocks" or "a heading followed by an ordered list"). The token stream is flat, so regex on rendered output is a natural fit. This keeps the renderer simple (one token in, one HTML fragment out) and moves heuristic logic to an explicit post-processing phase.

## Extractor Protocol

**Module:** `selfdoc/extractors/protocol.py` -- defines the `LanguageExtractor` protocol interface that all language extractors must implement to participate in directive resolution, coverage analysis, and language auto-detection. The protocol is `runtime_checkable`, allowing the extractor registry to validate implementations at import time rather than failing at call time.

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

The Python extractor uses `ast` because Python's grammar makes regex unreliable (decorators, multiline signatures, nested classes). Go and TypeScript have simpler export conventions (capitalized names, explicit `export` keywords) that regex handles reliably.

### Language detection

The registry provides auto-detection via `detect_language`, which probes for language-specific marker files in the project root using a fixed priority order: `pyproject.toml` or `setup.py` for Python, `go.mod` for Go, then `package.json` or `tsconfig.json` for TypeScript. This powers the `selfdoc init` command and the fallback when `language` is omitted from config.

## Resolver Dispatch Chain

**Module:** `selfdoc/resolver.py` -- when a directive is encountered during the build, the resolver created by `make_resolver` processes it through a three-level dispatch chain, stopping at the first match. This design allows content directives and custom directives to override built-in behavior:

1. **Content directives** -- `resolve_content` handles callouts and `list-glossary`. These transform body content into styled HTML without source code access. If matched, resolution stops here.

2. **Custom directives** -- if `selfdoc.json` declares a `"directives"` map, the resolver loads the Python script and calls `resolve(attrs, config, body)`.

3. **Language extractor** -- the built-in extractor for the project's language handles it. Most common path for `ref`, `table-schema`, `code-test`, `code-help`, `table-config`.

If none match, the resolver emits an inline error marker visible in rendered output.

### Built-in directive catalog

The catalog in `selfdoc/catalog.py` defines 76 built-in directives organized into two tiers based on implementation status. Declaring future directives makes them parse-valid so authors can mark intent before extraction logic exists:

- **Core directives** (shipped and functional): `ref`, `table-schema`, `code-test`, `code-help`, `table-config`, callouts, `list-glossary`
- **Future directives** (declared, parse-valid, not yet implemented): organized by prefix (`table-*`, `code-*`, `list-*`, `callout-*`, `prose-*`)

Declaring future directives means the parser accepts them without error, so documentation authors can mark intent before extraction logic exists.

## Lint System

**Module:** `selfdoc/check.py` -- validates documentation quality across three dimensions: directive correctness, API coverage measurement, and SEO best practices. The lint system operates on tokens rather than raw Markdown text, which lets it reliably distinguish content inside code blocks from content in the page body and produce accurate line numbers in diagnostics.

### Directive validation

For every directive in every template, the checker performs full resolution using the project's language extractor. This catches broken module paths, missing target symbols, malformed attributes, and custom directive script errors before the documentation reaches production. Each failure includes the file path and line number for quick navigation.

### Coverage analysis

Measures how many public symbols in your source code are referenced by at least one directive across all documentation templates. It uses each language extractor's `public_symbols` method to enumerate exports and cross-references them against the set of symbols mentioned in resolved directive output. The result is a percentage that can be gated by `min_coverage`.

### SEO lint checks

The module runs 15 checks covering metadata quality, content structure, accessibility, and description staleness. Each check has a unique code (e.g., SEO001 through SEO015), a severity level of either error or warning, and an actionable message with specific fix suggestions. Errors block CI pipelines while warnings are informational:

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

### Why tokens, not raw Markdown

The lint system operates on tokens rather than raw text, getting pre-parsed structure for free. It can reliably distinguish "an image inside a code block" (skip SEO003) from "an image in body text" (flag it).

### Staleness detection

When a page's content hash differs from the last build but its description hash is unchanged, the checker flags it as potentially stale -- catching the common case where content changes but the frontmatter description still describes the old version.
