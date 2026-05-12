# SEO/GEO Audit

Comprehensive audit of selfdoc's generated HTML against 50 SEO and GEO (Generative Engine Optimization) best practices. Conducted 2026-05-11.

**Overall: 13 DONE / 18 PARTIAL / 19 MISSING out of 50.**

## Group 1: HTML Structure and Semantics (3/8 done)

### 1. Single H1 per page with keyword hierarchy -- PARTIAL

Each page should have exactly one H1. AI engines parse and cite content by heading sections independently. `md_to_html()` in `html.py` converts any `#` to `<h1>` with no enforcement of a single-H1 rule. The demo page has 3 H1s.

### 2. Semantic HTML5 landmarks -- PARTIAL

Uses `<header>`, `<nav>`, `<main>`, `<aside>`, `<footer>` (page-level). Missing `<article>` around the content body. No document-level `<footer>` (the existing `<footer>` is inside `<main>`).

### 3. Descriptive anchor text on internal links -- DONE

All generator-produced anchor texts are descriptive: sidebar uses page labels, prev/next uses titles, edit link says "Edit this page on GitHub", breadcrumb says "Home". No "click here" patterns.

### 4. Self-contained answer paragraphs under each heading -- MISSING

No tooling or guidance for content authors. A 40-60 word lead paragraph under each heading increases AI citation probability by ~40%. The generator has no lint/check for this.

### 5. TOC with anchor links -- DONE

`_build_toc()` extracts h2/h3 headings with `id` slugs, renders desktop `<aside class="toc">` and mobile `<details class="mobile-toc">`. Scrollspy via IntersectionObserver. Only h2/h3 included (h4-h6 excluded).

### 6. Breadcrumbs with markup -- PARTIAL

Visible breadcrumbs with `<nav class="breadcrumbs" aria-label="Breadcrumbs">`. Missing BreadcrumbList JSON-LD structured data. Flat hierarchy only (Home -> Page), no intermediate directory levels.

### 7. Skip-to-content link -- DONE

`<a class="skip-link" href="#main-content">Skip to content</a>` is the first element inside `<body>`. CSS positions it off-screen and reveals on focus.

### 8. Clean heading levels without gaps -- MISSING

`md_to_html()` converts heading levels directly from Markdown with no validation. Skipping H2 to H4 produces invalid hierarchy silently. No warning in `selfdoc check`.

---

## Group 2: Meta Tags and Head Elements (2/8 done)

### 9. Title tag under 60 characters -- PARTIAL

Format is `{title} - {project_name}`. Page-specific keyword is first (good), but no length enforcement. Long headings or project names produce overlong titles. No warning or truncation.

### 10. Meta description 120-155 chars -- PARTIAL

`<meta name="description">` emitted only when frontmatter `description` is set. No auto-generation from page content. No length validation or warning.

### 11. Canonical URL on every page -- PARTIAL

`<link rel="canonical">` emitted only when `base_url` is configured. Projects without `base_url` get no canonical tags. The 404 page incorrectly gets a canonical URL. No warning when `base_url` is missing.

### 12. Open Graph and Twitter Card tags -- PARTIAL

Problems:
- Missing `og:url` despite canonical URL being computed.
- Missing `og:description`.
- `og:image` uses a relative path (OG spec requires absolute URLs).
- `og:image` is SVG (Facebook/LinkedIn don't support SVG).
- No Twitter Card tags at all (`twitter:card`, `twitter:title`, `twitter:description`, `twitter:image`).
- All OG tags conditional on `base_url`.

### 13. Charset as first meta tag -- DONE

`<meta charset="UTF-8">` is the first element inside `<head>`, well within the first 1024 bytes.

### 14. Viewport meta tag -- DONE

`<meta name="viewport" content="width=device-width, initial-scale=1.0">` is the second element in `<head>`.

### 15. Language declaration on html element -- PARTIAL

`<html lang="en">` is hardcoded. No config option to set a different language. Projects documenting non-English content cannot change this.

### 16. Preconnect and preload resource hints -- PARTIAL

Preconnect for `fonts.googleapis.com` and `fonts.gstatic.com` (with `crossorigin`). Missing preconnect for `cdnjs.cloudflare.com` (highlight.js CDN). No `preload` for critical resources (main stylesheet).

---

## Group 3: Structured Data / JSON-LD (0/7 done)

### 17. TechArticle schema with dateModified -- PARTIAL

JSON-LD emits `@type: "TechArticle"` with `headline`, `url`, and stub `author`. No `datePublished` or `dateModified`. Frontmatter parser doesn't extract dates. Build pipeline doesn't read file mtimes or git dates.

### 18. BreadcrumbList schema -- MISSING

Visible breadcrumbs exist but no BreadcrumbList JSON-LD. Search engines cannot programmatically identify them as breadcrumbs.

### 19. WebSite schema with SearchAction -- MISSING

Site has working Cmd+K search but no WebSite JSON-LD with SearchAction on the homepage. This enables sitelinks searchbox in Google results.

### 20. Organization or Person schema for authorship -- PARTIAL

Author is `{"@type": "Organization", "name": "<project_name>"}` where the name is the project directory name (e.g., "selfdoc"). No config for actual author/publisher. No `publisher`, `logo`, `url`, or `sameAs` for E-E-A-T.

### 21. SoftwareSourceCode schema on code blocks -- MISSING

Code blocks have `class="language-{lang}"` and the `repo` config field exists, but no SoftwareSourceCode JSON-LD is emitted.

### 22. ItemList schema for list pages -- MISSING

No ItemList JSON-LD for structured list content. 74.2% of AI citations come from structured list content.

### 23. DefinedTerm schema for technical terms -- MISSING

No DefinedTerm or DefinedTermSet markup. No glossary feature, no term definition detection.

---

## Group 4: Performance and Core Web Vitals (1/7 done)

### 24. Inline critical CSS, defer the rest -- MISSING

All CSS loaded via external `<link rel="stylesheet">`. The entire theme (~1345 lines) is render-blocking. Plus two highlight.js stylesheets. No CSS is inlined in `<head>`.

### 25. Explicit width and height on images -- MISSING

`<img>` tags have `src`, `alt`, and `loading` only. No `width` or `height`. Causes CLS as browser can't reserve space. Markdown doesn't natively carry dimensions.

### 26. Lazy-load below-fold, fetchpriority on LCP -- PARTIAL

All images universally get `loading="lazy"`, including the LCP image. The first/LCP image should have `fetchpriority="high"` and no lazy-loading.

### 27. Minify HTML, CSS, and JS at build time -- MISSING

CSS written as-is from theme file. HTML written with no post-processing. Inline JS emitted verbatim with full whitespace and comments. No minification anywhere.

### 28. Pre-compress with Brotli at build time -- MISSING

No `.br` or `.gz` files generated. No compression step in the build pipeline. Would need `brotli` package or CLI (conflicts with zero-dependency constraint).

### 29. font-display swap on web fonts -- DONE

Google Fonts URL includes `display=swap`, which causes `font-display: swap` in the returned `@font-face` rules.

### 30. Minimal or zero JavaScript -- MISSING

Loads highlight.js from CDN (~50KB min+gz). Plus ~360 lines of inline JS for: theme toggle, copy buttons, scrollspy, mobile sidebar, Cmd+K search, link prefetch, feedback widget, code tabs, run buttons. The baseline page does not work without JS (copy/run buttons don't exist, search doesn't work, theme toggle broken).

---

## Group 5: Crawlability and Indexing (2/7 done)

### 31. XML sitemap with lastmod dates -- PARTIAL

`sitemap.xml` generated with `<url><loc>` entries (conditional on `base_url`). No `<lastmod>` element. Source file mtimes available via `os.path.getmtime()` during build but never captured.

### 32. robots.txt with AI crawler permissions -- MISSING

No `robots.txt` generated. No references to any user-agent directives. Missing explicit allow for `ChatGPT-User`, `OAI-SearchBot`, `PerplexityBot`, `Googlebot`. Missing `Sitemap:` directive.

### 33. llms.txt with site map for AI agents -- DONE

`_generate_llms_txt()` produces Markdown-formatted file with project name, description from `index.md`, and `## Pages` listing each page as `- [Title](url): first sentence`.

### 34. llms-full.txt with complete content -- DONE

`_generate_llms_full_txt()` concatenates all resolved Markdown content into a single file separated by `---` dividers.

### 35. RSS or Atom feed -- MISSING

No feed generation. No `<link rel="alternate" type="application/rss+xml">` in HTML `<head>`. No date tracking to populate `<pubDate>` entries.

### 36. Consistent trailing slash policy -- PARTIAL

Implicitly uses "no trailing slash, .html extensions" consistently within the generated site. `base_url` has trailing slash stripped. But no redirect rules generated (no `_redirects` for Cloudflare Pages).

### 37. Custom 404 page with navigation and search -- PARTIAL

`404.html` generated with topbar and theme toggle, plus Cmd+K search dialog. But: no sidebar navigation (`nav_html = ""`), no popular page links, no visible search prompt (only keyboard shortcut).

---

## Group 6: Content Formatting for AI Citation (3/7 done)

### 38. Visible "Last updated" date on every page -- MISSING

No `dateModified`/`datePublished` in JSON-LD. No visible "Last updated" text on rendered pages. No mechanism to extract dates from frontmatter, file mtime, or git history. This is a cross-cutting gap: items 17, 31, 35, and 38 all depend on date tracking that doesn't exist.

### 39. Inline statistics and data points -- MISSING

Content authoring concern. No linting or check that warns when pages lack numeric content. Including stats every 150-200 words improves AI visibility by ~40%.

### 40. Definition paragraphs using "X is..." patterns -- MISSING

No detection of definitional patterns. No `<dfn>` markup generated. No DefinedTerm schema (see item 23). AI systems specifically extract "X is defined as..." patterns for citations.

### 41. Comparison tables with thead headers -- DONE

`_parse_table()` correctly produces `<thead>` with `<th>` elements and `<tbody>` with `<td>` elements. Tables wrapped in `<div class="table-wrap">`. Structured tables are 150% more likely to be extracted by AI engines.

### 42. Code blocks with language annotations -- DONE

Code blocks with language specifiers produce `<code class="language-{lang}">` and a visible `<div class="code-label">{lang}</div>`.

### 43. Summary or TL;DR block at page top -- MISSING

No visible summary/abstract rendered on pages. Frontmatter `description` is used only as `<meta name="description">`, never shown on the page. `_first_sentence()` exists but only used for llms.txt.

### 44. Ordered and unordered lists for procedures -- DONE

`<ul>`, `<ol>`, and `<ol class="steps">` all properly rendered. Step-guide enhancement auto-applied when heading contains "step", "guide", or "tutorial".

---

## Group 7: Accessibility and User Experience (2/6 done)

### 45. Alt text on all images -- PARTIAL

`<img>` tags include `alt` from Markdown `![alt](src)`, but empty alt values `![](url)` are silently accepted (producing `alt=""`). No linting or warning in `selfdoc check`.

### 46. WCAG AA color contrast -- PARTIAL

Light mode passes. Dark mode has failures:
- Sidebar text `#8b949e` on `#161b22` = ~4.0:1 (fails 4.5:1 for normal text).
- Secondary text `#8b949e` on `#0d1117` = ~4.6:1 (borderline).
High-contrast mode (`@media (prefers-contrast: more)`) exists and strengthens colors. No automated contrast checking.

### 47. Dark mode via prefers-color-scheme -- DONE

Full implementation: `@media (prefers-color-scheme: dark)` CSS, `[data-theme]` manual override, three-state toggle (system/light/dark), localStorage persistence, highlight.js stylesheet switching.

### 48. Print stylesheet -- DONE

`@media print` hides sidebar/toc/topbar/nav/feedback/buttons/search/theme-toggle/skip-link/gradient-strip. Linearizes layout, wraps long code, appends URLs after links. Minor: breadcrumbs and edit link not hidden.

### 49. Keyboard navigation with focus indicators -- PARTIAL

`focus-visible` outlines on links/buttons/inputs/tabindex elements. Code blocks and annotations are keyboard-focusable. Problems:
- Copy and Run buttons have `opacity: 0` and only appear on `pre:hover` -- invisible to keyboard-only users. No `:focus-within` rule.
- Tab buttons lack `role="tab"`, `aria-selected`, and `role="tabpanel"`.
- Search results lack `role="listbox"` / `role="option"` / `aria-activedescendant`.

### 50. HTTPS with HSTS header -- MISSING

Neither Cloudflare Pages nor GitHub Pages deploy generates HSTS configuration. No `_headers` file created in output. Cloudflare Pages needs `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` in a `_headers` file.

---

## Cross-cutting gaps

**Date tracking**: Items 17, 31, 35, and 38 all depend on knowing when pages were last modified. No date infrastructure exists -- no frontmatter date parsing, no file mtime capture, no git date extraction. This is the single highest-impact gap: it affects structured data freshness signals, sitemap crawl prioritization, RSS feeds, and visible "last updated" dates.

**Structured data**: The weakest group (0/7 done). The only JSON-LD is a minimal TechArticle stub. Five schema types are entirely absent (BreadcrumbList, WebSite, SoftwareSourceCode, ItemList, DefinedTerm).

**Performance**: No build-time optimization exists. HTML, CSS, and JS are emitted verbatim. No minification, no compression, no critical CSS extraction. highlight.js adds ~50KB to every page.

**AI crawler access**: No robots.txt means reliance on hosting defaults (which may block AI crawlers). llms.txt and llms-full.txt are strong points.
