"""Convert Markdown files to static HTML with a built-in minimal converter.

No external dependencies -- handles headings, code blocks, inline code,
paragraphs, lists, links, bold/italic, tables, blockquotes, and admonitions.
"""

import html
import json
import re
from datetime import datetime

from selfdoc.themes import get_theme

# Admonition types recognized in GitHub-flavored blockquotes (> [!TYPE])
_ADMONITION_TYPES = {"NOTE", "TIP", "WARNING", "CAUTION", "IMPORTANT"}


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
                   has_custom_css=False, repo=None, docs_dir_name="docs/",
                   base_url=None, frontmatter=None, lang="en",
                   page_dates=None, author=None, feed_url=None):
    """Convert Markdown files to static HTML.

    Args:
        markdown_files: Dict mapping relative paths to MD content.
        project_name: Project name for titles and sidebar.
        version: Version string for display (optional).
        has_custom_css: Whether a custom.css file exists for the project.
        repo: GitHub repo URL for "Edit this page" links (optional).
        docs_dir_name: Docs directory name for constructing source paths.
        base_url: Base URL for canonical links and sitemap (optional).
        frontmatter: Dict mapping relative paths to metadata dicts (Feature 34).
        page_dates: Dict mapping relative paths to ISO date strings (optional).
        author: Author dict from config (optional, keys: name, type, url).
        feed_url: Relative URL to the Atom feed (optional, e.g. "feed.xml").

    Returns:
        Dict mapping file paths (.html) to HTML content.
    """
    if not project_name:
        project_name = "Documentation"
    if not version:
        version = ""
    if frontmatter is None:
        frontmatter = {}
    if page_dates is None:
        page_dates = {}

    # Build navigation from the file list, using frontmatter for ordering
    nav_items = _build_nav(markdown_files, frontmatter)

    html_files = {}
    for page_idx, (md_path, md_content) in enumerate(
        # Iterate in nav order so prev/next matches sidebar
        [(item["md_path"], markdown_files[item["md_path"]])
         for item in nav_items if item["md_path"] in markdown_files]
    ):
        html_path = _md_to_html_path(md_path)
        # Compute relative path from this file back to root for nav links
        depth = md_path.count("/")
        prefix = "../" * depth if depth > 0 else ""
        body_html = md_to_html(md_content)
        # Rewrite internal .md links to .html
        body_html = body_html.replace('.md"', '.html"')
        body_html = body_html.replace(".md)", ".html)")
        nav_html = _render_nav(nav_items, prefix, current_path=html_path)

        # Use frontmatter title if available, else extract from content
        # (Feature 34)
        page_meta = frontmatter.get(md_path, {})
        title = page_meta.get("title") or _extract_title(md_content, project_name)

        # Meta description from frontmatter (Feature 34)
        description = page_meta.get("description", "")

        # Track frontmatter description for visible summary block (Phase 2.6)
        frontmatter_description = description or None

        # Auto-generate description from first paragraph if not in frontmatter
        if not description:
            description = _extract_first_paragraph(body_html)

        css_href = prefix + "style.css"
        custom_css_href = (prefix + "custom.css") if has_custom_css else None

        # Prev/next page links (Feature 8)
        prev_page = nav_items[page_idx - 1] if page_idx > 0 else None
        next_page = (nav_items[page_idx + 1]
                     if page_idx < len(nav_items) - 1 else None)

        # Breadcrumbs (Feature 9): not shown on index.html
        breadcrumbs = None
        if html_path != "index.html":
            breadcrumbs = _build_breadcrumbs(html_path, title, prefix)

        # Extract TOC from the body HTML (Feature 2)
        toc_html = _build_toc(body_html)

        # Source path for "Edit this page" link (Feature 14)
        source_path = docs_dir_name.rstrip("/") + "/" + md_path

        # Date modified for this page (Wave 2 date infrastructure)
        date_modified = page_dates.get(md_path)

        # Compute feed href relative to this page's depth
        page_feed_url = (prefix + feed_url) if feed_url else None

        full_html = _wrap_page(
            body_html, nav_html, title, project_name, version,
            css_href, custom_css_href,
            toc_html=toc_html,
            breadcrumbs=breadcrumbs,
            prev_page=prev_page,
            next_page=next_page,
            prefix=prefix,
            repo=repo,
            source_path=source_path,
            base_url=base_url,
            page_path=html_path,
            description=description,
            lang=lang,
            date_modified=date_modified,
            author=author,
            feed_url=page_feed_url,
            summary=frontmatter_description,
        )
        html_files[html_path] = full_html

    return html_files


def generate_404_page(project_name=None, version=None, has_custom_css=False,
                      nav_items=None, repo=None, base_url=None, lang="en",
                      feed_url=None):
    """Generate a custom 404 page using the standard page template (Feature 39).

    Returns the full HTML string for 404.html.
    """
    if not project_name:
        project_name = "Documentation"
    if not version:
        version = ""
    if nav_items is None:
        nav_items = []

    # Render sidebar navigation from nav_items
    nav_html = _render_nav(nav_items, prefix="", current_path="404.html")

    # Search prompt button
    search_html = (
        '<p>Try searching for what you need:</p>\n'
        '<button onclick="document.getElementById(\'search-dialog\')'
        '.showModal(); document.querySelector(\'.search-input\').focus();" '
        'style="padding: 0.5rem 1.5rem; font-size: 1rem; cursor: pointer; '
        'border: 1px solid var(--border); border-radius: 6px; '
        'background: var(--bg-secondary, #f5f5f5); '
        'color: var(--text-primary, #333);">'
        'Search documentation</button>'
    )

    # Popular pages section (first 5 nav items)
    popular_html = ""
    if nav_items:
        popular_links = []
        for item in nav_items[:5]:
            popular_links.append(
                f'<li><a href="{item["path"]}">'
                f'{_escape_html(item["label"])}</a></li>'
            )
        popular_html = (
            '\n<h2>Popular pages</h2>\n'
            '<ul>\n' + "\n".join(popular_links) + '\n</ul>'
        )

    body_html = (
        '<h1>Page not found</h1>\n'
        '<p>The page you are looking for does not exist.</p>\n'
        '<p><a href="index.html">Go to the homepage</a></p>\n'
        + search_html
        + popular_html
    )
    title = "Page not found"

    return _wrap_page(
        body_html, nav_html, title, project_name, version,
        css_href="style.css",
        custom_css_href="custom.css" if has_custom_css else None,
        prefix="",
        base_url=base_url,
        page_path="404.html",
        lang=lang,
        feed_url=feed_url,
    )


def md_to_html(text):
    """Convert Markdown text to HTML.

    Handles: headings, code blocks (with tabs and annotations), inline code,
    paragraphs, unordered lists, ordered lists, links, bold, italic, tables.
    """
    lines = text.split("\n")
    html_parts = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Fenced code blocks (with annotation support -- Feature 32)
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```

            # Collect annotation definitions after code block (Feature 32)
            # Lines like [1]: explanation text
            annotations = {}
            annotation_start = i
            while i < len(lines) and re.match(r"^\[(\d+)\]:\s*(.+)$", lines[i]):
                m = re.match(r"^\[(\d+)\]:\s*(.+)$", lines[i])
                annotations[m.group(1)] = m.group(2)
                i += 1

            code_block_html = _render_code_block(
                lang, code_lines, annotations
            )
            html_parts.append(code_block_html)
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

        # Tables: detect | col | col | pattern (Feature 38: wrap in .table-wrap)
        if re.match(r"^\|.+\|$", line.strip()):
            table_lines = []
            while i < len(lines) and re.match(r"^\|.+\|$", lines[i].strip()):
                table_lines.append(lines[i].strip())
                i += 1
            html_parts.append(
                '<div class="table-wrap">'
                + _parse_table(table_lines)
                + '</div>'
            )
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

        # Blockquotes (including admonitions)
        if line.startswith(">"):
            bq_lines = []
            while i < len(lines) and lines[i].startswith(">"):
                # Strip leading '> ' or '>'
                stripped = re.sub(r"^>\s?", "", lines[i])
                bq_lines.append(stripped)
                i += 1
            html_parts.append(_parse_blockquote(bq_lines))
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
            if current.startswith(">"):
                break
            para_lines.append(current)
            i += 1
        para_content = _inline_format(" ".join(para_lines))
        html_parts.append(f"<p>{para_content}</p>")

    result = "\n".join(html_parts)

    # Post-process: group consecutive code blocks into tabs (Feature 31)
    result = _group_code_tabs(result)

    # Post-process: add class="steps" to <ol> after step/guide/tutorial
    # headings (Feature 33)
    result = _apply_step_guides(result)

    # Post-process: wrap h3/h4 + code block + description in API entry
    # cards (Feature 48)
    result = _wrap_api_entries(result)

    return result


def _render_code_block(lang, code_lines, annotations=None):
    """Render a single fenced code block to HTML.

    Handles diff highlighting (Feature 27) and inline code annotations
    (Feature 32).
    """
    if annotations is None:
        annotations = {}

    # Diff-style line highlighting (Feature 27)
    is_diff = lang == "diff" or any(
        cl.startswith("+") or cl.startswith("-")
        for cl in code_lines
    )

    if is_diff:
        code_content = _render_diff_lines(code_lines)
    else:
        code_content = _escape_html("\n".join(code_lines))

    # Replace annotation markers // [N] or # [N] with badge elements
    # (Feature 32)
    if annotations:
        for num, note in annotations.items():
            escaped_note = _escape_html(note)
            badge = (
                f'<span class="code-annotation" data-note="{escaped_note}" '
                f'tabindex="0">{_escape_html(num)}</span>'
            )
            # Match escaped marker patterns in the code content
            # The markers were already HTML-escaped, so match escaped forms
            code_content = code_content.replace(
                f"// [{_escape_html(num)}]", badge
            )
            code_content = code_content.replace(
                f"# [{_escape_html(num)}]", badge
            )

    if lang:
        escaped_lang = _escape_html(lang)
        label = f'<div class="code-label">{escaped_lang}</div>'
        return (
            f'<div class="code-block">{label}'
            f'<pre tabindex="0"><code class="language-{escaped_lang}">'
            f"{code_content}</code></pre></div>"
        )
    return (
        f'<div class="code-block">'
        f'<pre tabindex="0"><code>{code_content}</code></pre>'
        f'</div>'
    )


def _group_code_tabs(html):
    """Group consecutive code blocks into a tabbed interface (Feature 31).

    Detects runs of consecutive <div class="code-block"> elements (with
    different language labels) and wraps them in a tab container.
    Only groups blocks that have language labels.
    """
    parts = html.split("\n")
    result = []
    i = 0

    while i < len(parts):
        part = parts[i]
        # Check if this is a code block with a language label
        if '<div class="code-block"><div class="code-label">' in part:
            # Collect consecutive code blocks with language labels
            group = [part]
            j = i + 1
            while (j < len(parts) and
                   '<div class="code-block"><div class="code-label">' in parts[j]):
                group.append(parts[j])
                j += 1

            if len(group) >= 2:
                # Build tabbed interface
                tabs = []
                panels = []
                for idx, block_html in enumerate(group):
                    # Extract language from the code-label div
                    label_match = re.search(
                        r'<div class="code-label">([^<]+)</div>', block_html
                    )
                    lang = label_match.group(1) if label_match else f"Tab {idx + 1}"
                    lang_id = lang.lower().replace(" ", "-")
                    active = " active" if idx == 0 else ""
                    tabs.append(
                        f'<button class="tab{active}" '
                        f'data-lang="{_escape_html(lang_id)}">'
                        f'{_escape_html(lang)}</button>'
                    )
                    panels.append(
                        f'<div class="tab-panel{active}" '
                        f'data-lang="{_escape_html(lang_id)}">'
                        f'{block_html}</div>'
                    )
                tab_bar = '<div class="tab-bar">' + "".join(tabs) + '</div>'
                result.append(
                    '<div class="code-tabs">'
                    + tab_bar
                    + "".join(panels)
                    + '</div>'
                )
                i = j
            else:
                result.append(part)
                i += 1
        else:
            result.append(part)
            i += 1

    return "\n".join(result)


def _apply_step_guides(html):
    """Add class="steps" to <ol> elements that follow step/guide/tutorial
    headings (Feature 33).

    Detects headings (h2, h3) containing keywords "step", "guide", or
    "tutorial" (case-insensitive) and adds the "steps" class to the
    immediately following <ol>.
    """
    return re.sub(
        r'(<h[23]\s[^>]*>.*?(?:step|guide|tutorial).*?</h[23]>)\n<ol>',
        r'\1\n<ol class="steps">',
        html,
        flags=re.IGNORECASE,
    )


def _wrap_api_entries(html):
    """Wrap h3/h4 + code block + description paragraph in API entry cards
    (Feature 48).

    When an h3 or h4 heading is immediately followed by a code-block div
    (a function/type signature) and optionally a <p> (description), wrap
    them together in a <div class="api-entry">.
    """
    return re.sub(
        r'(<h[34]\s[^>]*>.*?</h[34]>)\n'
        r'(<div class="code-block">.*?</div>)\n'
        r'(<p>.*?</p>)',
        r'<div class="api-entry">\1\n\2\n\3</div>',
        html,
    )


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


def _parse_blockquote(bq_lines):
    """Parse blockquote lines, detecting admonitions.

    If the first line matches [!TYPE] where TYPE is a recognized admonition,
    render as a styled admonition div. Otherwise render as a plain blockquote.
    """
    if not bq_lines:
        return ""

    # Check for admonition pattern: [!NOTE], [!WARNING], etc.
    admonition_match = re.match(r"^\[!(\w+)\]\s*$", bq_lines[0].strip())
    if admonition_match:
        admonition_type = admonition_match.group(1).upper()
        if admonition_type in _ADMONITION_TYPES:
            # Remaining lines are the admonition body
            body_lines = bq_lines[1:]
            # Skip leading empty lines
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
            body_md = "\n".join(body_lines)
            # Convert body to inline-formatted paragraphs
            body_parts = []
            for para in body_md.split("\n\n"):
                para = para.strip()
                if para:
                    body_parts.append(f"<p>{_inline_format(para)}</p>")
            body_html = "\n".join(body_parts) if body_parts else ""
            title = admonition_type.capitalize()
            css_class = admonition_type.lower()
            return (
                f'<div class="admonition {css_class}">\n'
                f'<p class="admonition-title">{title}</p>\n'
                f'{body_html}\n'
                f'</div>'
            )

    # Plain blockquote
    content = _inline_format(" ".join(line for line in bq_lines if line.strip()))
    return f"<blockquote><p>{content}</p></blockquote>"


def _render_diff_lines(code_lines):
    """Render code lines with diff-style highlighting.

    Lines starting with '+' get class "line-add", lines starting with '-'
    get class "line-remove". Other lines get a plain "line" span.
    """
    parts = []
    for line in code_lines:
        escaped = _escape_html(line)
        if line.startswith("+"):
            parts.append(f'<span class="line line-add">{escaped}</span>')
        elif line.startswith("-"):
            parts.append(f'<span class="line line-remove">{escaped}</span>')
        else:
            parts.append(f'<span class="line">{escaped}</span>')
    return "\n".join(parts)


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
            # Images: ![alt](src) -- must come before links
            formatted = re.sub(
                r"!\[([^\]]*)\]\(([^)]+)\)",
                r'<img src="\2" alt="\1" loading="lazy">',
                formatted,
            )
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


def _build_nav(markdown_files, frontmatter=None):
    """Build navigation items from the markdown file list.

    Sorts by frontmatter 'order' (lower = first), then alphabetically
    (Feature 35). Index.md is always first regardless of order.

    Returns list of dicts: {"label": str, "path": str (html path), "md_path": str}
    """
    if frontmatter is None:
        frontmatter = {}

    nav = []
    # Index first
    if "index.md" in markdown_files:
        nav.append({
            "label": "Home", "path": "index.html", "md_path": "index.md",
        })

    # Remaining pages: sort by frontmatter order, then alphabetically
    other_pages = [p for p in markdown_files.keys() if p != "index.md"]

    def sort_key(md_path):
        meta = frontmatter.get(md_path, {})
        order = meta.get("order")
        # Pages with order come first (sorted numerically),
        # pages without order come after (sorted alphabetically)
        if isinstance(order, (int, float)):
            return (0, order, md_path)
        return (1, 0, md_path)

    for md_path in sorted(other_pages, key=sort_key):
        # Use frontmatter title as label if available, else filename
        meta = frontmatter.get(md_path, {})
        label = meta.get("title") or md_path.replace(".md", "").replace("/", " / ")
        nav.append({
            "label": label,
            "path": _md_to_html_path(md_path),
            "md_path": md_path,
        })

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


def _extract_first_paragraph(page_html):
    """Extract text from the first <p> tag for use as a meta description.

    Strips HTML tags, unescapes HTML entities, trims whitespace, and
    truncates to 155 characters at a word boundary. Returns empty string
    if no paragraph found.
    """
    match = re.search(r"<p>(.*?)</p>", page_html, re.DOTALL)
    if not match:
        return ""
    text = re.sub(r"<[^>]+>", "", match.group(1))
    text = html.unescape(text)
    text = text.strip()
    if not text:
        return ""
    if len(text) <= 155:
        return text
    # Truncate at word boundary
    truncated = text[:155]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated


def _build_toc(body_html):
    """Extract h2/h3 headings from body HTML and build a TOC nested list.

    Returns HTML string for the TOC, or empty string if fewer than 2 headings.
    """
    headings = re.findall(
        r'<(h[23])\s+id="([^"]+)">[^<]*(?:<[^>]+>[^<]*)*?'
        r'<a[^>]*class="heading-link"[^>]*>[^<]*</a>(.*?)</\1>',
        body_html,
    )
    if len(headings) < 2:
        return ""

    items = []
    for tag, slug, text in headings:
        # Strip any remaining HTML tags from the heading text
        clean_text = re.sub(r"<[^>]+>", "", text).strip()
        level = tag  # "h2" or "h3"
        indent_cls = " toc-h3" if level == "h3" else ""
        items.append(
            f'<li class="toc-item{indent_cls}">'
            f'<a href="#{slug}">{_escape_html(clean_text)}</a></li>'
        )

    return '<nav class="toc-nav"><ul>' + "\n".join(items) + "</ul></nav>"


def _build_breadcrumbs(html_path, page_title, prefix):
    """Build breadcrumb HTML for a non-index page.

    Args:
        html_path: The current page's html path (e.g. "guide.html").
        page_title: The page title extracted from the first heading.
        prefix: Relative prefix back to root.

    Returns:
        Breadcrumb HTML string.
    """
    return (
        '<nav class="breadcrumbs" aria-label="Breadcrumbs">'
        f'<a href="{prefix}index.html">Home</a>'
        f' / <span>{_escape_html(page_title)}</span>'
        '</nav>'
    )


def _wrap_page(body_html, nav_html, title, project_name, version,
               css_href="style.css", custom_css_href=None,
               toc_html="", breadcrumbs=None, prev_page=None,
               next_page=None, prefix="", repo=None, source_path=None,
               base_url=None, page_path=None, description="",
               lang="en", date_modified=None, author=None,
               feed_url=None, summary=None):
    """Wrap converted HTML body in the full page template."""
    version_badge = (
        f'<span class="version-badge">v{_escape_html(version)}</span>'
        if version else ""
    )
    custom_css_tag = (
        f'\n<link rel="stylesheet" href="{custom_css_href}">'
        if custom_css_href else ""
    )
    # Atom feed link tag
    feed_tag = ""
    if feed_url:
        feed_tag = (
            f'\n<link rel="alternate" type="application/atom+xml" '
            f'title="{_escape_html(project_name)} Feed" href="{feed_url}">'
        )
    # Meta description tag (Feature 34)
    description_tag = ""
    if description:
        description_tag = (
            f'\n<meta name="description" content="{_escape_html(description)}">'
        )

    # Breadcrumbs (Feature 9)
    breadcrumbs_html = breadcrumbs if breadcrumbs else ""

    # Edit link (Feature 14)
    edit_link_html = ""
    if repo and source_path:
        repo_url = repo.rstrip("/")
        edit_url = f"{repo_url}/edit/main/{source_path}"
        edit_link_html = (
            f'<a class="edit-link" href="{edit_url}">'
            f'Edit this page on GitHub</a>'
        )

    # Prev/next page navigation (Feature 8)
    page_nav_html = ""
    if prev_page or next_page:
        prev_link = ""
        next_link = ""
        if prev_page:
            prev_href = prefix + prev_page["path"]
            prev_label = _escape_html(prev_page["label"])
            prev_link = (
                f'<a class="page-nav-prev" href="{prev_href}">'
                f'&larr; {prev_label}</a>'
            )
        if next_page:
            next_href = prefix + next_page["path"]
            next_label = _escape_html(next_page["label"])
            next_link = (
                f'<a class="page-nav-next" href="{next_href}">'
                f'{next_label} &rarr;</a>'
            )
        page_nav_html = (
            f'<nav class="page-nav">{prev_link}{next_link}</nav>'
        )

    # Feedback widget (Feature 30)
    feedback_html = (
        '<div class="feedback">'
        '<span>Was this page helpful?</span>'
        '<button class="feedback-yes" aria-label="Yes">Yes</button>'
        '<button class="feedback-no" aria-label="No">No</button>'
        '</div>'
    )

    # Format date_modified for display (e.g. "May 1, 2026")
    date_display_html = ""
    if date_modified:
        try:
            dt = datetime.strptime(date_modified, "%Y-%m-%d")
            formatted_date = dt.strftime("%B %-d, %Y")
        except (ValueError, TypeError):
            formatted_date = date_modified
        date_display_html = (
            f'<time datetime="{_escape_html(date_modified)}">'
            f'{_escape_html(formatted_date)}</time>'
        )

    # Page footer (Feature 18): combines edit link, feedback, and prev/next nav
    footer_html = ""
    footer_parts = []
    meta_parts = []
    if edit_link_html:
        meta_parts.append(edit_link_html)
    if date_display_html:
        meta_parts.append(f'Last updated {date_display_html}')
    if meta_parts:
        footer_parts.append(
            f'<div class="page-meta">{"".join(meta_parts)}</div>'
        )
    footer_parts.append(feedback_html)
    if page_nav_html:
        footer_parts.append(page_nav_html)
    footer_html = (
        f'<footer class="page-footer">'
        f'{"".join(footer_parts)}'
        f'</footer>'
    )

    # TOC aside (Feature 2) -- desktop only
    toc_aside = ""
    if toc_html:
        toc_aside = f'<aside class="toc">{toc_html}</aside>'

    # Mobile TOC disclosure (Feature 26) -- shown only on mobile via CSS
    mobile_toc_html = ""
    if toc_html:
        mobile_toc_html = (
            f'<details class="mobile-toc">'
            f'<summary>On this page</summary>'
            f'{toc_html}'
            f'</details>'
        )

    # Page summary block from frontmatter description (Phase 2.6)
    summary_html = ""
    if summary:
        summary_html = (
            f'<div class="page-summary">\n'
            f'  <p>{_escape_html(summary)}</p>\n'
            f'</div>'
        )

    # SEO: OG meta tags (Feature 21), canonical URL (Feature 22),
    # JSON-LD structured data (Feature 23)
    seo_tags = ""
    if base_url and page_path:
        canonical_url = f"{base_url}/{page_path}"
        escaped_title = _escape_html(title)
        escaped_project = _escape_html(project_name)
        slug = page_path.replace(".html", "")

        # Build author object for TechArticle
        if author and author.get("name"):
            author_obj = {
                "@type": author.get("type") or "Organization",
                "name": author["name"],
            }
            if author.get("url"):
                author_obj["url"] = author["url"]
        else:
            author_obj = {"@type": "Organization", "name": project_name}

        # TechArticle JSON-LD
        tech_article = {
            "@context": "https://schema.org",
            "@type": "TechArticle",
            "headline": title,
            "url": canonical_url,
            "author": author_obj,
        }
        if date_modified:
            tech_article["dateModified"] = date_modified

        escaped_desc = _escape_html(description)
        og_desc_tag = (
            f'\n<meta property="og:description" content="{escaped_desc}">'
            if description else ""
        )
        twitter_desc_tag = (
            f'\n<meta name="twitter:description" content="{escaped_desc}">'
            if description else ""
        )

        seo_tags = (
            f'\n<meta property="og:image" content="{base_url}/og-{slug}.svg">'
            f'\n<meta property="og:title" content="{escaped_title}'
            f' - {escaped_project}">'
            f'\n<meta property="og:type" content="article">'
            f'\n<meta property="og:url" content="{canonical_url}">'
            f'{og_desc_tag}'
            f'\n<meta name="twitter:card" content="summary">'
            f'\n<meta name="twitter:title" content="{escaped_title}'
            f' - {escaped_project}">'
            f'{twitter_desc_tag}'
            f'\n<link rel="canonical" href="{canonical_url}">'
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(tech_article)}'
            f'\n</script>'
        )

        # BreadcrumbList JSON-LD for non-index pages
        if breadcrumbs:
            breadcrumb_ld = {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "Home",
                        "item": f"{base_url}/index.html",
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": title,
                    },
                ],
            }
            seo_tags += (
                f'\n<script type="application/ld+json">\n'
                f'{json.dumps(breadcrumb_ld)}'
                f'\n</script>'
            )

        # WebSite + SearchAction JSON-LD for index page only
        if page_path == "index.html":
            website_ld = {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": project_name,
                "url": f"{base_url}/",
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": f"{base_url}/?q={{search_term_string}}",
                    "query-input": "required name=search_term_string",
                },
            }
            seo_tags += (
                f'\n<script type="application/ld+json">\n'
                f'{json.dumps(website_ld)}'
                f'\n</script>'
            )

        # SoftwareSourceCode JSON-LD when code blocks with language annotations exist
        lang_matches = re.findall(r'class="language-(\w+)"', body_html)
        if lang_matches:
            unique_langs = list(dict.fromkeys(lang_matches))
            prog_lang = unique_langs[0] if len(unique_langs) == 1 else unique_langs
            source_code_ld = {
                "@context": "https://schema.org",
                "@type": "SoftwareSourceCode",
                "programmingLanguage": prog_lang,
            }
            if repo:
                source_code_ld["codeRepository"] = repo
            seo_tags += (
                f'\n<script type="application/ld+json">\n'
                f'{json.dumps(source_code_ld)}'
                f'\n</script>'
            )

    # Theme toggle SVG icons (Feature 6)
    sun_icon = (
        '<svg class="icon-sun" width="18" height="18" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="5"/>'
        '<line x1="12" y1="1" x2="12" y2="3"/>'
        '<line x1="12" y1="21" x2="12" y2="23"/>'
        '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>'
        '<line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>'
        '<line x1="1" y1="12" x2="3" y2="12"/>'
        '<line x1="21" y1="12" x2="23" y2="12"/>'
        '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>'
        '<line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>'
        '</svg>'
    )
    moon_icon = (
        '<svg class="icon-moon" width="18" height="18" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
        '</svg>'
    )
    auto_icon = (
        '<svg class="icon-auto" width="18" height="18" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 2a10 10 0 0 1 0 20z" fill="currentColor"/>'
        '</svg>'
    )

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape_html(title)} - {_escape_html(project_name)}</title>{description_tag}
<link rel="icon" type="image/svg+xml" href="{prefix}favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://cdnjs.cloudflare.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{css_href}">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css" id="hljs-light">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github-dark.min.css" id="hljs-dark" media="(prefers-color-scheme: dark)">{custom_css_tag}{feed_tag}{seo_tags}
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/highlight.min.js"></script>
<script>hljs.highlightAll();</script>
<script>
// Theme toggle: apply saved preference before paint to avoid flash
(function() {{
  var saved = localStorage.getItem('selfdoc-theme');
  if (saved === 'light' || saved === 'dark') {{
    document.documentElement.setAttribute('data-theme', saved);
  }}
}})();
</script>
</head>
<body>
<a class="skip-link" href="#main-content">Skip to content</a>
<header class="topbar">
<div class="topbar-inner">
<button class="hamburger" aria-label="Toggle navigation" aria-expanded="false">
<span></span><span></span><span></span>
</button>
<a class="project-name" href="{prefix}index.html">{_escape_html(project_name)}</a>
{version_badge}
<button class="theme-toggle" aria-label="Toggle theme">
{sun_icon}{moon_icon}{auto_icon}
</button>
</div>
</header>
<div class="layout">
<nav class="sidebar" id="sidebar">
<ul class="nav-list">
{nav_html}
</ul>
</nav>
<main class="content" id="main-content">
<article>
{breadcrumbs_html}
{mobile_toc_html}
{summary_html}
{body_html}
{footer_html}
</article>
</main>
{toc_aside}
</div>
<footer class="site-footer">
<p>Built with <a href="https://github.com/smm-h/selfdoc">selfdoc</a></p>
</footer>
<script>
// Theme toggle (Feature 6)
(function() {{
  var btn = document.querySelector('.theme-toggle');
  var states = ['system', 'light', 'dark'];
  function getState() {{
    var s = localStorage.getItem('selfdoc-theme');
    return (s === 'light' || s === 'dark') ? s : 'system';
  }}
  function apply(state) {{
    if (state === 'light' || state === 'dark') {{
      document.documentElement.setAttribute('data-theme', state);
      localStorage.setItem('selfdoc-theme', state);
    }} else {{
      document.documentElement.removeAttribute('data-theme');
      localStorage.removeItem('selfdoc-theme');
    }}
    btn.setAttribute('data-state', state);
    // Update highlight.js stylesheet media attributes
    var hljsLight = document.getElementById('hljs-light');
    var hljsDark = document.getElementById('hljs-dark');
    if (hljsLight && hljsDark) {{
      if (state === 'dark') {{
        hljsLight.media = 'not all';
        hljsDark.media = 'all';
      }} else if (state === 'light') {{
        hljsLight.media = 'all';
        hljsDark.media = 'not all';
      }} else {{
        hljsLight.media = '(prefers-color-scheme: light)';
        hljsDark.media = '(prefers-color-scheme: dark)';
      }}
    }}
  }}
  apply(getState());
  btn.addEventListener('click', function() {{
    var cur = getState();
    var next = states[(states.indexOf(cur) + 1) % states.length];
    apply(next);
  }});
}})();

// Copy button on code blocks (Feature 5)
document.querySelectorAll('pre').forEach(function(pre) {{
  var code = pre.querySelector('code');
  if (!code) return;
  var btn = document.createElement('button');
  btn.className = 'copy-btn';
  btn.textContent = 'Copy';
  btn.addEventListener('click', function() {{
    navigator.clipboard.writeText(code.textContent).then(function() {{
      btn.textContent = 'Copied!';
      setTimeout(function() {{ btn.textContent = 'Copy'; }}, 2000);
    }});
  }});
  pre.style.position = 'relative';
  pre.appendChild(btn);
}});

// Scrollspy for TOC (Feature 2)
(function() {{
  var tocLinks = document.querySelectorAll('.toc a');
  if (!tocLinks.length) return;
  var observer = new IntersectionObserver(function(entries) {{
    entries.forEach(function(entry) {{
      var id = entry.target.getAttribute('id');
      var link = document.querySelector('.toc a[href="#' + id + '"]');
      if (link) {{
        if (entry.isIntersecting) {{
          tocLinks.forEach(function(a) {{ a.classList.remove('active'); }});
          link.classList.add('active');
        }}
      }}
    }});
  }}, {{ rootMargin: '-80px 0px -80% 0px' }});
  document.querySelectorAll('main h2[id], main h3[id]').forEach(function(h) {{
    observer.observe(h);
  }});
}})();

// Mobile sidebar toggle (Feature 25)
(function() {{
  var toggle = document.querySelector('.hamburger');
  var sidebar = document.getElementById('sidebar');
  if (!toggle || !sidebar) return;
  function openSidebar() {{
    document.body.classList.add('sidebar-open');
    toggle.setAttribute('aria-expanded', 'true');
  }}
  function closeSidebar() {{
    document.body.classList.remove('sidebar-open');
    toggle.setAttribute('aria-expanded', 'false');
  }}
  toggle.addEventListener('click', function() {{
    if (document.body.classList.contains('sidebar-open')) {{
      closeSidebar();
    }} else {{
      openSidebar();
    }}
  }});
  // Close when clicking outside (overlay area)
  document.addEventListener('click', function(e) {{
    if (document.body.classList.contains('sidebar-open') &&
        !sidebar.contains(e.target) && !toggle.contains(e.target)) {{
      closeSidebar();
    }}
  }});
  // Close when a nav link is clicked
  sidebar.querySelectorAll('a').forEach(function(link) {{
    link.addEventListener('click', function() {{
      closeSidebar();
    }});
  }});
}})();

// Cmd+K search (Feature 19)
(function() {{
  var dialog = document.getElementById('search-dialog');
  if (!dialog) return;
  var input = dialog.querySelector('.search-input');
  var resultsList = dialog.querySelector('.search-results');
  var searchIndex = null;
  var activeIdx = -1;

  function loadIndex() {{
    if (searchIndex) return Promise.resolve(searchIndex);
    return fetch('{prefix}search-index.json')
      .then(function(r) {{ return r.json(); }})
      .then(function(data) {{ searchIndex = data; return data; }});
  }}

  function openSearch() {{
    loadIndex();
    dialog.showModal();
    input.value = '';
    resultsList.innerHTML = '';
    activeIdx = -1;
    input.focus();
  }}

  function closeSearch() {{
    dialog.close();
  }}

  function renderResults(query) {{
    resultsList.innerHTML = '';
    activeIdx = -1;
    if (!query || !searchIndex) return;
    var q = query.toLowerCase();
    var matches = searchIndex.filter(function(entry) {{
      return entry.title.toLowerCase().indexOf(q) !== -1 ||
             entry.body.toLowerCase().indexOf(q) !== -1;
    }}).slice(0, 10);
    matches.forEach(function(entry, idx) {{
      var li = document.createElement('li');
      li.className = 'search-result-item';
      var a = document.createElement('a');
      a.href = '{prefix}' + entry.path;
      var titleEl = document.createElement('div');
      titleEl.className = 'search-result-title';
      titleEl.textContent = entry.title;
      var snippet = document.createElement('div');
      snippet.className = 'search-result-snippet';
      var bodyLower = entry.body.toLowerCase();
      var pos = bodyLower.indexOf(q);
      if (pos !== -1) {{
        var start = Math.max(0, pos - 40);
        var end = Math.min(entry.body.length, pos + q.length + 60);
        snippet.textContent = (start > 0 ? '...' : '') +
          entry.body.substring(start, end) +
          (end < entry.body.length ? '...' : '');
      }} else {{
        snippet.textContent = entry.body.substring(0, 100) +
          (entry.body.length > 100 ? '...' : '');
      }}
      a.appendChild(titleEl);
      a.appendChild(snippet);
      li.appendChild(a);
      resultsList.appendChild(li);
    }});
  }}

  function setActive(idx) {{
    var items = resultsList.querySelectorAll('.search-result-item');
    items.forEach(function(li) {{ li.classList.remove('active'); }});
    if (idx >= 0 && idx < items.length) {{
      activeIdx = idx;
      items[idx].classList.add('active');
      items[idx].scrollIntoView({{ block: 'nearest' }});
    }}
  }}

  document.addEventListener('keydown', function(e) {{
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {{
      e.preventDefault();
      if (dialog.open) closeSearch();
      else openSearch();
    }}
  }});

  dialog.addEventListener('click', function(e) {{
    if (e.target === dialog) closeSearch();
  }});

  input.addEventListener('input', function() {{
    renderResults(input.value);
  }});

  input.addEventListener('keydown', function(e) {{
    var items = resultsList.querySelectorAll('.search-result-item');
    if (e.key === 'ArrowDown') {{
      e.preventDefault();
      setActive(Math.min(activeIdx + 1, items.length - 1));
    }} else if (e.key === 'ArrowUp') {{
      e.preventDefault();
      setActive(Math.max(activeIdx - 1, 0));
    }} else if (e.key === 'Enter' && activeIdx >= 0) {{
      e.preventDefault();
      var link = items[activeIdx].querySelector('a');
      if (link) window.location.href = link.href;
    }} else if (e.key === 'Escape') {{
      closeSearch();
    }}
  }});
}})();

// Prefetch links on hover (Feature 20)
document.querySelectorAll('.sidebar a, .page-nav a').forEach(function(link) {{
  link.addEventListener('mouseenter', function() {{
    var href = link.getAttribute('href');
    if (href && !document.querySelector('link[href="' + href + '"]')) {{
      var prefetch = document.createElement('link');
      prefetch.rel = 'prefetch';
      prefetch.href = href;
      document.head.appendChild(prefetch);
    }}
  }}, {{ once: true }});
}});

// Feedback widget (Feature 30)
(function() {{
  var widget = document.querySelector('.feedback');
  if (!widget) return;
  var key = 'selfdoc-feedback-' + location.pathname;
  if (localStorage.getItem(key)) {{
    widget.innerHTML = '<span>Thanks for your feedback!</span>';
    return;
  }}
  widget.querySelectorAll('button').forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      localStorage.setItem(key, btn.className);
      widget.innerHTML = '<span>Thanks for your feedback!</span>';
    }});
  }});
}})();

// Code tabs: switch between language panels (Feature 31)
(function() {{
  document.querySelectorAll('.code-tabs').forEach(function(tabGroup) {{
    var buttons = tabGroup.querySelectorAll('.tab-bar .tab');
    var panels = tabGroup.querySelectorAll('.tab-panel');
    buttons.forEach(function(btn) {{
      btn.addEventListener('click', function() {{
        var lang = btn.getAttribute('data-lang');
        // Deactivate all tabs and panels in this group
        buttons.forEach(function(b) {{ b.classList.remove('active'); }});
        panels.forEach(function(p) {{ p.classList.remove('active'); }});
        // Activate the selected tab and panel
        btn.classList.add('active');
        var panel = tabGroup.querySelector('.tab-panel[data-lang="' + lang + '"]');
        if (panel) panel.classList.add('active');
        // Persist preference in localStorage
        localStorage.setItem('selfdoc-tab-' + lang, 'true');
        // Sync same-language tabs across all tab groups on the page
        document.querySelectorAll('.code-tabs').forEach(function(otherGroup) {{
          if (otherGroup === tabGroup) return;
          var otherBtn = otherGroup.querySelector('.tab-bar .tab[data-lang="' + lang + '"]');
          if (otherBtn) otherBtn.click();
        }});
      }});
    }});
    // Restore persisted language preference
    buttons.forEach(function(btn) {{
      var lang = btn.getAttribute('data-lang');
      if (localStorage.getItem('selfdoc-tab-' + lang)) {{
        btn.click();
      }}
    }});
  }});
}})();

// Embedded live code playground (Feature 41)
// Adds a "Run" button to Go and Python code blocks linking to online playgrounds.
(function() {{
  document.querySelectorAll('.code-block').forEach(function(block) {{
    var label = block.querySelector('.code-label');
    if (!label) return;
    var lang = label.textContent.trim().toLowerCase();
    var code = block.querySelector('code');
    if (!code) return;
    var url = null;
    if (lang === 'go') {{
      url = 'https://go.dev/play/p/?body=' + encodeURIComponent(code.textContent);
    }} else if (lang === 'python') {{
      url = 'https://www.online-python.com/';
    }}
    if (url) {{
      var btn = document.createElement('a');
      btn.className = 'run-btn';
      btn.href = url;
      btn.target = '_blank';
      btn.rel = 'noopener';
      btn.textContent = 'Run';
      block.querySelector('pre').appendChild(btn);
    }}
  }});
}})();

// Feature 42: API playground / "Try it" panel -- future feature requiring a running backend.
// Feature 43: Browser/platform compatibility tables -- future feature, not relevant for most projects.
</script>
<dialog class="search-dialog" id="search-dialog">
<div class="search-inner">
<input type="search" class="search-input" placeholder="Search docs... (Cmd+K)" autofocus>
<ul class="search-results"></ul>
</div>
</dialog>
</body>
</html>
"""
