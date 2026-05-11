"""Convert Markdown files to static HTML with a built-in minimal converter.

No external dependencies -- handles headings, code blocks, inline code,
paragraphs, lists, links, bold/italic, tables, blockquotes, and admonitions.
"""

import re

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
        title = _extract_title(md_content, project_name)
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

        full_html = _wrap_page(
            body_html, nav_html, title, project_name, version,
            css_href, custom_css_href,
            toc_html=toc_html,
            breadcrumbs=breadcrumbs,
            prev_page=prev_page,
            next_page=next_page,
            prefix=prefix,
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

    Returns list of dicts: {"label": str, "path": str (html path), "md_path": str}
    """
    nav = []
    # Index first
    if "index.md" in markdown_files:
        nav.append({
            "label": "Home", "path": "index.html", "md_path": "index.md",
        })

    # Remaining pages sorted alphabetically
    for md_path in sorted(markdown_files.keys()):
        if md_path == "index.md":
            continue
        # Use the filename (without extension) as the label
        label = md_path.replace(".md", "").replace("/", " / ")
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
               next_page=None, prefix=""):
    """Wrap converted HTML body in the full page template."""
    version_badge = (
        f'<span class="version-badge">v{_escape_html(version)}</span>'
        if version else ""
    )
    custom_css_tag = (
        f'\n<link rel="stylesheet" href="{custom_css_href}">'
        if custom_css_href else ""
    )

    # Breadcrumbs (Feature 9)
    breadcrumbs_html = breadcrumbs if breadcrumbs else ""

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

    # TOC aside (Feature 2)
    toc_aside = ""
    if toc_html:
        toc_aside = f'<aside class="toc">{toc_html}</aside>'

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
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape_html(title)} - {_escape_html(project_name)}</title>
<link rel="stylesheet" href="{css_href}">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css" id="hljs-light">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github-dark.min.css" id="hljs-dark" media="(prefers-color-scheme: dark)">{custom_css_tag}
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
<button class="sidebar-toggle" aria-label="Toggle navigation">
<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
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
{breadcrumbs_html}
{body_html}
{page_nav_html}
</main>
{toc_aside}
</div>
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

// Mobile sidebar toggle
(function() {{
  var toggle = document.querySelector('.sidebar-toggle');
  var sidebar = document.getElementById('sidebar');
  if (toggle && sidebar) {{
    toggle.addEventListener('click', function() {{
      sidebar.classList.toggle('open');
    }});
    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', function(e) {{
      if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {{
        sidebar.classList.remove('open');
      }}
    }});
  }}
}})();
</script>
</body>
</html>
"""
