---
title: Directives Reference
description: "Complete reference for all built-in selfdoc directives including code extraction, content blocks, and custom directive authoring."
order: 30
---

# Directives Reference

selfdoc directives are inline blocks in Markdown templates that get resolved into content at build time. They pull live information from your source code, so documentation stays in sync with the implementation.

## Syntax

Directives come in two forms, depending on whether the directive is self-contained with just attributes or needs to include additional body content that gets passed to the resolver function. Directives placed inside fenced code blocks are ignored, so you can safely document directive syntax in your pages:

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
