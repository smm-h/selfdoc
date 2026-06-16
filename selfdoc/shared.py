"""Generate shared elements for multi-project documentation assembly."""

from __future__ import annotations

import html
import json
from datetime import datetime

from selfdoc.build import _make_feed_entry


def generate_homepage(manifests: list[dict], docs_base: str) -> str:
    """Produce an HTML content fragment listing all projects.

    Args:
        manifests: List of loaded manifest dicts.
        docs_base: Base URL for the documentation site.

    Returns:
        HTML fragment with project cards.
    """
    sorted_manifests = sorted(manifests, key=lambda m: m.get("name", "").lower())
    parts = ['<section class="project-list">', "  <h1>Projects</h1>"]
    for m in sorted_manifests:
        name = html.escape(m.get("name", ""))
        slug = html.escape(m.get("slug", ""))
        version = html.escape(m.get("version", ""))
        description = html.escape(m.get("description", ""))
        href = f"{docs_base}/{slug}/"
        parts.append(f'  <article class="project-card">')
        parts.append(f"    <h2><a href=\"{href}\">{name}</a></h2>")
        if version:
            parts.append(f'    <span class="version-badge">v{version}</span>')
        if description:
            parts.append(f"    <p>{description}</p>")
        parts.append(f"  </article>")
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
        manifest_slug = m.get("slug", "")
        manifest_name = m.get("name", "")
        for post in m.get("posts", []):
            posts.append({
                "date": post.get("date", ""),
                "title": post.get("title", ""),
                "slug": post.get("slug", ""),
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
        parts.append(f'  <article class="blog-entry">')
        parts.append(f"    <time>{date}</time>")
        parts.append(f'    <span class="project-name">{project_name}</span>')
        parts.append(f"    <a href=\"{href}\">{title}</a>")
        parts.append(f"  </article>")
    parts.append("</section>")
    return "\n".join(parts)


def generate_nav_json(manifests: list[dict]) -> str:
    """Produce a JSON string with navigation data for all projects.

    Args:
        manifests: List of loaded manifest dicts.

    Returns:
        Pretty-printed JSON string.
    """
    sorted_manifests = sorted(manifests, key=lambda m: m.get("name", "").lower())
    projects = [
        {
            "name": m.get("name", ""),
            "slug": m.get("slug", ""),
            "version": m.get("version", ""),
        }
        for m in sorted_manifests
    ]
    nav = {"projects": projects, "blog": "/blog/"}
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
        manifest_slug = m.get("slug", "")
        for post in m.get("posts", []):
            post_url = f"{docs_base}/{manifest_slug}/posts/{post.get('slug', '')}/"
            date_val = post.get("date", "")
            title_val = post.get("title", "")
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
        manifest_slug = m.get("slug", "")
        for page in m.get("pages", []):
            path = page.get("path", "")
            url_segment = _page_path_to_url_segment(path)
            url = f"{docs_base}/{manifest_slug}/{url_segment}"
            # Ensure trailing slash unless already present
            if not url.endswith("/"):
                url += "/"
            urls.append(url)
        for post in m.get("posts", []):
            post_slug = post.get("slug", "")
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
        for page in m.get("pages", []):
            known.add(page.get("path", ""))
        for post in m.get("posts", []):
            known.add(post.get("path", ""))
            # Also add the slug-based post path
            manifest_slug = m.get("slug", "")
            post_slug = post.get("slug", "")
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
