---
title: Glossary Guide
description: "How to use selfdoc's glossary feature: define terms with dfn tags and list-glossary directives, get auto-linking and a generated glossary page."
nav_group: "Guides"
nav_order: 14
---

# Glossary Guide

selfdoc can build a glossary from terms defined across your documentation. Define a term once, and selfdoc auto-links the first mention on every other page back to its definition. You also get a generated glossary page that aggregates all terms alphabetically.

## Defining Terms

There are two ways to mark a term as a glossary entry.

### Inline `<dfn>` tags

Wrap a term in `<dfn>` tags anywhere in your Markdown content. selfdoc picks up the term name from the tag and the surrounding paragraph as its definition:

```markdown
A <dfn>directive</dfn> is a structured marker in your Markdown templates
that selfdoc resolves at build time by extracting content from source code.
```

This creates a glossary entry for "directive" with the paragraph text as its definition.

### The `list-glossary` directive

For a dedicated glossary section, use the `list-glossary` content directive. Each term is defined with `**Term**: Definition` syntax:

```markdown
:<: list-glossary
:=:
::: **Directive**: A structured marker that selfdoc resolves at build time.
::: **Extractor**: A language-specific module that reads source code to fulfill directives.
::: **Frontmatter**: YAML metadata at the top of a Markdown file.
:>:
```

This renders as a styled definition list (`<dl>/<dt>/<dd>`) and registers each term in the site-wide glossary. The `glossary` alias also works in place of `list-glossary`.

## Auto-linking

Once a term is defined (via either method), selfdoc auto-links the first occurrence of that term on every other page. The link points to the term's definition, either on the glossary page or on whichever page defined it.

Auto-linking is case-insensitive for matching but preserves the original casing in the rendered text. Only the first mention per page gets linked -- subsequent mentions are left as plain text to avoid cluttering the page.

> [!NOTE]
> Auto-linking skips content inside glossary blocks themselves to prevent circular links. Terms inside code blocks and headings are also left alone.

## The Generated Glossary Page

When `glossary` is `true` in your `selfdoc.json` (which it is by default), selfdoc generates an alphabetically sorted glossary page that collects every `<dfn>` term and `list-glossary` entry across your entire site. Each entry shows the term, its definition, and a link back to the page where it was defined.

## Configuration

The glossary feature is controlled by a single boolean in `selfdoc.json`:

```json
{
  "glossary": true
}
```

- `true` (default) -- glossary page is generated, auto-linking is active
- `false` -- no glossary page, no auto-linking (but `<dfn>` tags and `list-glossary` directives still render normally on their own pages)

## Tips

- Define terms close to where they are first explained. Readers who follow the auto-link land right in context.
- Use `list-glossary` for a curated reference section. Use inline `<dfn>` for terms introduced naturally in prose.
- The glossary page filename is based on whether you have a `glossary-terms.md` template in `docs/`. If you do, its content is used as the page body above the auto-generated term list.
- In unified (multi-project) builds, terms from all projects are merged into a single glossary with project attribution.

Next: [Multi-Language Support](multi-language/) -->
