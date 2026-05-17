#!/usr/bin/env python3
"""Custom directive script that generates a catalog of all built-in directives.

Reads CORE_DIRECTIVES from selfdoc.catalog and outputs a Markdown reference
grouped by category.
"""

from selfdoc.catalog import CORE_DIRECTIVES


def resolve(attrs, config, body):
    """Generate a Markdown directive catalog grouped by category."""
    # Group directives by category
    categories = {}
    for name, spec in CORE_DIRECTIVES.items():
        categories.setdefault(spec.category, []).append((name, spec))

    # Sort within each category by name
    for cat in categories:
        categories[cat].sort(key=lambda x: x[0])

    # Category display names
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
            required = ", ".join(f"`{a}`" for a in spec.required_attrs) or "—"
            optional = ", ".join(f"`{a}`" for a in spec.optional_attrs) or "—"
            lines.append(
                f"| `{name}` | {spec.description} | {required} | {optional} |"
            )
        lines.append("")
        # Add examples subsection
        lines.append(f"#### {title} Examples")
        lines.append("")
        for name, spec in categories[cat_key]:
            if spec.example:
                lines.append(f"**`{name}`**:")
                lines.append("")
                lines.append("```markdown")
                lines.append(spec.example)
                lines.append("```")
                lines.append("")

    return "\n".join(lines)
