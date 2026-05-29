---
title: Directives Reference
description: "Complete reference for all built-in selfdoc directives including code extraction, content blocks, and custom directive authoring."
order: 30
nav_group: "Guides"
nav_order: 2
---

# Directives Reference

selfdoc directives are inline blocks in Markdown templates that get resolved into content at build time. They pull live information from your source code, so documentation stays in sync with the implementation.

## Syntax

Directives use 6 marker types and come in two forms: self-closing one-liners for directives that need only attributes, and block directives for those that accept additional body content passed to the resolver function. The marker characters (`:-:`, `:<:`, `:>:`, `:=:`, `:::`, `:@:`) are designed to be visually distinctive in plain Markdown.

:<: callout-note
:=:
::: Directives inside fenced code blocks (triple backticks) are ignored. You can safely show directive syntax in code examples without triggering resolution.
:>:

**One-liner** (self-closing, no body):

```markdown
:-: name key="value"
```

**Block** (with body content):

```markdown
:<: name key="value"
::: body line 1
::: body line 2
:>:
```

Block directives can also include additional attributes and a body separator:

```markdown
:<: name key="value"
:@: another="attr"
:=:
::: body content here
:>:
```

## Built-in Directives

The following table shows all built-in directives that selfdoc recognizes, their current implementation status (shipped or planned for a future release), and a brief description of what each directive extracts from source code or generates as content.

:-: catalog

### The `exclude` Attribute

The `table-schema` and `table-config` directives accept an optional `exclude` attribute — a comma-separated list of top-level keys to omit from the rendered table. Whitespace around commas is stripped.

```markdown
:-: table-config path="selfdoc.json" exclude="versions, locales"
:-: table-schema path="schema.json" exclude="internal_field"
```

If any excluded key does not exist in the file, a hard error is produced (no silent skips). Works with JSON, TOML, and JSONC files. For `table-schema`, `exclude` only applies when the path points to a data file — it has no effect when extracting from a Python dataclass or Go struct.

## Custom Directives

You can extend selfdoc with project-specific custom directives by registering them in your `selfdoc.json` configuration file, pointing each directive name to a Python script that implements the resolution logic. Custom directives take priority over built-in directives of the same name:

```json
{
  "directives": {
    "my-directive": "scripts/my-directive.py"
  }
}
```

Each custom directive script must export a `resolve(attrs, config, body)` function that returns a Markdown string:

```python
def resolve(attrs, config, body):
    """Called when :-: my-directive is encountered."""
    return "Generated content here"
```

- `attrs` — dict of key-value pairs from the directive line
- `config` — the full `selfdoc.json` configuration dict
- `body` — list of body lines (empty list for one-liners)

Custom directives take priority over built-in directives of the same name.
