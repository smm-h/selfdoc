"""Generate shared elements for multi-project documentation assembly including homepage, blog index, nav JSON, RSS feed, and sitemap."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime

from selfdoc_core.build import _make_feed_entry

# Matches a <link rel=canonical ...> element with any attribute order and
# any quoting style.  Hand-authored HTML is not normalized, so the pattern
# has to be permissive about how the element was written.
_CANONICAL_LINK_RE = re.compile(
    r"""<link\b[^>]*\brel\s*=\s*["']?canonical["']?[^>]*>""",
    re.IGNORECASE,
)
_HEAD_OPEN_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)


def _ensure_canonical(page_html: str, url: str) -> str:
    """Return *page_html* carrying exactly one rel=canonical link naming *url*.

    The portfolio is hand-authored HTML that selfblog copies rather than
    generates, so it may already declare a canonical (possibly the wrong
    one) or none at all.  An existing link is rewritten in place; otherwise
    one is spliced in directly after the opening ``<head>`` tag.

    Raises:
        ValueError: when the document has no ``<head>`` to splice into.
            A page that cannot declare a canonical is a hard error, not a
            page served without one.
    """
    link = f'<link rel="canonical" href="{html.escape(url)}">'
    if _CANONICAL_LINK_RE.search(page_html):
        return _CANONICAL_LINK_RE.sub(lambda _m: link, page_html, count=1)
    match = _HEAD_OPEN_RE.search(page_html)
    if match is None:
        raise ValueError(
            "cannot declare a canonical URL: the document has no <head> "
            "element to splice the rel=canonical link into"
        )
    insert_at = match.end()
    return f"{page_html[:insert_at]}\n  {link}{page_html[insert_at:]}"


def wrap_shared_page(
    title: str,
    body_html: str,
    css_url: str = "",
    canonical_url: str = "",
) -> str:
    """Wrap an HTML fragment in a complete HTML page.

    Args:
        title: Page title for the <title> tag.
        body_html: HTML fragment to place inside <body>.
        css_url: Optional URL for an external CSS stylesheet.
        canonical_url: Absolute URL for the page's rel=canonical link.
            The assembly site is reachable on more than one host, so the
            shared pages declare which one is canonical.  Empty means no
            canonical link is emitted.

    Returns:
        Complete HTML document string.
    """
    css_link = ""
    if css_url:
        css_link = f'\n    <link rel="stylesheet" href="{html.escape(css_url)}">'
    canonical_link = ""
    if canonical_url:
        canonical_link = (
            f'\n    <link rel="canonical" href="{html.escape(canonical_url)}">'
        )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '    <meta charset="utf-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"    <title>{html.escape(title)}</title>{canonical_link}{css_link}\n"
        "    <style>\n"
        "        body { max-width: 48rem; margin: 0 auto; padding: 1rem 1.5rem;"
        " font-family: system-ui, -apple-system, sans-serif;"
        " line-height: 1.6; color: #222; }\n"
        "        a { color: #0366d6; }\n"
        "        a:visited { color: #6f42c1; }\n"
        "    </style>\n"
        "</head>\n"
        "<body>\n"
        f"{body_html}\n"
        "</body>\n"
        "</html>\n"
    )


def generate_homepage(manifests: list[dict], docs_base: str) -> str:
    """Produce an HTML content fragment listing all projects.

    Args:
        manifests: List of loaded manifest dicts.
        docs_base: Base URL for the documentation site.

    Returns:
        HTML fragment with project cards.
    """
    sorted_manifests = sorted(manifests, key=lambda m: (m.get("name") or "").lower())
    parts = ['<section class="project-list">', "  <h1>Projects</h1>"]
    for m in sorted_manifests:
        name = html.escape(m.get("name") or "")
        slug = html.escape(m.get("slug") or "")
        version = html.escape(m.get("version") or "")
        description = html.escape(m.get("description") or "")
        href = f"{docs_base}/{slug}/"
        parts.append('  <article class="project-card">')
        parts.append(f"    <h2><a href=\"{href}\">{name}</a></h2>")
        if version:
            if version == "0.0.0":
                parts.append('    <span class="version-badge">monorepo</span>')
            else:
                parts.append(f'    <span class="version-badge">v{version}</span>')
        if description:
            parts.append(f"    <p>{description}</p>")
        parts.append("  </article>")
    parts.append("</section>")
    return "\n".join(parts)


def generate_blog_index(manifests: list[dict], docs_base: str) -> str:
    """Produce an HTML fragment listing all posts across projects, newest first.

    Args:
        manifests: List of loaded manifest dicts.
        docs_base: Base URL for the documentation site.

    Returns:
        HTML fragment with the blog index.
    """
    posts = []
    for m in manifests:
        manifest_slug = m.get("slug") or ""
        manifest_name = m.get("name") or ""
        for post in m.get("posts") or []:
            posts.append({
                "date": post.get("date") or "",
                "title": post.get("title") or "",
                "slug": post.get("slug") or "",
                "project_name": manifest_name,
                "manifest_slug": manifest_slug,
            })

    if not posts:
        return "<p>No posts yet.</p>"

    posts.sort(key=lambda p: p["date"], reverse=True)

    parts = ['<section class="blog-index">', "  <h1>Blog</h1>"]
    for post in posts:
        date = html.escape(post["date"])
        project_name = html.escape(post["project_name"])
        title = html.escape(post["title"])
        href = f"{docs_base}/{post['manifest_slug']}/posts/{post['slug']}/"
        parts.append('  <article class="blog-entry">')
        parts.append(f"    <time>{date}</time>")
        parts.append(f'    <span class="project-name">{project_name}</span>')
        parts.append(f"    <a href=\"{href}\">{title}</a>")
        parts.append("  </article>")
    parts.append("</section>")
    return "\n".join(parts)


def generate_nav_json(manifests: list[dict], blog_path: str = "/blog/") -> str:
    """Produce a JSON string with navigation data for all projects.

    Args:
        manifests: List of loaded manifest dicts.
        blog_path: URL path for the blog link in navigation.

    Returns:
        Pretty-printed JSON string.
    """
    sorted_manifests = sorted(manifests, key=lambda m: (m.get("name") or "").lower())
    projects = [
        {
            "name": m.get("name") or "",
            "slug": m.get("slug") or "",
            "version": m.get("version") or "",
        }
        for m in sorted_manifests
    ]
    nav = {"projects": projects, "blog": blog_path}
    return json.dumps(nav, indent=2)


def generate_unified_feed(
    manifests: list[dict],
    docs_base: str,
    feed_title: str = "",
) -> str:
    """Produce an Atom XML feed aggregating posts from all projects.

    Args:
        manifests: List of loaded manifest dicts.
        docs_base: Base URL for the documentation site.
        feed_title: Title for the feed. Defaults to "Documentation".

    Returns:
        Complete Atom XML string.
    """
    if not feed_title:
        feed_title = "Documentation"

    entries = []
    for m in manifests:
        manifest_slug = m.get("slug") or ""
        for post in m.get("posts") or []:
            post_url = f"{docs_base}/{manifest_slug}/posts/{post.get('slug') or ''}/"
            date_val = post.get("date") or ""
            title_val = post.get("title") or ""
            entries.append(_make_feed_entry(
                title=title_val,
                url=post_url,
                date=date_val,
            ))

    # Sort by date descending
    entries.sort(key=lambda e: e[0], reverse=True)

    if entries:
        most_recent = entries[0][0]
    else:
        most_recent = datetime.now().strftime("%Y-%m-%d")

    entry_xml = "\n".join(entry for _, entry in entries)
    if entry_xml:
        entry_xml += "\n"

    feed_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <title>{html.escape(feed_title)}</title>\n"
        f'  <link href="{docs_base}/feed.xml" rel="self"/>\n'
        f'  <link href="{docs_base}/"/>\n'
        f"  <id>{docs_base}/</id>\n"
        f"  <updated>{most_recent}T00:00:00Z</updated>\n"
        f"{entry_xml}"
        "</feed>\n"
    )
    return feed_xml


def generate_sitemap(manifests: list[dict], docs_base: str) -> str:
    """Produce a sitemap XML listing all pages and posts from all projects.

    Args:
        manifests: List of loaded manifest dicts.
        docs_base: Base URL for the documentation site.

    Returns:
        Complete sitemap XML string.
    """
    urls = []
    for m in manifests:
        manifest_slug = m.get("slug") or ""
        for page in m.get("pages") or []:
            path = page.get("path") or ""
            url_segment = _page_path_to_url_segment(path)
            url = f"{docs_base}/{manifest_slug}/{url_segment}"
            # Ensure trailing slash unless already present
            if not url.endswith("/"):
                url += "/"
            urls.append(url)
        for post in m.get("posts") or []:
            post_slug = post.get("slug") or ""
            url = f"{docs_base}/{manifest_slug}/posts/{post_slug}/"
            urls.append(url)

    urls.sort()

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        parts.append(f"  <url><loc>{html.escape(url)}</loc></url>")
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


def _page_path_to_url_segment(path: str) -> str:
    """Convert a page path to a URL segment.

    Args:
        path: Page path from manifest (e.g. "guide.md", "index.md",
              "api/reference.md").

    Returns:
        URL segment (e.g. "guide/", "", "api/reference/").
    """
    if path.endswith(".md"):
        path = path[:-3]
    if path == "index":
        return ""
    if path.endswith("/index"):
        return path[: -len("/index")] + "/"
    return path + "/"


def validate_cross_project_links(
    manifests: list[dict],
    link_registry: dict[str, list[str]],
) -> list[str]:
    """Check that all cross-project links resolve to known pages or posts.

    Args:
        manifests: List of loaded manifest dicts.
        link_registry: Maps source page path to list of target URLs.

    Returns:
        List of error strings for broken links. Empty if all valid.
    """
    known = set()
    for m in manifests:
        manifest_slug = m.get("slug") or ""
        for page in m.get("pages") or []:
            known.add(page.get("path") or "")
            # Also add the URL-form page path
            url_segment = _page_path_to_url_segment(page.get("path") or "")
            known.add(f"{manifest_slug}/{url_segment}")
        for post in m.get("posts") or []:
            known.add(post.get("path") or "")
            # Also add the slug-based post path
            post_slug = post.get("slug") or ""
            known.add(f"{manifest_slug}/posts/{post_slug}")

    errors = []
    for source, targets in sorted(link_registry.items()):
        for target in targets:
            if target not in known:
                errors.append(
                    f"Broken link in '{source}': target '{target}' "
                    f"not found in any project"
                )
    return errors
