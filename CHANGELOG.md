# Changelog

## Unreleased

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
