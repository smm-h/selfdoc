"""Convert Markdown files to static HTML with a built-in minimal converter.

No external dependencies -- handles headings, code blocks, inline code,
paragraphs, lists, links, bold/italic, and tables.
"""

import re

from selfdoc.themes import get_theme


def _slugify(text):
    """Convert heading text to a URL-friendly slug for deep linking.

    Strips HTML tags first, then: lowercase, spaces to hyphens,
    remove non-alphanumeric characters except hyphens.
    """
    # Strip HTML tags (e.g. <code>, <strong>, <a>)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.lower()
    text = text.replace(" ", "-")
    text = re.sub(r"[^a-z0-9-]", "", text)
    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def get_css(theme_name="minimal"):
    """Return the CSS content for the named theme.

    Args:
        theme_name: Name of the theme to load (default "minimal").

    Returns:
        The CSS content as a string.
    """
    return get_theme(theme_name)


def generate_html(markdown_files, project_name=None, version=None,
                   has_custom_css=False):
    """Convert Markdown files to static HTML.

    Args:
        markdown_files: Dict mapping relative paths to MD content.
        project_name: Project name for titles and sidebar.
        version: Version string for display (optional).
        has_custom_css: Whether a custom.css file exists for the project.

    Returns:
        Dict mapping file paths (.html) to HTML content.
    """
    if not project_name:
        project_name = "Documentation"
    if not version:
        version = ""

    # Build navigation from the file list
    nav_items = _build_nav(markdown_files)

    html_files = {}
    for md_path, md_content in markdown_files.items():
        html_path = _md_to_html_path(md_path)
        # Compute relative path from this file back to root for nav links
        depth = md_path.count("/")
        prefix = "../" * depth if depth > 0 else ""
        body_html = md_to_html(md_content)
        # Rewrite internal .md links to .html
        body_html = body_html.replace('.md"', '.html"')
        body_html = body_html.replace(".md)", ".html)")
        nav_html = _render_nav(nav_items, prefix, current_path=html_path)
        title = _extract_title(md_content, project_name)
        css_href = prefix + "style.css"
        custom_css_href = (prefix + "custom.css") if has_custom_css else None
        full_html = _wrap_page(
            body_html, nav_html, title, project_name, version,
            css_href, custom_css_href,
        )
        html_files[html_path] = full_html

    return html_files


def md_to_html(text):
    """Convert Markdown text to HTML.

    Handles: headings, code blocks, inline code, paragraphs,
    unordered lists, ordered lists, links, bold, italic, tables.
    """
    lines = text.split("\n")
    html_parts = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Fenced code blocks
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            code_content = _escape_html("\n".join(code_lines))
            if lang:
                html_parts.append(
                    f'<pre><code class="language-{_escape_html(lang)}">'
                    f"{code_content}</code></pre>"
                )
            else:
                html_parts.append(f"<pre><code>{code_content}</code></pre>")
            continue

        # Headings
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            content = _inline_format(heading_match.group(2))
            slug = _slugify(content)
            anchor = f'<a class="heading-link" href="#{slug}">#</a>'
            html_parts.append(
                f'<h{level} id="{slug}">{anchor}{content}</h{level}>'
            )
            i += 1
            continue

        # Tables: detect | col | col | pattern
        if re.match(r"^\|.+\|$", line.strip()):
            table_lines = []
            while i < len(lines) and re.match(r"^\|.+\|$", lines[i].strip()):
                table_lines.append(lines[i].strip())
                i += 1
            html_parts.append(_parse_table(table_lines))
            continue

        # Unordered list items (collect consecutive)
        if re.match(r"^[-*]\s+", line):
            list_items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                item_text = re.sub(r"^[-*]\s+", "", lines[i])
                list_items.append(f"<li>{_inline_format(item_text)}</li>")
                i += 1
            html_parts.append("<ul>" + "".join(list_items) + "</ul>")
            continue

        # Ordered list items
        if re.match(r"^\d+\.\s+", line):
            list_items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                item_text = re.sub(r"^\d+\.\s+", "", lines[i])
                list_items.append(f"<li>{_inline_format(item_text)}</li>")
                i += 1
            html_parts.append("<ol>" + "".join(list_items) + "</ol>")
            continue

        # Empty lines (skip, they separate paragraphs)
        if not line.strip():
            i += 1
            continue

        # Paragraph: collect consecutive non-empty, non-special lines
        para_lines = []
        while i < len(lines):
            current = lines[i]
            if not current.strip():
                break
            if current.startswith("```"):
                break
            if re.match(r"^#{1,6}\s+", current):
                break
            if re.match(r"^[-*]\s+", current):
                break
            if re.match(r"^\d+\.\s+", current):
                break
            if re.match(r"^\|.+\|$", current.strip()):
                break
            para_lines.append(current)
            i += 1
        para_content = _inline_format(" ".join(para_lines))
        html_parts.append(f"<p>{para_content}</p>")

    return "\n".join(html_parts)


def _parse_table(table_lines):
    """Parse markdown table lines into an HTML <table>.

    Expects lines like:
        | Header1 | Header2 |
        | ------- | ------- |
        | Cell1   | Cell2   |

    The separator line (containing only |, -, and spaces) is detected
    and used to separate header from body rows.
    """
    if not table_lines:
        return ""

    rows = []
    for line in table_lines:
        # Strip leading/trailing pipes and split by |
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)

    # Detect separator row (all cells match /^-+$/ or are empty)
    separator_idx = None
    for idx, row in enumerate(rows):
        if all(re.match(r"^-+$", cell) or cell == "" for cell in row):
            separator_idx = idx
            break

    html = "<table>\n"

    if separator_idx is not None and separator_idx > 0:
        # Rows before separator are headers
        html += "<thead>\n"
        for row in rows[:separator_idx]:
            html += "<tr>" + "".join(f"<th>{_inline_format(c)}</th>" for c in row) + "</tr>\n"
        html += "</thead>\n"
        # Rows after separator are body
        html += "<tbody>\n"
        for row in rows[separator_idx + 1:]:
            html += "<tr>" + "".join(f"<td>{_inline_format(c)}</td>" for c in row) + "</tr>\n"
        html += "</tbody>\n"
    else:
        # No separator: all rows are body
        html += "<tbody>\n"
        for row in rows:
            html += "<tr>" + "".join(f"<td>{_inline_format(c)}</td>" for c in row) + "</tr>\n"
        html += "</tbody>\n"

    html += "</table>"
    return html


def _inline_format(text):
    """Apply inline formatting: links, bold, italic, inline code."""
    # Inline code first (protect from other transformations)
    parts = []
    segments = text.split("`")
    for idx, seg in enumerate(segments):
        if idx % 2 == 1:
            # Inside backticks -- render as code, no further processing
            parts.append(f"<code>{_escape_html(seg)}</code>")
        else:
            # Outside backticks -- apply other inline formatting
            formatted = seg
            # Links: [text](url)
            formatted = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                r'<a href="\2">\1</a>',
                formatted,
            )
            # Bold: **text**
            formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", formatted)
            # Italic: *text*
            formatted = re.sub(r"\*(.+?)\*", r"<em>\1</em>", formatted)
            parts.append(formatted)
    return "".join(parts)


def _escape_html(text):
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _md_to_html_path(md_path):
    """Convert a .md path to .html."""
    if md_path.endswith(".md"):
        return md_path[:-3] + ".html"
    return md_path + ".html"


def _build_nav(markdown_files):
    """Build navigation items from the markdown file list.

    Returns list of dicts: {"label": str, "path": str (html path)}
    """
    nav = []
    # Index first
    if "index.md" in markdown_files:
        nav.append({"label": "Home", "path": "index.html"})

    # Remaining pages sorted alphabetically
    for md_path in sorted(markdown_files.keys()):
        if md_path == "index.md":
            continue
        # Use the filename (without extension) as the label
        label = md_path.replace(".md", "").replace("/", " / ")
        nav.append({"label": label, "path": _md_to_html_path(md_path)})

    return nav


def _render_nav(nav_items, prefix, current_path=""):
    """Render the sidebar navigation HTML as a flat list of links."""
    items_html = []
    for item in nav_items:
        href = prefix + item["path"]
        active_cls = ' class="active"' if item["path"] == current_path else ""
        items_html.append(
            f'<li><a href="{href}"{active_cls}>'
            f'{_escape_html(item["label"])}</a></li>'
        )
    return "".join(items_html)


def _extract_title(md_content, fallback):
    """Extract the first heading from markdown content as the page title."""
    match = re.match(r"^#\s+(.+)$", md_content, re.MULTILINE)
    if match:
        return match.group(1)
    return fallback


def _wrap_page(body_html, nav_html, title, project_name, version,
               css_href="style.css", custom_css_href=None):
    """Wrap converted HTML body in the full page template."""
    version_badge = (
        f'<span class="version-badge">v{_escape_html(version)}</span>'
        if version else ""
    )
    custom_css_tag = (
        f'\n<link rel="stylesheet" href="{custom_css_href}">'
        if custom_css_href else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape_html(title)} - {_escape_html(project_name)}</title>
<link rel="stylesheet" href="{css_href}">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github-dark.min.css" media="(prefers-color-scheme: dark)">{custom_css_tag}
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/highlight.min.js"></script>
<script>hljs.highlightAll();</script>
</head>
<body>
<header class="topbar">
<div class="topbar-inner">
<a class="project-name" href="index.html">{_escape_html(project_name)}</a>
{version_badge}
</div>
</header>
<div class="layout">
<nav class="sidebar">
<ul class="nav-list">
{nav_html}
</ul>
</nav>
<main class="content">
{body_html}
</main>
</div>
</body>
</html>
"""
