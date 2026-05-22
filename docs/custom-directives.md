---
title: Custom Directives
description: "Write custom directives as Python scripts that generate Markdown content at build time, with access to project config and directive attributes."
nav_group: "Guides"
nav_order: 9
---

# Custom Directives

selfdoc's built-in directives cover common patterns like module references and schema tables, but sometimes you need something project-specific. Custom directives let you write a Python script that generates Markdown content at build time, driven by your own logic.

## How It Works

A custom directive is a Python script with a `resolve(attrs, config, body)` function. You register it in `selfdoc.json`, then use it in your Markdown templates just like a built-in directive. During the build, selfdoc calls your function and replaces the directive marker with whatever Markdown you return.

## Configuration

Map directive names to script paths in the `directives` section of `selfdoc.json`:

```json
{
  "directives": {
    "catalog": "scripts/catalog-directive.py",
    "config-schema": "scripts/config-schema-directive.py"
  }
}
```

Paths are relative to the project root. Each script must define a `resolve` function at module level.

## The resolve Interface

```python
def resolve(attrs, config, body):
    """Generate Markdown content for this directive.

    Args:
        attrs: Dict of key-value attributes from the directive marker.
        config: The full selfdoc.json config dict.
        body: String body content (for block directives), or None for self-closing.

    Returns:
        A string of Markdown content that replaces the directive marker.
    """
```

- **attrs** -- a `dict[str, str]` parsed from the directive's inline attributes. For `:-: my-directive path="foo" target="bar"`, this is `{"path": "foo", "target": "bar"}`.
- **config** -- the full loaded `selfdoc.json` as a Python dict. Useful for reading `source`, `language`, `base_url`, or any custom fields you add.
- **body** -- for block directives (the `:<:` / `:>:` syntax), this is the content between the opening and closing markers. For self-closing directives (`:-:`), this is `None`.

Return a string of Markdown. selfdoc will process it through the normal Markdown-to-HTML pipeline, so you get headings, tables, code blocks, and inline formatting for free.

## Example: Directive Catalog

selfdoc's own documentation uses a custom directive to generate the built-in directive reference table. Here is the script at `scripts/catalog-directive.py`:

```python
from selfdoc.catalog import CORE_DIRECTIVES

def resolve(attrs, config, body):
    categories = {}
    for name, spec in CORE_DIRECTIVES.items():
        categories.setdefault(spec.category, []).append((name, spec))

    for cat in categories:
        categories[cat].sort(key=lambda x: x[0])

    category_titles = {
        "code": "Code Extraction",
        "content": "Content Blocks",
    }

    lines = []
    for cat_key in ("code", "content"):
        if cat_key not in categories:
            continue
        title = category_titles.get(cat_key, cat_key.title())
        lines.append(f"### {title}")
        lines.append("")
        lines.append("| Directive | Description | Required | Optional |")
        lines.append("|-----------|-------------|----------|----------|")
        for name, spec in categories[cat_key]:
            required = ", ".join(f"`{a}`" for a in spec.required_attrs) or "---"
            optional = ", ".join(f"`{a}`" for a in spec.optional_attrs) or "---"
            lines.append(f"| `{name}` | {spec.description} | {required} | {optional} |")
        lines.append("")

    return "\n".join(lines)
```

It imports directly from selfdoc's own modules, groups directives by category, and returns a Markdown table. In the docs, it is invoked with a simple self-closing marker:

```markdown
:-: catalog
```

No attributes needed -- the script reads everything it needs from the selfdoc internals.

## Example: Config Schema

The second custom directive, `scripts/config-schema-directive.py`, generates a configuration reference table from a hardcoded schema definition. It groups config keys by category (Core, Features, SEO, Deploy, Branding, Generation) and renders each group as a Markdown table:

```python
SCHEMA = [
    {"key": "language", "type": "string", "required": True,
     "category": "Core", "description": "Source language."},
    {"key": "source", "type": "array", "required": True,
     "category": "Core", "description": "Source directory paths."},
    # ... more fields ...
]

def resolve(attrs, config, body):
    lines = []
    for category in CATEGORY_ORDER:
        fields = [f for f in SCHEMA if f["category"] == category]
        if not fields:
            continue
        lines.append(f"### {category}")
        lines.append("")
        lines.append("| Key | Type | Required | Description |")
        lines.append("|-----|------|----------|-------------|")
        for field in fields:
            lines.append(f"| `{field['key']}` | `{field['type']}` | ... | {field['description']} |")
        lines.append("")
    return "\n".join(lines)
```

This approach keeps the schema definition close to the directive that renders it, rather than trying to parse it from source code at build time.

## Tips

- **Return Markdown, not HTML.** selfdoc processes your output through its full Markdown pipeline, so you get syntax highlighting, heading anchors, and table styling for free.
- **Use config for project info.** The `config` parameter gives you access to `base_url`, `language`, `source`, and any custom keys you add to `selfdoc.json`.
- **Body parameter for block directives.** If your directive uses block syntax (`:<:` / `:>:`), the content between markers is passed as `body`. This is useful for directives that transform or augment user-provided content.
- **Keep scripts in `scripts/`.** The convention is to put directive scripts in a `scripts/` directory at the project root, but any path relative to the project root works.

> [!WARNING]
> Custom directive scripts run as Python code during the build. They have full access to the filesystem and Python environment. Only use trusted scripts.

Next: [Check Guide](check-guide/) -->
