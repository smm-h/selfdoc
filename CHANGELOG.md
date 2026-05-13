# Changelog

## 0.4.0

### Breaking Changes

- Directive syntax redesigned: new attribute-based format (`:-:`, `:<:`, `:>:`) with a formal directive catalog replacing the old `:::name arg` syntax. All existing directive blocks must be migrated. The `glossary` directive is now `list-glossary`.
- Custom directive scripts must update from `resolve(arg, config)` to `resolve(attrs, config, body)`. Body content is now forwarded.
- Extractors refactored to a `LanguageExtractor` protocol with a registry. Custom extractor integrations may need updating.

### Added

- `selfdoc gen` command: auto-generates documentation pages from source code structure, with exclusion patterns, `generated: true` frontmatter, and stale file cleanup
- `selfdoc gen-data` command: runs sandboxed scripts (via bubblewrap) to generate CSV/JSON data files for documentation
- First-class strictcli support: auto-detects strictcli usage and generates CLI documentation pages
- Description staleness detection: `selfdoc check` warns (STALE001) when a page description no longer matches page content, tracked via content hashing in `.selfdoc/hashes/`
- Pluggable search engine: choose `"builtin"`, `"fuse"`, or `"minisearch"` via the `search_engine` config field
- Landing page template: hero section with tagline, CTA button, and feature cards, configured via `branding` config field
- Cross-page term linking: `<dfn>` definitions automatically linked across pages with dotted-underline `.term-link` styling
- Auto-generated glossary page: collects all `<dfn>` terms site-wide into an alphabetical glossary with source links
- Documentation coverage for Go (exported symbols) and TypeScript/JavaScript (`export` declarations), previously Python-only
- Per-symbol coverage tracking with configurable `min_coverage` threshold
- Callout directives (note, tip, warning, danger, important) as first-class directive types
- Feed filtering via `feed: false` frontmatter; changelog pages auto-detected and excluded by default
- Changelog auto-detection: `CHANGELOG.md` in project root is automatically included as a documentation page
- Reading progress bar fixed below the topbar
- Scroll affordance gradients on overflowing code blocks and tables
- Sticky first column on horizontally-scrolling tables
- `auto_detect` config field to disable step guide and API entry heuristics globally or per-page via `auto_steps`/`auto_api` frontmatter
- `selfdoc build --warn-only` flag to treat lint warnings as non-fatal
- Page progress indicator ("Page X of Y") between prev/next links
- Current page title shown in the topbar on non-index pages

### Fixed

- Heading anchor IDs now deduplicate (appends `-1`, `-2` for repeated headings) and preserve Unicode characters
- Code tab sync no longer infinite-loops with 3+ tab groups sharing a language
- Scrollspy correctly tracks headings when scrolling in both directions
- Step guide detection tightened: keyword must appear at start of heading text, 200-char lookback (no more false positives on "Next Steps" or "Troubleshooting Steps")
- API entry wrapping tightened: requires identifier-like heading and single-line code block (no more false positives on tutorial sections)
- Heading copy-to-clipboard shows a toast notification
- Prev/next links show directional labels ("Previous" / "Next") above page titles
- Edit link opens in a new tab
- OG description falls back to first paragraph when no frontmatter description
- Admonition icons use CSS mask-image technique, adapting correctly to dark mode
- Each admonition type has a distinct background color
- Focus indicators use `:focus-visible` throughout (keyboard-only, no mouse outlines)
- Sidebar active link has a visible background highlight
- Mobile sidebar traps focus within the overlay
- Mobile sidebar closes on Escape key
- Table rows highlight on hover
- Diff highlighting uses `+`/`-` prefix symbols in addition to color
- Cmd+K label adapts to platform (shows Ctrl+K on Windows/Linux)
- "Last updated" date shown at the top of the page alongside breadcrumbs
- Search "no results" message includes guidance ("Try different terms or browse the sidebar")
- Feedback "No" response prompts for written feedback instead of just "Thanks"
- Negative feedback provides a text input for follow-up
- Collapsible section indicators replaced with 16x16px SVG chevrons (previously 8x12px CSS triangles)
- `<summary>` elements have `:focus-visible` outlines
- `<pre>` elements have `aria-label` describing the code language
- `llms-full.txt` includes page boundaries with title headings and path comments

### Improved

- Theme toggle shows descriptive ARIA labels indicating current state and next action
- Smooth scroll disabled on initial page load to prevent fragment target delay
- Target highlight animation uses 20% accent color (previously 12%, too faint)
- `<dfn>` tags visually distinct from inline `<code>` (dotted underline vs border)
- Page summary block visually distinct from blockquotes (card style vs left border)

## 0.3.1

- npm package renamed from `selfdoc` to `selfdocumenting` (npm blocks `selfdoc` due to similarity with abandoned `self-doc` package). Install via `npm install -g selfdocumenting` or `npx selfdocumenting`. The CLI command remains `selfdoc`.

## 0.3.0

### Breaking Changes

- `base_url` is now a required field in `selfdoc.json` (previously optional)
- Frontmatter `description` is now required on every page (auto-extraction removed); missing description is a build error
- `selfdoc build` now fails on SEO lint warnings

### Added

- Subdirectory-based nested nav groups with collapsible sidebar sections, localStorage persistence, and frontmatter overrides (`nav_group`, `nav_order`)
- Configurable search trigger via `search` config field: `"icon"` (magnifying glass button), `"bar"` (text input with Cmd+K hint), or `"hidden"`
- Functional feedback widget via `feedback` config field with webhook POST and Google Analytics event support
- Atom feed generation (`feed.xml`) with auto-discovery `<link>` tag in `<head>`
- Definition list syntax (`term\n: definition`) with glossary styling and DefinedTerm JSON-LD
- Inline stat markup (`==value==`) producing semantic `<data>` elements
- Code tabs for switching between language variants with localStorage persistence
- Git branch auto-detection for edit links; configurable via `branch` config field
- Edit link shown at both top and bottom of content area
- Rich OG card PNG generation with text overlay via predraw (optional dependency)
- SEO lint framework with 15 rules covering headings, descriptions, images, contrast, and structured data
- JSON-LD structured data: TechArticle, BreadcrumbList, WebSite, SoftwareSourceCode, Organization/Person, ItemList, DefinedTermSet
- Open Graph and Twitter Card meta tags with `og:locale`, `og:image:alt`, and auto-generated social card images
- `robots.txt` with explicit AI crawler permissions (GPTBot, ClaudeBot, PerplexityBot, etc.)
- `llms.txt` and `llms-full.txt` for AI documentation ingestion
- Visible "Last updated" dates with `<time>` elements, `dateModified` in JSON-LD, and sitemap `lastmod`
- `selfdoc check --ignore SEO007,SEO008` to suppress specific lint rules
- `selfdoc check --format json` for machine-readable output
- `selfdoc check` reports undocumented public symbols when coverage is below 100%
- Color-coded `selfdoc check` output (green/yellow/red by severity)
- `lint_ignore` config field for project-level lint rule suppression
- New config fields: `lang` (BCP 47), `author`, `twitter`, `branch`, `search`, `feedback`

### Fixed

- Edit link and "Last updated" date no longer run together (flex layout with gap)
- Sticky table headers no longer hide behind the fixed topbar
- Search shows "No results" message instead of blank space
- Search dialog closes when clicking a result link
- Copy button now always visible on code blocks (was hidden until hover, invisible on touch)
- Fixed dark mode contrast for all accent colors
- Fixed breadcrumb intermediate links pointing to non-existent directory index pages
- Fixed code-block hover shadow invisible in dark mode

### Improved

- Build-time Pygments syntax highlighting (replaced client-side highlight.js)
- Build-time CSS, JS, and HTML minification with critical CSS inlining
- Gzip and Brotli pre-compression of build output
- Search JS externalized to `search.js` with lazy index loading
- Conditional JS inclusion based on page content
- ARIA labels on sidebar nav, TOC nav, and search dialog
- Dynamic theme toggle ARIA label indicating current state
- Roving tabindex on code tabs per WAI-ARIA pattern
- Table `<caption>` derived from preceding heading for screen readers
- 44px minimum touch targets on all interactive elements
- Heading anchors visible on touch devices
- Admonition icons (distinct SVG per type: info, lightbulb, warning triangle, octagon, exclamation)
- Card-style prev/next navigation links
- Styled generic `<details>/<summary>` in content
- Styled standalone `<dfn>` tags outside glossary context
- RSS feed link in site footer
- Fragment highlight animation when navigating to `#section` URLs
- Print stylesheet: 2cm margins, forced light colors, hidden breadcrumbs, code wrapping
- Topbar truncates long project names with ellipsis
- Security headers and trailing slash redirects for Cloudflare Pages

## 0.2.0

### Added

- Theme system with per-project theming via `"theme"` in selfdoc.json and optional `docs/custom.css` overrides
- Minimal theme: clean typography, dark mode, high-contrast, and reduced-motion variants (all auto-detected from OS preferences)
- Top bar with project name and version badge
- Heading anchor links for deep linking
- Syntax highlighting via highlight.js (light + dark themes)
- Google-style docstring formatting (Args, Returns, Raises rendered as structured lists)

### Fixed

- Heading hierarchy: directive expansions use h2/h3/h4 instead of injecting h1
- Module name mangling (`selfdoc.extractorsthon` bug)
- Nested `_build/_build` recursion when rebuilding
- Deploy supports `CF_ACCOUNT_ID` and `CF_PAGES_API_TOKEN` env var names (remapped to wrangler's expected names)
- CSS extracted to cacheable `style.css` instead of inlined per page

## 0.1.0

- Code-aware static site generator
- `:::directive` syntax for embedding code-extracted content
- Python, Go, TypeScript/JS extractors
- 5 built-in directives (module, schema, test, cli, config)
- Custom directive plugins
- `selfdoc check` coverage analysis
- HTML generation with responsive CSS
- Deploy to Cloudflare Pages + GitHub Pages
- SSE live reload in `selfdoc serve`
