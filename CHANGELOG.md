# Changelog

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
