#!/usr/bin/env python3
"""Custom directive script that generates a configuration reference table.

Outputs a Markdown table documenting all selfdoc.json config keys, grouped by
category: Core, Features, SEO, Deploy, Branding, and Generation.
"""

# Schema is hardcoded rather than AST-parsed from config.py. The validation
# logic in config.py is stable and this approach is more reliable.

SCHEMA = [
    # Core
    {
        "key": "language",
        "type": "string",
        "required": True,
        "category": "Core",
        "description": (
            "Source language. One of: `python`, `go`, `typescript`, `javascript`."
        ),
    },
    {
        "key": "source",
        "type": "array",
        "required": True,
        "category": "Core",
        "description": "Non-empty list of source directory paths to scan.",
    },
    {
        "key": "base_url",
        "type": "string",
        "required": True,
        "category": "Core",
        "description": (
            "Site base URL (e.g. `https://example.com`). Trailing slash is stripped."
        ),
    },
    {
        "key": "docs",
        "type": "string",
        "required": False,
        "category": "Core",
        "description": 'Directory containing Markdown templates. Default: `"docs/"`.',
    },
    {
        "key": "output",
        "type": "string",
        "required": False,
        "category": "Core",
        "description": 'Build output directory. Default: `"docs/_build/"`.',
    },
    {
        "key": "repo",
        "type": "string",
        "required": False,
        "category": "Core",
        "description": "GitHub repository URL. Enables source links in generated pages.",
    },
    {
        "key": "branch",
        "type": "string",
        "required": False,
        "category": "Core",
        "description": "Git branch for source links. Used with `repo`.",
    },
    {
        "key": "description",
        "type": "string",
        "required": False,
        "category": "Core",
        "description": "Project description used in site metadata and SEO tags.",
    },
    {
        "key": "directives",
        "type": "object",
        "required": False,
        "category": "Core",
        "description": (
            "Map of custom directive names to script paths (relative to project root). "
            "Default: `{}`."
        ),
    },
    # Features
    {
        "key": "theme",
        "type": "string",
        "required": False,
        "category": "Features",
        "description": 'Theme name. Default: `"minimal"`.',
    },
    {
        "key": "search",
        "type": "string",
        "required": False,
        "category": "Features",
        "description": (
            "Search UI style. One of: `icon`, `bar`, `hidden`."
        ),
    },
    {
        "key": "search_engine",
        "type": "string",
        "required": False,
        "category": "Features",
        "description": (
            "Search engine backend. One of: `builtin`, `fuse`, `minisearch`."
        ),
    },
    {
        "key": "feedback",
        "type": "object",
        "required": False,
        "category": "Features",
        "description": (
            "Page feedback widget. Must contain at least one of "
            "`webhook` (URL string) or `ga` (Google Analytics ID string)."
        ),
    },
    {
        "key": "auto_detect",
        "type": "object",
        "required": False,
        "category": "Features",
        "description": (
            "Auto-detection toggles. Valid keys: `steps` (bool), `api_entries` (bool)."
        ),
    },
    {
        "key": "min_coverage",
        "type": "integer",
        "required": False,
        "category": "Features",
        "description": (
            "Minimum documentation coverage (0--100). "
            "`selfdoc check` fails if coverage is below this threshold."
        ),
    },
    # SEO
    {
        "key": "author",
        "type": "object",
        "required": False,
        "category": "SEO",
        "description": (
            "Author metadata. Required sub-key: `name` (string). "
            "Optional: `type` (`Person` or `Organization`), "
            "`twitter` (handle starting with `@`)."
        ),
    },
    {
        "key": "twitter",
        "type": "string",
        "required": False,
        "category": "SEO",
        "description": (
            "Twitter handle (starts with `@`). Overridden by `author.twitter` if both set."
        ),
    },
    {
        "key": "lang",
        "type": "string",
        "required": False,
        "category": "SEO",
        "description": (
            "BCP 47 language tag for HTML `lang` attribute (e.g. `en`, `en-US`, `pt-BR`)."
        ),
    },
    {
        "key": "lint_ignore",
        "type": "array",
        "required": False,
        "category": "SEO",
        "description": (
            "List of SEO lint codes to suppress (e.g. `[\"SEO007\"]`). "
            "Each entry must match the pattern `SEO` followed by digits."
        ),
    },
    # Deploy
    {
        "key": "deploy.provider",
        "type": "string",
        "required": "When `deploy` is present",
        "category": "Deploy",
        "description": (
            "Deploy provider. One of: `cloudflare-pages`, `github-pages`."
        ),
    },
    {
        "key": "deploy.project",
        "type": "string",
        "required": "For `cloudflare-pages`",
        "category": "Deploy",
        "description": "Cloudflare Pages project name.",
    },
    # Branding
    {
        "key": "branding.tagline",
        "type": "string",
        "required": False,
        "category": "Branding",
        "description": "Hero tagline displayed on the landing page.",
    },
    {
        "key": "branding.cta_text",
        "type": "string",
        "required": False,
        "category": "Branding",
        "description": "Primary call-to-action button text.",
    },
    {
        "key": "branding.cta_link",
        "type": "string",
        "required": False,
        "category": "Branding",
        "description": "Primary call-to-action button URL.",
    },
    {
        "key": "branding.secondary_cta_text",
        "type": "string",
        "required": False,
        "category": "Branding",
        "description": "Secondary call-to-action button text.",
    },
    {
        "key": "branding.secondary_cta_link",
        "type": "string",
        "required": False,
        "category": "Branding",
        "description": "Secondary call-to-action button URL.",
    },
    {
        "key": "branding.logo",
        "type": "string",
        "required": False,
        "category": "Branding",
        "description": "Path to logo image.",
    },
    {
        "key": "branding.features",
        "type": "array",
        "required": False,
        "category": "Branding",
        "description": (
            "List of feature cards for the landing page. "
            "Each item must have `title` (string) and `description` (string)."
        ),
    },
    # Generation
    {
        "key": "gen.exclude",
        "type": "array",
        "required": False,
        "category": "Generation",
        "description": (
            "List of module paths to exclude from `selfdoc gen` output."
        ),
    },
    {
        "key": "gen_data",
        "type": "object",
        "required": False,
        "category": "Generation",
        "description": (
            "Data generation configuration. Contains `scripts`: a list of "
            "objects with `command` (string), `output` (string), and "
            "`mounts` (list of strings)."
        ),
    },
]

CATEGORY_ORDER = ["Core", "Features", "SEO", "Deploy", "Branding", "Generation"]


def resolve(attrs, config, body):
    """Generate a Markdown configuration reference grouped by category."""
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
            key = f"`{field['key']}`"
            ftype = f"`{field['type']}`"
            if field["required"] is True:
                req = "Yes"
            elif field["required"] is False:
                req = "No"
            else:
                req = field["required"]
            desc = field["description"]
            lines.append(f"| {key} | {ftype} | {req} | {desc} |")

        lines.append("")

    return "\n".join(lines)
