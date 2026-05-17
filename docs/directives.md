---
title: Directives Reference
description: "Complete reference for all built-in selfdoc directives including code extraction and content block types."
order: 30
---

# Directives Reference

selfdoc directives are inline blocks in Markdown templates that get resolved into content at build time. They pull live information from your source code, so documentation stays in sync with the implementation.

## Syntax

Directives come in two forms:

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

:-: catalog

## Custom Directives

You can extend selfdoc with custom directives by adding entries to `selfdoc.json`:

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
