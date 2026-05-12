"""Convert Markdown files to static HTML with a built-in minimal converter.

No external dependencies -- handles headings, code blocks, inline code,
paragraphs, lists, links, bold/italic, tables, blockquotes, and admonitions.
Syntax highlighting uses Pygments when available (optional dependency).
"""

import html
import json
import re
from datetime import datetime

from selfdoc.themes import get_theme

# Pygments is optional: when available, code blocks get build-time syntax
# highlighting.  When missing, code blocks render as plain text.
try:
    from pygments import highlight as pygments_highlight
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

# Admonition types recognized in GitHub-flavored blockquotes (> [!TYPE])
_ADMONITION_TYPES = {"NOTE", "TIP", "WARNING", "CAUTION", "IMPORTANT"}


def _minify_js(js_text):
    """Minify JavaScript by removing comments and collapsing whitespace.

    Conservative approach: avoids breaking URLs containing ``//`` and
    preserves single spaces between identifiers.
    """
    # Remove multi-line comments /* ... */
    js_text = re.sub(r"/\*.*?\*/", "", js_text, flags=re.DOTALL)
    # Remove single-line comments (// ... to end of line) but not inside
    # strings and not URLs (https://, http://).  Only strip when //
    # appears at the start of a line or after whitespace/semicolons.
    js_text = re.sub(r"(?m)(?<=^)[ \t]*//(?!.*['\"]).*$", "", js_text)
    js_text = re.sub(r"(?m)(?<=[;{}\n])[ \t]*//(?!.*['\"]).*$", "", js_text)
    # Collapse runs of whitespace (but keep at least one space between
    # word characters so identifiers don't merge)
    js_text = re.sub(r"[ \t]+", " ", js_text)
    # Remove whitespace around structural characters
    js_text = re.sub(r"\s*([{}();,=])\s*", r"\1", js_text)
    # Strip blank lines
    js_text = re.sub(r"\n{2,}", "\n", js_text)
    js_text = js_text.strip()
    return js_text


def _generate_search_js():
    """Return the search JS as a standalone IIFE string.

    Reads the path prefix from ``data-search-prefix`` on the search dialog
    element so the script is page-independent.  The search index is fetched
    lazily on first dialog open (not on page load).
    """
    return (
        "// Cmd+K search (Feature 19)\n"
        "(function() {\n"
        "  var dialog = document.getElementById('search-dialog');\n"
        "  if (!dialog) return;\n"
        "  var searchPrefix = dialog.getAttribute('data-search-prefix') || '';\n"
        "  var input = dialog.querySelector('.search-input');\n"
        "  var resultsList = dialog.querySelector('.search-results');\n"
        "  var searchIndex = null;\n"
        "  var activeIdx = -1;\n"
        "\n"
        "  function loadIndex() {\n"
        "    if (searchIndex) return Promise.resolve(searchIndex);\n"
        "    return fetch(searchPrefix + 'search-index.json')\n"
        "      .then(function(r) { return r.json(); })\n"
        "      .then(function(data) { searchIndex = data; return data; });\n"
        "  }\n"
        "\n"
        "  function openSearch() {\n"
        "    loadIndex();\n"
        "    dialog.showModal();\n"
        "    input.value = '';\n"
        "    resultsList.innerHTML = '';\n"
        "    activeIdx = -1;\n"
        "    input.focus();\n"
        "  }\n"
        "\n"
        "  function closeSearch() {\n"
        "    dialog.close();\n"
        "  }\n"
        "\n"
        "  function renderResults(query) {\n"
        "    resultsList.innerHTML = '';\n"
        "    activeIdx = -1;\n"
        "    if (!query || !searchIndex) return;\n"
        "    var q = query.toLowerCase();\n"
        "    var matches = searchIndex.filter(function(entry) {\n"
        "      return entry.title.toLowerCase().indexOf(q) !== -1 ||\n"
        "             entry.body.toLowerCase().indexOf(q) !== -1;\n"
        "    }).slice(0, 10);\n"
        "    matches.forEach(function(entry, idx) {\n"
        "      var li = document.createElement('li');\n"
        "      li.className = 'search-result-item';\n"
        "      li.setAttribute('role', 'option');\n"
        "      li.id = 'search-result-' + idx;\n"
        "      var a = document.createElement('a');\n"
        "      a.href = searchPrefix + entry.path;\n"
        "      var titleEl = document.createElement('div');\n"
        "      titleEl.className = 'search-result-title';\n"
        "      titleEl.textContent = entry.title;\n"
        "      var snippet = document.createElement('div');\n"
        "      snippet.className = 'search-result-snippet';\n"
        "      var bodyLower = entry.body.toLowerCase();\n"
        "      var pos = bodyLower.indexOf(q);\n"
        "      if (pos !== -1) {\n"
        "        var start = Math.max(0, pos - 40);\n"
        "        var end = Math.min(entry.body.length, pos + q.length + 60);\n"
        "        snippet.textContent = (start > 0 ? '...' : '') +\n"
        "          entry.body.substring(start, end) +\n"
        "          (end < entry.body.length ? '...' : '');\n"
        "      } else {\n"
        "        snippet.textContent = entry.body.substring(0, 100) +\n"
        "          (entry.body.length > 100 ? '...' : '');\n"
        "      }\n"
        "      a.appendChild(titleEl);\n"
        "      a.appendChild(snippet);\n"
        "      a.addEventListener('click', function() { closeSearch(); });\n"
        "      li.appendChild(a);\n"
        "      resultsList.appendChild(li);\n"
        "    });\n"
        "    if (matches.length === 0 && q) {\n"
        "      var noLi = document.createElement('li');\n"
        "      noLi.className = 'search-no-results';\n"
        "      noLi.textContent = 'No results for \"' + q + '\"';\n"
        "      resultsList.appendChild(noLi);\n"
        "    }\n"
        "  }\n"
        "\n"
        "  function setActive(idx) {\n"
        "    var items = resultsList.querySelectorAll('.search-result-item');\n"
        "    items.forEach(function(li) { li.classList.remove('active'); });\n"
        "    if (idx >= 0 && idx < items.length) {\n"
        "      activeIdx = idx;\n"
        "      items[idx].classList.add('active');\n"
        "      items[idx].scrollIntoView({ block: 'nearest' });\n"
        "      input.setAttribute('aria-activedescendant', items[idx].id);\n"
        "    } else {\n"
        "      input.removeAttribute('aria-activedescendant');\n"
        "    }\n"
        "  }\n"
        "\n"
        "  var trigger = document.querySelector('.search-trigger, .search-bar-trigger');\n"
        "  if (trigger) {\n"
        "    trigger.addEventListener('click', function(e) {\n"
        "      e.preventDefault();\n"
        "      openSearch();\n"
        "    });\n"
        "  }\n"
        "\n"
        "  document.addEventListener('keydown', function(e) {\n"
        "    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {\n"
        "      e.preventDefault();\n"
        "      if (dialog.open) closeSearch();\n"
        "      else openSearch();\n"
        "    }\n"
        "  });\n"
        "\n"
        "  dialog.addEventListener('click', function(e) {\n"
        "    if (e.target === dialog) closeSearch();\n"
        "  });\n"
        "\n"
        "  input.addEventListener('input', function() {\n"
        "    renderResults(input.value);\n"
        "  });\n"
        "\n"
        "  input.addEventListener('keydown', function(e) {\n"
        "    var items = resultsList.querySelectorAll('.search-result-item');\n"
        "    if (e.key === 'ArrowDown') {\n"
        "      e.preventDefault();\n"
        "      setActive(Math.min(activeIdx + 1, items.length - 1));\n"
        "    } else if (e.key === 'ArrowUp') {\n"
        "      e.preventDefault();\n"
        "      setActive(Math.max(activeIdx - 1, 0));\n"
        "    } else if (e.key === 'Enter' && activeIdx >= 0) {\n"
        "      e.preventDefault();\n"
        "      var link = items[activeIdx].querySelector('a');\n"
        "      if (link) window.location.href = link.href;\n"
        "    } else if (e.key === 'Escape') {\n"
        "      closeSearch();\n"
        "    }\n"
        "  });\n"
        "})();\n"
    )


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


def generate_pygments_css():
    """Generate Pygments CSS rules for light and dark mode.

    Uses 'default' style for light mode and 'monokai' for dark mode.
    Scoped to ``.code-block code`` to match the HTML structure produced
    by ``_render_code_block()``.

    Returns the CSS string, or an empty string if Pygments is not installed.
    """
    if not HAS_PYGMENTS:
        return ""
    scope = ".code-block code"
    light = HtmlFormatter(style="default").get_style_defs(scope)
    dark = HtmlFormatter(style="monokai").get_style_defs(scope)
    return (
        f"{light}\n\n"
        f"@media (prefers-color-scheme: dark) {{\n"
        f"  :root:not([data-theme='light']) {{\n"
        f"    {dark}\n"
        f"  }}\n"
        f"}}\n\n"
        f"[data-theme='dark'] {{\n"
        f"  {dark}\n"
        f"}}"
    )


def generate_html(markdown_files, project_name=None, version=None,
                   has_custom_css=False, repo=None, docs_dir_name="docs/",
                   base_url=None, frontmatter=None, lang="en",
                   page_dates=None, author=None, feed_url=None,
                   critical_css=None, twitter_site=None, search=None,
                   feedback=None, branch="main"):
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
        page_dates: Dict mapping relative paths to (published, modified) tuples (optional).
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

    # Flatten nav_items for page iteration order (prev/next links)
    flat_nav = _flatten_nav(nav_items)

    html_files = {}
    for page_idx, (md_path, md_content) in enumerate(
        # Iterate in nav order so prev/next matches sidebar
        [(item["md_path"], markdown_files[item["md_path"]])
         for item in flat_nav if item["md_path"] in markdown_files]
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

        # Truncate description for meta tag (SEO best practice: <= 155 chars)
        # The summary block can still show the full text via `summary`.
        description = _truncate_description(description)

        css_href = prefix + "style.css"
        custom_css_href = (prefix + "custom.css") if has_custom_css else None

        # Prev/next page links (Feature 8)
        prev_page = flat_nav[page_idx - 1] if page_idx > 0 else None
        next_page = (flat_nav[page_idx + 1]
                     if page_idx < len(flat_nav) - 1 else None)

        # Breadcrumbs (Feature 9): not shown on index.html
        breadcrumbs = None
        if html_path != "index.html":
            breadcrumbs = _build_breadcrumbs(html_path, title, prefix)

        # Extract TOC from the body HTML (Feature 2)
        toc_html = _build_toc(body_html)

        # Source path for "Edit this page" link (Feature 14)
        source_path = docs_dir_name.rstrip("/") + "/" + md_path

        # Date published and modified for this page (Wave 2 date infrastructure)
        date_tuple = page_dates.get(md_path)
        date_published = date_tuple[0] if date_tuple else None
        date_modified = date_tuple[1] if date_tuple else None

        # Compute feed href relative to this page's depth
        page_feed_url = (prefix + feed_url) if feed_url else None

        # Schema type from frontmatter (e.g. "itemlist" for ItemList JSON-LD)
        schema = page_meta.get("schema")

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
            date_published=date_published,
            date_modified=date_modified,
            author=author,
            feed_url=page_feed_url,
            summary=frontmatter_description,
            critical_css=critical_css,
            schema=schema,
            twitter_site=twitter_site,
            search=search,
            feedback=feedback,
            branch=branch,
        )
        html_files[html_path] = full_html

    return html_files


def generate_404_page(project_name=None, version=None, has_custom_css=False,
                      nav_items=None, repo=None, base_url=None, lang="en",
                      feed_url=None, critical_css=None):
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

    # Popular pages section (first 5 nav items, flattened)
    flat_nav = _flatten_nav(nav_items)
    popular_html = ""
    if flat_nav:
        popular_links = []
        for item in flat_nav[:5]:
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
        page_path=None,
        lang=lang,
        feed_url=feed_url,
        critical_css=critical_css,
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
            readable = re.sub(r"<[^>]+>", "", content).replace("_", " ")
            anchor = (
                f'<a class="heading-link" href="#{slug}"'
                f' aria-label="Link to section: {_escape_html(readable)}">#</a>'
            )
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
            table_html = _parse_table(table_lines)
            # Add caption from most recent heading for accessibility
            caption_text = ""
            for prev_part in reversed(html_parts):
                heading_m = re.search(
                    r"<h[1-6][^>]*>.*?</a>(.*?)</h[1-6]>", prev_part
                )
                if heading_m:
                    caption_text = re.sub(r"<[^>]+>", "", heading_m.group(1)).strip()
                    break
            if caption_text:
                table_html = table_html.replace(
                    "<table>",
                    f'<table><caption class="sr-only">'
                    f"{_escape_html(caption_text)}</caption>",
                    1,
                )
            html_parts.append(
                '<div class="table-wrap">'
                + table_html
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

        # Definition list: a non-blank line followed by `: ` definition lines
        if (line.strip()
                and i + 1 < len(lines)
                and lines[i + 1].startswith(": ")):
            dl_items = []
            while i < len(lines):
                term_line = lines[i].strip()
                if not term_line:
                    break
                # Check that next line is a definition
                if i + 1 >= len(lines) or not lines[i + 1].startswith(": "):
                    break
                term_html = _inline_format(term_line)
                dl_items.append(f"<dt><dfn>{term_html}</dfn></dt>")
                i += 1
                # Collect one or more `: ` definition lines
                while i < len(lines) and lines[i].startswith(": "):
                    defn_text = lines[i][2:]
                    dl_items.append(f"<dd>{_inline_format(defn_text)}</dd>")
                    i += 1
                # Skip blank lines between term/definition pairs
                while i < len(lines) and not lines[i].strip():
                    i += 1
            html_parts.append(
                '<div class="glossary">\n<dl>\n'
                + "\n".join(dl_items)
                + "\n</dl>\n</div>"
            )
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
            # Don't absorb a line if the next line starts a definition
            if (i + 1 < len(lines)
                    and lines[i + 1].startswith(": ")):
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

    # Post-process: auto-detect definitional patterns after headings and
    # wrap the subject in <dfn> tags (Phase 6A)
    result = _apply_definitions(result)

    # Post-process: mark the first image as high-priority LCP candidate
    # (Phase 3.3). All images start with loading="lazy" from _inline_format;
    # promote the first one to eager loading with high fetchpriority.
    result = re.sub(
        r'loading="lazy"',
        'fetchpriority="high" loading="eager"',
        result,
        count=1,
    )

    return result


def _render_code_block(lang, code_lines, annotations=None):
    """Render a single fenced code block to HTML.

    Handles diff highlighting (Feature 27), inline code annotations
    (Feature 32), and build-time syntax highlighting via Pygments
    (Wave 3 Phase 0).
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
    elif HAS_PYGMENTS and lang:
        # Build-time syntax highlighting via Pygments.  The formatter
        # uses nowrap=True so we keep our own <pre><code> wrapper.
        # Pygments handles HTML escaping internally.
        try:
            lexer = get_lexer_by_name(lang)
            formatter = HtmlFormatter(nowrap=True)
            code_content = pygments_highlight(
                "\n".join(code_lines), lexer, formatter
            )
            # pygments_highlight appends a trailing newline; strip it so
            # we don't get an extra blank line inside <code>.
            code_content = code_content.rstrip("\n")
        except Exception:
            # Unknown language or Pygments error -- fall back to plain text
            code_content = _escape_html("\n".join(code_lines))
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
                    selected = "true" if idx == 0 else "false"
                    escaped_lang_id = _escape_html(lang_id)
                    tabs.append(
                        f'<button class="tab{active}" '
                        f'role="tab" '
                        f'id="tab-{escaped_lang_id}" '
                        f'aria-selected="{selected}" '
                        f'aria-controls="panel-{escaped_lang_id}" '
                        f'data-lang="{escaped_lang_id}">'
                        f'{_escape_html(lang)}</button>'
                    )
                    panels.append(
                        f'<div class="tab-panel{active}" '
                        f'role="tabpanel" '
                        f'id="panel-{escaped_lang_id}" '
                        f'aria-labelledby="tab-{escaped_lang_id}" '
                        f'data-lang="{escaped_lang_id}">'
                        f'{block_html}</div>'
                    )
                tab_bar = '<div class="tab-bar" role="tablist">' + "".join(tabs) + '</div>'
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


def _apply_definitions(html):
    """Wrap definitional subjects in <dfn> tags when they follow headings.

    Detects patterns like "X is a ...", "X refers to ...", "X means ...",
    "X represents ...", or the inverted "A/An X is ..." in the first <p>
    after an <h2> or <h3> heading, and wraps X in <dfn>.
    """
    # Match: <h2/h3 ...>...</h2/h3> followed by optional whitespace then <p>
    # that starts with a definitional pattern.
    #
    # The subject (X) can be:
    #   - Plain text (one or more words)
    #   - Wrapped in <code>...</code>
    #   - Wrapped in <strong>...</strong>
    #
    # Definitional verbs: "is a", "is an", "is the", "refers to",
    # "means", "represents"

    # Pattern for the subject: plain words, or <code>...</code>,
    # or <strong>...</strong>
    subject_plain = r"[A-Za-z][A-Za-z0-9 ]*?"
    subject_code = r"<code>[^<]+</code>"
    subject_strong = r"<strong>[^<]+</strong>"
    subject = rf"(?:{subject_code}|{subject_strong}|{subject_plain})"

    # Definitional verbs
    direct_verb = r"(?:is\s+(?:a|an|the)\b|refers\s+to\b|means\b|represents\b)"

    # Inverted form: "A/An Subject verb ..."
    inverted_pattern = (
        rf"(<h[23]\s[^>]*>.*?</h[23]>)\n"
        rf"<p>(?:A|An)\s+({subject})\s+({direct_verb})"
    )

    # Direct form pattern (excludes "A/An " starts to avoid overlap)
    direct_pattern = (
        rf"(<h[23]\s[^>]*>.*?</h[23]>)\n"
        rf"<p>(?!An?\s)({subject})\s+({direct_verb})"
    )

    def _wrap_subject(match_obj, inverted=False):
        heading = match_obj.group(1)
        subject_text = match_obj.group(2)
        verb = match_obj.group(3)

        # Wrap subject in <dfn>. If it's inside <code> or <strong>,
        # wrap the outer tag.
        dfn_subject = f"<dfn>{subject_text}</dfn>"

        if inverted:
            # Determine original article from context
            # Re-read the full match to get the article
            full = match_obj.group(0)
            article = "An" if full.startswith(heading + "\n<p>An ") else "A"
            return f"{heading}\n<p>{article} <dfn>{subject_text}</dfn> {verb}"
        return f"{heading}\n<p>{dfn_subject} {verb}"

    # Apply inverted form first (more specific), then direct form
    result = re.sub(inverted_pattern, lambda m: _wrap_subject(m, inverted=True), html)
    result = re.sub(direct_pattern, lambda m: _wrap_subject(m, inverted=False), result)

    return result


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
            # Inline stat/data markup: ==value== -> <data value="value">value</data>
            formatted = re.sub(
                r"==([^=]+?)==",
                r'<data value="\1">\1</data>',
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

    Pages in subdirectories are grouped under collapsible nav groups.
    Group title defaults to the titlecased directory name but can be
    overridden via ``nav_group`` frontmatter.  ``nav_order`` frontmatter
    controls sort order within a group (default 0, ties broken
    alphabetically).

    Returns list of dicts.  Ungrouped items:
        {"label": str, "path": str, "md_path": str}
    Group items:
        {"group": str, "slug": str, "items": [ungrouped-style dicts]}
    """
    if frontmatter is None:
        frontmatter = {}

    # Collect all items with their metadata
    ungrouped = []  # top-level pages (no subdirectory)
    groups = {}     # dir_name -> list of item dicts

    for md_path in markdown_files:
        meta = frontmatter.get(md_path, {})
        label = meta.get("title") or md_path.replace(".md", "").replace("/", " / ")
        item = {
            "label": label,
            "path": _md_to_html_path(md_path),
            "md_path": md_path,
        }

        # Determine group membership
        parts = md_path.split("/")
        if len(parts) > 1:
            # Subdirectory page -- group by first directory component
            dir_name = parts[0]
            # nav_group frontmatter overrides group title
            group_title = meta.get("nav_group") or dir_name.replace(
                "-", " ").replace("_", " ").title()
            nav_order = meta.get("nav_order", 0)
            if not isinstance(nav_order, (int, float)):
                nav_order = 0
            item["_nav_order"] = nav_order

            if dir_name not in groups:
                groups[dir_name] = {"title": group_title, "items": []}
            # If a later page overrides the group title, update it
            if meta.get("nav_group"):
                groups[dir_name]["title"] = meta["nav_group"]
            groups[dir_name]["items"].append(item)
        else:
            # Top-level page
            order = meta.get("order")
            if isinstance(order, (int, float)):
                item["_sort_key"] = (0, order, md_path)
            else:
                item["_sort_key"] = (1, 0, md_path)
            ungrouped.append(item)

    # Sort ungrouped: index.md always first, then by order/alpha
    nav = []
    # Pull out index.md
    index_item = None
    rest = []
    for item in ungrouped:
        if item["md_path"] == "index.md":
            index_item = item
        else:
            rest.append(item)

    if index_item:
        index_item["label"] = "Home"
        nav.append(index_item)

    rest.sort(key=lambda x: x["_sort_key"])
    nav.extend(rest)

    # Clean up internal sort keys
    for item in nav:
        item.pop("_sort_key", None)

    # Build sorted groups: groups sorted alphabetically by group title
    sorted_group_keys = sorted(
        groups.keys(), key=lambda k: groups[k]["title"].lower()
    )

    for dir_name in sorted_group_keys:
        group_data = groups[dir_name]
        # Sort items within group by nav_order then alphabetically
        group_data["items"].sort(
            key=lambda x: (x.get("_nav_order", 0), x["md_path"])
        )
        # Clean up internal keys
        for item in group_data["items"]:
            item.pop("_nav_order", None)
            item.pop("_sort_key", None)

        slug = re.sub(r"[^a-z0-9]+", "-", group_data["title"].lower()).strip("-")
        nav.append({
            "group": group_data["title"],
            "slug": slug,
            "items": group_data["items"],
        })

    return nav


def _flatten_nav(nav_items):
    """Flatten grouped nav items into a simple page list.

    Groups are expanded in order so that prev/next links work across
    group boundaries.  Returns a list of dicts with ``label``, ``path``,
    and ``md_path`` keys (no group wrappers).
    """
    flat = []
    for item in nav_items:
        if "group" in item:
            flat.extend(item["items"])
        else:
            flat.append(item)
    return flat


def _render_nav(nav_items, prefix, current_path=""):
    """Render the sidebar navigation HTML.

    Ungrouped items render as flat ``<li><a>`` elements.  Grouped items
    render inside ``<details>/<summary>`` wrappers with a
    ``nav-group`` class.  The group containing the active page gets the
    ``open`` attribute so it auto-expands.
    """
    items_html = []
    for item in nav_items:
        if "group" in item:
            # Check if the active page is in this group
            is_active_group = any(
                sub["path"] == current_path for sub in item["items"]
            )
            open_attr = " open" if is_active_group else ""
            sub_items = []
            for sub in item["items"]:
                href = prefix + sub["path"]
                active_cls = (
                    ' class="active"' if sub["path"] == current_path else ""
                )
                sub_items.append(
                    f'<li><a href="{href}"{active_cls}>'
                    f'{_escape_html(sub["label"])}</a></li>'
                )
            items_html.append(
                f'<li class="nav-group">'
                f'<details{open_attr}>'
                f'<summary class="nav-group-title">'
                f'{_escape_html(item["group"])}</summary>'
                f'<ul class="nav-group-items">'
                f'{"".join(sub_items)}'
                f'</ul>'
                f'</details>'
                f'</li>'
            )
        else:
            href = prefix + item["path"]
            active_cls = (
                ' class="active"' if item["path"] == current_path else ""
            )
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
    return truncated + "..."


def _truncate_description(description):
    """Truncate a description string for use in meta tags.

    If the description exceeds 155 characters, truncates at the last
    word boundary before 155 chars and appends "...".  Returns the
    original string unchanged if it fits within 155 characters.
    """
    if not description or len(description) <= 155:
        return description
    truncated = description[:155]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + "..."


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

    return '<nav class="toc-nav" aria-label="Table of contents"><ul>' + "\n".join(items) + "</ul></nav>"


def _build_breadcrumbs(html_path, page_title, prefix):
    """Build breadcrumb HTML for a non-index page.

    For flat pages like ``guide.html``, produces ``Home / Guide``.
    For subdirectory pages like ``api/endpoints.html``, produces
    ``Home / Api / Endpoints`` with intermediate directory links.

    Args:
        html_path: The current page's html path (e.g. "guide.html"
            or "api/endpoints.html").
        page_title: The page title extracted from the first heading.
        prefix: Relative prefix back to root.

    Returns:
        Breadcrumb HTML string.
    """
    parts = html_path.split("/")
    crumbs = [f'<a href="{prefix}index.html">Home</a>']
    # Add intermediate directory breadcrumbs
    for i, dir_name in enumerate(parts[:-1]):
        dir_path = "/".join(parts[:i + 1])
        label = _escape_html(dir_name.capitalize())
        crumbs.append(f'<a href="{prefix}{dir_path}/index.html">{label}</a>')
    # Final segment is the current page (no link)
    crumbs.append(f'<span>{_escape_html(page_title)}</span>')
    return (
        '<nav class="breadcrumbs" aria-label="Breadcrumbs">'
        + " / ".join(crumbs)
        + '</nav>'
    )


def _wrap_page(body_html, nav_html, title, project_name, version,
               css_href="style.css", custom_css_href=None,
               toc_html="", breadcrumbs=None, prev_page=None,
               next_page=None, prefix="", repo=None, source_path=None,
               base_url=None, page_path=None, description="",
               lang="en", date_published=None, date_modified=None, author=None,
               feed_url=None, summary=None, critical_css=None,
               schema=None, twitter_site=None, search=None,
               feedback=None, branch="main"):
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
    edit_url = ""
    if repo and source_path:
        repo_url = repo.rstrip("/")
        edit_url = f"{repo_url}/edit/{branch}/{source_path}"
        edit_link_html = (
            f'<a class="edit-link" href="{edit_url}">'
            f'Edit this page on GitHub</a>'
        )

    # Top edit link: right-aligned near breadcrumbs
    top_edit_link_html = ""
    if edit_url:
        top_edit_link_html = (
            f'<a class="edit-link edit-link-top" href="{edit_url}">Edit</a>'
        )

    # Content header: wraps breadcrumbs and top edit link
    if breadcrumbs_html and top_edit_link_html:
        breadcrumbs_html = (
            f'<div class="content-header">\n'
            f'{breadcrumbs_html}\n'
            f'{top_edit_link_html}\n'
            f'</div>'
        )
    elif top_edit_link_html:
        breadcrumbs_html = (
            f'<div class="content-header">\n'
            f'{top_edit_link_html}\n'
            f'</div>'
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

    # Feedback widget (Feature 30): only rendered when feedback config is set
    feedback_html = ""
    if feedback is not None:
        data_attrs = ""
        if feedback.get("webhook"):
            data_attrs += f' data-webhook="{_escape_html(feedback["webhook"])}"'
        if feedback.get("ga"):
            data_attrs += f' data-ga="{_escape_html(feedback["ga"])}"'
        feedback_html = (
            f'<div class="feedback"{data_attrs}>'
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
            f'<div class="page-meta">{"".join("<span>" + p + "</span>" for p in meta_parts)}</div>'
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
    escaped_title = _escape_html(title)
    escaped_project = _escape_html(project_name)
    canonical_url = f"{base_url}/{page_path}" if page_path else None

    # TechArticle JSON-LD -- emitted when page_path is set
    if page_path:
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

        tech_article = {
            "@context": "https://schema.org",
            "@type": "TechArticle",
            "headline": title,
            "author": author_obj,
        }
        if canonical_url:
            tech_article["url"] = canonical_url
        if description:
            tech_article["description"] = description
        if date_modified:
            tech_article["dateModified"] = date_modified
            tech_article["datePublished"] = date_published or date_modified

        # Publisher must always be an Organization per Google's spec
        if author and author.get("type") == "Organization":
            tech_article["publisher"] = author_obj
        else:
            tech_article["publisher"] = {
                "@type": "Organization",
                "name": project_name,
            }

        tech_article["inLanguage"] = lang

        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(tech_article)}'
            f'\n</script>'
        )

    # BreadcrumbList JSON-LD for non-index pages
    if breadcrumbs and page_path:
        home_item = {
            "@type": "ListItem",
            "position": 1,
            "name": "Home",
            "item": f"{base_url}/index.html",
        }
        items = [home_item]
        parts = page_path.split("/")
        # Intermediate directory entries
        for i, dir_name in enumerate(parts[:-1]):
            dir_path = "/".join(parts[:i + 1])
            entry = {
                "@type": "ListItem",
                "position": len(items) + 1,
                "name": dir_name.capitalize(),
                "item": f"{base_url}/{dir_path}/",
            }
            items.append(entry)
        # Final page entry (no item URL per Google spec)
        items.append({
            "@type": "ListItem",
            "position": len(items) + 1,
            "name": title,
        })
        breadcrumb_ld = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": items,
        }
        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(breadcrumb_ld)}'
            f'\n</script>'
        )

    # WebSite + SearchAction JSON-LD on the homepage
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

    # Standalone Organization/Person JSON-LD on homepage
    if page_path == "index.html":
        # Use Person schema when author.type is "Person"
        entity_type = "Organization"
        if author and author.get("type") == "Person":
            entity_type = "Person"

        entity_name = project_name
        if entity_type == "Person" and author and author.get("name"):
            entity_name = author["name"]

        org_ld = {
            "@context": "https://schema.org",
            "@type": entity_type,
            "name": entity_name,
        }
        # Determine URL: prefer author URL, fall back to base_url
        if author and author.get("url"):
            org_ld["url"] = author["url"]
        else:
            org_ld["url"] = base_url

        # sameAs: collect social profile URLs
        same_as = []
        if author:
            twitter_handle = author.get("twitter")
            if twitter_handle:
                handle = twitter_handle.lstrip("@")
                same_as.append(f"https://twitter.com/{handle}")
        if same_as:
            org_ld["sameAs"] = same_as

        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(org_ld)}'
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
            "name": title,
            "programmingLanguage": prog_lang,
        }
        if repo:
            source_code_ld["codeRepository"] = repo
        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(source_code_ld)}'
            f'\n</script>'
        )

    # DefinedTermSet JSON-LD from glossary blocks and standalone <dfn> tags
    defined_terms = []
    seen_names = set()

    # 1. Glossary terms: <dt><dfn>X</dfn></dt><dd>Y</dd>
    if '<div class="glossary">' in body_html:
        dfn_terms = re.findall(
            r"<dt><dfn>(.*?)</dfn></dt>\s*<dd>(.*?)</dd>",
            body_html,
        )
        for term_name, term_desc in dfn_terms:
            if term_name not in seen_names:
                seen_names.add(term_name)
                defined_terms.append({
                    "@type": "DefinedTerm",
                    "name": term_name,
                    "description": term_desc,
                })

    # 2. Standalone <dfn> tags from _apply_definitions (inside <p> tags,
    #    outside glossary blocks). Extract term and containing paragraph.
    for p_match in re.finditer(r"<p>(.*?)</p>", body_html, re.DOTALL):
        p_content = p_match.group(1)
        dfn_match = re.search(r"<dfn>(.*?)</dfn>", p_content)
        if not dfn_match:
            continue
        # Skip if this <p> is inside a glossary block
        p_start = p_match.start()
        # Find the last glossary-open before this <p>
        glossary_open = body_html.rfind('<div class="glossary">', 0, p_start)
        if glossary_open != -1:
            glossary_close = body_html.find('</div>', glossary_open)
            if glossary_close == -1 or glossary_close > p_start:
                continue  # inside a glossary block
        term_name = dfn_match.group(1)
        # Strip HTML tags from term name (e.g. <code>, <strong>)
        clean_name = re.sub(r"<[^>]+>", "", term_name).strip()
        if clean_name in seen_names:
            continue
        seen_names.add(clean_name)
        # Use full paragraph text (stripped of HTML) as description
        clean_desc = re.sub(r"<[^>]+>", "", p_content).strip()
        defined_terms.append({
            "@type": "DefinedTerm",
            "name": clean_name,
            "description": clean_desc,
        })

    if defined_terms:
        term_set_ld = {
            "@context": "https://schema.org",
            "@type": "DefinedTermSet",
            "name": f"{title} Glossary",
            "hasDefinedTerm": defined_terms,
        }
        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(term_set_ld)}'
            f'\n</script>'
        )

    # ItemList auto-detection: if schema is not set and the page is
    # list-heavy (more <li> than <p>, with at least 5 <li>), auto-set
    # schema to trigger ItemList JSON-LD.
    if not schema:
        li_count = body_html.count('<li>')
        p_count = body_html.count('<p>')
        if li_count > p_count and li_count >= 5:
            schema = "itemlist"

    # ItemList JSON-LD when frontmatter schema == "itemlist"
    if schema == "itemlist":
        li_matches = re.findall(r"<li>(.*?)</li>", body_html)
        if li_matches:
            item_list_elements = []
            for pos, li_content in enumerate(li_matches, start=1):
                # Strip HTML tags from each list item
                plain_text = re.sub(r"<[^>]+>", "", li_content).strip()
                entry = {
                    "@type": "ListItem",
                    "position": pos,
                    "name": plain_text,
                }
                # Extract URL from <a href="..."> if present
                href_match = re.search(r'<a\s+href="([^"]+)"', li_content)
                if href_match:
                    entry["item"] = href_match.group(1)
                item_list_elements.append(entry)
            item_list_ld = {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "itemListElement": item_list_elements,
            }
            seo_tags += (
                f'\n<script type="application/ld+json">\n'
                f'{json.dumps(item_list_ld)}'
                f'\n</script>'
            )

    # OG tags -- emitted when page_path exists
    if page_path:
        escaped_desc = _escape_html(description)
        og_desc_tag = (
            f'\n<meta property="og:description" content="{escaped_desc}">'
            if description else ""
        )
        twitter_desc_tag = (
            f'\n<meta name="twitter:description" content="{escaped_desc}">'
            if description else ""
        )

        twitter_card_type = "summary_large_image"

        og_type = "website" if page_path == "index.html" else "article"
        twitter_site_tag = (
            f'\n<meta name="twitter:site" content="{_escape_html(twitter_site)}">'
            if twitter_site else ""
        )

        # og:locale -- map lang code to locale string
        _LANG_TO_LOCALE = {
            "en": "en_US", "es": "es_ES", "fr": "fr_FR", "de": "de_DE",
            "it": "it_IT", "pt": "pt_BR", "ja": "ja_JP", "ko": "ko_KR",
            "zh": "zh_CN", "ru": "ru_RU", "ar": "ar_SA", "fa": "fa_IR",
            "nl": "nl_NL", "pl": "pl_PL", "tr": "tr_TR", "sv": "sv_SE",
        }
        effective_lang = lang if lang else "en"
        og_locale = _LANG_TO_LOCALE.get(
            effective_lang,
            f"{effective_lang}_{effective_lang.upper()}",
        )

        seo_tags += (
            f'\n<meta property="og:title" content="{escaped_title}'
            f' - {escaped_project}">'
            f'\n<meta property="og:type" content="{og_type}">'
            f'\n<meta property="og:site_name" content="{escaped_project}">'
            f'\n<meta property="og:locale" content="{og_locale}">'
            f'{og_desc_tag}'
            f'\n<meta name="twitter:card" content="{twitter_card_type}">'
            f'\n<meta name="twitter:title" content="{escaped_title}'
            f' - {escaped_project}">'
            f'{twitter_desc_tag}'
            f'{twitter_site_tag}'
        )

        slug = page_path.replace(".html", "")
        # og:image:alt -- use description if available, otherwise title
        og_image_alt = _escape_html(description if description else title)
        seo_tags += (
            f'\n<meta property="og:image" content="{base_url}/og-{slug}.png">'
            f'\n<meta property="og:image:type" content="image/png">'
            f'\n<meta property="og:image:width" content="1200">'
            f'\n<meta property="og:image:height" content="630">'
            f'\n<meta property="og:image:alt" content="{og_image_alt}">'
            f'\n<meta property="og:url" content="{canonical_url}">'
            f'\n<meta name="twitter:image" content="{base_url}/og-{slug}.png">'
        )

    # Canonical URL -- needs base_url
    if canonical_url:
        seo_tags += f'\n<link rel="canonical" href="{canonical_url}">'

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

    # Build inline JS as plain strings (not f-string escaped), minify,
    # then embed.  The head script runs before paint; the body script
    # handles interactive features.
    head_js = (
        "(function(){"
        "var saved=localStorage.getItem('selfdoc-theme');"
        "if(saved==='light'||saved==='dark'){"
        "document.documentElement.setAttribute('data-theme',saved);"
        "}"
        "})();"
    )

    # --- JS blocks: always included ---
    _JS_THEME_TOGGLE = (
        "// Theme toggle (Feature 6)\n"
        "(function(){\n"
        "  var btn = document.querySelector('.theme-toggle');\n"
        "  var states = ['system', 'light', 'dark'];\n"
        "  function getState() {\n"
        "    var s = localStorage.getItem('selfdoc-theme');\n"
        "    return (s === 'light' || s === 'dark') ? s : 'system';\n"
        "  }\n"
        "  function apply(state) {\n"
        "    if (state === 'light' || state === 'dark') {\n"
        "      document.documentElement.setAttribute('data-theme', state);\n"
        "      localStorage.setItem('selfdoc-theme', state);\n"
        "    } else {\n"
        "      document.documentElement.removeAttribute('data-theme');\n"
        "      localStorage.removeItem('selfdoc-theme');\n"
        "    }\n"
        "    btn.setAttribute('data-state', state);\n"
        "    var labels = {system: 'Theme: system. Click for light mode', light: 'Theme: light. Click for dark mode', dark: 'Theme: dark. Click for system theme'};\n"
        "    btn.setAttribute('aria-label', labels[state]);\n"
        "  }\n"
        "  apply(getState());\n"
        "  btn.addEventListener('click', function() {\n"
        "    var cur = getState();\n"
        "    var next = states[(states.indexOf(cur) + 1) % states.length];\n"
        "    apply(next);\n"
        "  });\n"
        "})();\n"
    )

    _JS_SIDEBAR_TOGGLE = (
        "// Mobile sidebar toggle (Feature 25)\n"
        "(function() {\n"
        "  var toggle = document.querySelector('.hamburger');\n"
        "  var sidebar = document.getElementById('sidebar');\n"
        "  if (!toggle || !sidebar) return;\n"
        "  function openSidebar() {\n"
        "    document.body.classList.add('sidebar-open');\n"
        "    toggle.setAttribute('aria-expanded', 'true');\n"
        "  }\n"
        "  function closeSidebar() {\n"
        "    document.body.classList.remove('sidebar-open');\n"
        "    toggle.setAttribute('aria-expanded', 'false');\n"
        "  }\n"
        "  toggle.addEventListener('click', function() {\n"
        "    if (document.body.classList.contains('sidebar-open')) {\n"
        "      closeSidebar();\n"
        "    } else {\n"
        "      openSidebar();\n"
        "    }\n"
        "  });\n"
        "  document.addEventListener('click', function(e) {\n"
        "    if (document.body.classList.contains('sidebar-open') &&\n"
        "        !sidebar.contains(e.target) && !toggle.contains(e.target)) {\n"
        "      closeSidebar();\n"
        "    }\n"
        "  });\n"
        "  sidebar.querySelectorAll('a').forEach(function(link) {\n"
        "    link.addEventListener('click', function() {\n"
        "      closeSidebar();\n"
        "    });\n"
        "  });\n"
        "})();\n"
    )

    # --- JS blocks: conditionally included ---
    _JS_COPY_BUTTON = (
        "// Copy button on code blocks (Feature 5)\n"
        "document.querySelectorAll('pre').forEach(function(pre) {\n"
        "  var code = pre.querySelector('code');\n"
        "  if (!code) return;\n"
        "  var btn = document.createElement('button');\n"
        "  btn.className = 'copy-btn';\n"
        "  btn.textContent = 'Copy';\n"
        "  btn.addEventListener('click', function() {\n"
        "    navigator.clipboard.writeText(code.textContent).then(function() {\n"
        "      btn.textContent = 'Copied!';\n"
        "      setTimeout(function() { btn.textContent = 'Copy'; }, 2000);\n"
        "    });\n"
        "  });\n"
        "  pre.style.position = 'relative';\n"
        "  pre.appendChild(btn);\n"
        "});\n"
    )

    _JS_SCROLLSPY = (
        "// Scrollspy for TOC (Feature 2)\n"
        "(function() {\n"
        "  var tocLinks = document.querySelectorAll('.toc a');\n"
        "  if (!tocLinks.length) return;\n"
        "  var observer = new IntersectionObserver(function(entries) {\n"
        "    entries.forEach(function(entry) {\n"
        "      var id = entry.target.getAttribute('id');\n"
        "      var link = document.querySelector('.toc a[href=\"#' + id + '\"');\n"
        "      if (link) {\n"
        "        if (entry.isIntersecting) {\n"
        "          tocLinks.forEach(function(a) { a.classList.remove('active'); });\n"
        "          link.classList.add('active');\n"
        "        }\n"
        "      }\n"
        "    });\n"
        "  }, { rootMargin: '-80px 0px -80% 0px' });\n"
        "  document.querySelectorAll('main h2[id], main h3[id]').forEach(function(h) {\n"
        "    observer.observe(h);\n"
        "  });\n"
        "})();\n"
    )

    _JS_FEEDBACK = (
        "// Feedback widget (Feature 30)\n"
        "(function() {\n"
        "  var widget = document.querySelector('.feedback');\n"
        "  if (!widget) return;\n"
        "  var key = 'selfdoc-feedback-' + location.pathname;\n"
        "  if (localStorage.getItem(key)) {\n"
        "    widget.innerHTML = '<span>Thanks for your feedback!</span>';\n"
        "    return;\n"
        "  }\n"
        "  var webhook = widget.getAttribute('data-webhook');\n"
        "  var gaId = widget.getAttribute('data-ga');\n"
        "  widget.querySelectorAll('button').forEach(function(btn) {\n"
        "    btn.addEventListener('click', function() {\n"
        "      var vote = btn.className.indexOf('yes') !== -1 ? 'yes' : 'no';\n"
        "      if (webhook) {\n"
        "        fetch(webhook, {\n"
        "          method: 'POST',\n"
        "          headers: {'Content-Type': 'application/json'},\n"
        "          body: JSON.stringify({\n"
        "            page: location.pathname,\n"
        "            vote: vote,\n"
        "            timestamp: new Date().toISOString(),\n"
        "            user_agent: navigator.userAgent\n"
        "          })\n"
        "        }).catch(function() {});\n"
        "      }\n"
        "      if (gaId && typeof gtag === 'function') {\n"
        "        gtag('event', 'selfdoc_feedback', {\n"
        "          page_path: location.pathname,\n"
        "          vote: vote\n"
        "        });\n"
        "      }\n"
        "      localStorage.setItem(key, btn.className);\n"
        "      widget.innerHTML = '<span>Thanks for your feedback!</span>';\n"
        "    });\n"
        "  });\n"
        "})();\n"
    )

    _JS_CODE_TABS = (
        "// Code tabs: switch between language panels (Feature 31)\n"
        "(function() {\n"
        "  document.querySelectorAll('.code-tabs').forEach(function(tabGroup) {\n"
        "    var buttons = tabGroup.querySelectorAll('.tab-bar .tab');\n"
        "    var panels = tabGroup.querySelectorAll('.tab-panel');\n"
        "    buttons.forEach(function(btn) {\n"
        "      btn.addEventListener('click', function() {\n"
        "        var lang = btn.getAttribute('data-lang');\n"
        "        buttons.forEach(function(b) { b.classList.remove('active'); b.setAttribute('aria-selected', 'false'); b.setAttribute('tabindex', '-1'); });\n"
        "        panels.forEach(function(p) { p.classList.remove('active'); });\n"
        "        btn.classList.add('active');\n"
        "        btn.setAttribute('aria-selected', 'true');\n"
        "        btn.setAttribute('tabindex', '0');\n"
        "        var panel = tabGroup.querySelector('.tab-panel[data-lang=\"' + lang + '\"');\n"
        "        if (panel) panel.classList.add('active');\n"
        "        localStorage.setItem('selfdoc-tab-' + lang, 'true');\n"
        "        document.querySelectorAll('.code-tabs').forEach(function(otherGroup) {\n"
        "          if (otherGroup === tabGroup) return;\n"
        "          var otherBtn = otherGroup.querySelector('.tab-bar .tab[data-lang=\"' + lang + '\"');\n"
        "          if (otherBtn) otherBtn.click();\n"
        "        });\n"
        "      });\n"
        "    });\n"
        "    buttons.forEach(function(btn) {\n"
        "      var lang = btn.getAttribute('data-lang');\n"
        "      if (localStorage.getItem('selfdoc-tab-' + lang)) {\n"
        "        btn.click();\n"
        "      }\n"
        "    });\n"
        "    // Initialize roving tabindex\n"
        "    buttons.forEach(function(b) {\n"
        "      b.setAttribute('tabindex', b.classList.contains('active') ? '0' : '-1');\n"
        "    });\n"
        "    // Keyboard navigation for tabs (WAI-ARIA)\n"
        "    var tabBar = tabGroup.querySelector('.tab-bar');\n"
        "    if (tabBar) {\n"
        "      tabBar.addEventListener('keydown', function(e) {\n"
        "        if (!e.target.classList.contains('tab')) return;\n"
        "        var tabs = Array.prototype.slice.call(buttons);\n"
        "        var idx = tabs.indexOf(e.target);\n"
        "        var next = -1;\n"
        "        if (e.key === 'ArrowRight') {\n"
        "          next = (idx + 1) % tabs.length;\n"
        "        } else if (e.key === 'ArrowLeft') {\n"
        "          next = (idx - 1 + tabs.length) % tabs.length;\n"
        "        } else if (e.key === 'Home') {\n"
        "          next = 0;\n"
        "        } else if (e.key === 'End') {\n"
        "          next = tabs.length - 1;\n"
        "        }\n"
        "        if (next >= 0) {\n"
        "          e.preventDefault();\n"
        "          tabs[next].focus();\n"
        "          tabs[next].click();\n"
        "        }\n"
        "      });\n"
        "    }\n"
        "  });\n"
        "})();\n"
    )

    _JS_RUN_BUTTON = (
        "// Embedded live code playground (Feature 41)\n"
        "(function() {\n"
        "  document.querySelectorAll('.code-block').forEach(function(block) {\n"
        "    var label = block.querySelector('.code-label');\n"
        "    if (!label) return;\n"
        "    var lang = label.textContent.trim().toLowerCase();\n"
        "    var code = block.querySelector('code');\n"
        "    if (!code) return;\n"
        "    var url = null;\n"
        "    if (lang === 'go') {\n"
        "      url = 'https://go.dev/play/p/?body=' + encodeURIComponent(code.textContent);\n"
        "    } else if (lang === 'python') {\n"
        "      url = 'https://www.online-python.com/';\n"
        "    }\n"
        "    if (url) {\n"
        "      var btn = document.createElement('a');\n"
        "      btn.className = 'run-btn';\n"
        "      btn.href = url;\n"
        "      btn.target = '_blank';\n"
        "      btn.rel = 'noopener';\n"
        "      btn.textContent = 'Run';\n"
        "      block.querySelector('pre').appendChild(btn);\n"
        "    }\n"
        "  });\n"
        "})();\n"
    )

    _JS_NAV_GROUPS = (
        "// Nav group collapse persistence\n"
        "(function() {\n"
        "  var groups = document.querySelectorAll('.nav-group details');\n"
        "  if (!groups.length) return;\n"
        "  groups.forEach(function(d) {\n"
        "    var slug = d.querySelector('.nav-group-title');\n"
        "    if (!slug) return;\n"
        "    var key = 'selfdoc-nav-' + slug.textContent.trim()"
        ".toLowerCase().replace(/[^a-z0-9]+/g, '-');\n"
        "    var saved = localStorage.getItem(key);\n"
        "    if (saved === 'closed') {\n"
        "      d.removeAttribute('open');\n"
        "    }\n"
        "    d.addEventListener('toggle', function() {\n"
        "      localStorage.setItem(key, d.open ? 'open' : 'closed');\n"
        "    });\n"
        "  });\n"
        "})();\n"
    )

    # Search trigger HTML (configurable: "icon", "bar", or "hidden")
    effective_search = search if search else "icon"
    if effective_search == "icon":
        search_trigger_html = (
            '<button class="search-trigger" aria-label="Search documentation" title="Search (Cmd+K)">\n'
            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>\n'
            '</button>\n'
        )
    elif effective_search == "bar":
        search_trigger_html = (
            '<button class="search-bar-trigger" aria-label="Search documentation">\n'
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>\n'
            '<span class="search-bar-text">Search...</span>\n'
            '<kbd class="search-bar-kbd">Cmd+K</kbd>\n'
            '</button>\n'
        )
    else:
        # "hidden" -- no trigger in topbar
        search_trigger_html = ""

    # Assemble JS blocks: always-needed first, then conditional
    js_blocks = [_JS_THEME_TOGGLE, _JS_SIDEBAR_TOGGLE, _JS_NAV_GROUPS]

    if "<pre" in body_html:
        js_blocks.append(_JS_COPY_BUTTON)
    if toc_html:
        js_blocks.append(_JS_SCROLLSPY)
    if 'class="feedback"' in footer_html:
        js_blocks.append(_JS_FEEDBACK)
    if 'class="code-tabs"' in body_html:
        js_blocks.append(_JS_CODE_TABS)
    if 'class="code-label"' in body_html:
        js_blocks.append(_JS_RUN_BUTTON)

    body_js = _minify_js("\n".join(js_blocks))

    # Google Analytics script (injected when feedback.ga is configured)
    ga_head_script = ""
    if feedback and feedback.get("ga"):
        ga_id = _escape_html(feedback["ga"])
        ga_head_script = (
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>\n'
            f'<script>\n'
            f'window.dataLayer = window.dataLayer || [];\n'
            f'function gtag(){{dataLayer.push(arguments);}}\n'
            f"gtag('js', new Date());\n"
            f"gtag('config', '{ga_id}');\n"
            f'</script>\n'
        )

    # Feed link in site footer (Feature 9.5)
    feed_footer_html = ""
    if feed_url:
        feed_footer_html = (
            '\n<p><a class="feed-link" href="' + _escape_html(feed_url) + '">'
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">'
            '<circle cx="6.18" cy="17.82" r="2.18"/>'
            '<path d="M4 4.44v2.83c7.03 0 12.73 5.7 12.73 12.73h2.83c0-8.59-6.97-15.56-15.56-15.56z'
            'm0 5.66v2.83c3.9 0 7.07 3.17 7.07 7.07h2.83c0-5.47-4.43-9.9-9.9-9.9z"/>'
            '</svg>'
            'Subscribe via RSS</a></p>'
        )

    return (
        f'<!DOCTYPE html>\n'
        f'<html lang="{lang}">\n'
        f'<head>\n'
        f'<meta charset="UTF-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<title>{_escape_html(title)} - {_escape_html(project_name)}</title>{description_tag}\n'
        f'<link rel="icon" type="image/svg+xml" href="{prefix}favicon.svg">\n'
        f'<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        f'<link rel="preload" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" as="style">\n'
        f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" media="print"'
        f" onload=\"this.media='all'\">"
        f'<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"></noscript>\n'
        f'{"<style>" + critical_css + "</style>" + chr(10) if critical_css else ""}'
        f'<link rel="preload" href="{css_href}" as="style">\n'
        f'<link rel="stylesheet" href="{css_href}" media="print"'
        f" onload=\"this.media='all'\">"
        f'<noscript><link rel="stylesheet" href="{css_href}"></noscript>'
        f'{custom_css_tag}{feed_tag}{seo_tags}\n'
        f'<script>{head_js}</script>\n'
        f'{ga_head_script}'
        f'</head>\n'
        f'<body>\n'
        f'<a class="skip-link" href="#main-content">Skip to content</a>\n'
        f'<header class="topbar">\n'
        f'<div class="topbar-inner">\n'
        f'<button class="hamburger" aria-label="Toggle navigation" aria-expanded="false">\n'
        f'<span></span><span></span><span></span>\n'
        f'</button>\n'
        f'<a class="project-name" href="{prefix}index.html">{_escape_html(project_name)}</a>\n'
        f'{version_badge}\n'
        f'<button class="theme-toggle" aria-label="Toggle theme">\n'
        f'{sun_icon}{moon_icon}{auto_icon}\n'
        f'</button>\n'
        f'{search_trigger_html}'
        f'</div>\n'
        f'</header>\n'
        f'<div class="layout">\n'
        f'<nav class="sidebar" id="sidebar" aria-label="Site navigation">\n'
        f'<ul class="nav-list">\n'
        f'{nav_html}\n'
        f'</ul>\n'
        f'</nav>\n'
        f'<main class="content" id="main-content">\n'
        f'<article>\n'
        f'{breadcrumbs_html}\n'
        f'{mobile_toc_html}\n'
        f'{summary_html}\n'
        f'{body_html}\n'
        f'{footer_html}\n'
        f'</article>\n'
        f'</main>\n'
        f'{toc_aside}\n'
        f'</div>\n'
        f'<footer class="site-footer">\n'
        f'<p>Built with <a href="https://github.com/smm-h/selfdoc">selfdoc</a></p>\n'
        f'{feed_footer_html}\n'
        f'</footer>\n'
        f'<script>{body_js}</script>\n'
        f'<dialog class="search-dialog" id="search-dialog" data-search-prefix="{prefix}" aria-label="Search documentation">\n'
        f'<div class="search-inner">\n'
        f'<input type="search" class="search-input" placeholder="Search docs... (Cmd+K)" aria-controls="search-results">\n'
        f'<ul class="search-results" id="search-results" role="listbox"></ul>\n'
        f'</div>\n'
        f'</dialog>\n'
        f'<script defer src="{prefix}search.js"></script>\n'
        f'</body>\n'
        f'</html>\n'
    )
