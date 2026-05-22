# Deferred Features

Items explicitly deferred during the 2026-05-22 design session. Each is a self-contained feature that can be picked up independently.

## Logo Design

Create a proper logo/icon for selfdoc to replace the auto-generated favicon initial. Would appear in the header, favicon, and OG cards.

## RTL and CJK Support

- Auto-detect or configure RTL locales (Farsi, Arabic, Hebrew) and set `dir="rtl"` on HTML
- Decide between CSS logical properties, separate RTL stylesheet, or both
- CJK typography considerations (line breaking, font stacks, spacing)
- Config: `rtl` flag already planned as part of locale config (`locales: [{code, label, default, rtl}]`)

## Author Frontmatter and Search Filter

- Optional `author` field in page frontmatter
- Rendered as a byline below the page title
- Searchable via `author=name` filter
- Useful for multi-contributor projects with section owners

## Content-Type Search Filter

- Auto-detect rendered element types in each page at build time (table, code, callout, image, list, definition, video, diagram, steps, api-card, glossary-term, tabs, diff, schema, etc.)
- Expose as `content-type=table` search filter
- No restricted list -- detect all element types selfdoc knows how to render
