"""Generate shared elements for multi-project documentation assembly including homepage, blog index, nav JSON, RSS feed, and sitemap."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime

from selfdoc_core.build import _make_feed_entry, check_post_slug_uniqueness

#: The segment a project's posts sit under inside its own site subtree.
POSTS_SEGMENT = "posts"

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
    posts = merge_project_posts(manifests)

    if not posts:
        return "<p>No posts yet.</p>"

    posts.sort(key=lambda p: p["date"], reverse=True)

    parts = ['<section class="blog-index">', "  <h1>Blog</h1>"]
    for post in posts:
        date = html.escape(post["date"])
        project_name = html.escape(post["project_name"])
        title = html.escape(post["title"])
        href = f"{docs_base}/{post_target(post['manifest_slug'], post['slug'])}/"
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
    for post in merge_project_posts(manifests):
        post_url = f"{docs_base}/{post_target(post['manifest_slug'], post['slug'])}/"
        entries.append(_make_feed_entry(
            title=post["title"],
            url=post_url,
            date=post["date"],
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
            url = f"{docs_base}/{page_target(manifest_slug, page.get('path') or '')}"
            # Ensure trailing slash unless already present
            if not url.endswith("/"):
                url += "/"
            urls.append(url)
    for post in merge_project_posts(manifests):
        urls.append(
            f"{docs_base}/{post_target(post['manifest_slug'], post['slug'])}/"
        )

    urls.sort()

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        parts.append(f"  <url><loc>{html.escape(url)}</loc></url>")
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


#: Crawlers the assembly's robots.txt names explicitly.  The wildcard rule
#: already allows them; naming each one is what keeps a future disallow from
#: being written once and applying to everybody by accident.
ROBOTS_AGENTS = (
    "*", "GPTBot", "ChatGPT-User", "Google-Extended", "PerplexityBot",
    "ClaudeBot", "Googlebot", "OAI-SearchBot",
)


def generate_robots_txt(canonical_base: str) -> str:
    """Produce the assembly's robots.txt, naming the site-wide sitemap.

    Each constituent project's own build writes a robots.txt at its own
    output root, which ends up buried at ``<slug>/robots.txt`` where no
    crawler reads it.  The one that is served is this one.
    """
    lines = []
    for agent in ROBOTS_AGENTS:
        lines.append(f"User-agent: {agent}")
        lines.append("Allow: /")
        lines.append("")
    lines.append(f"Sitemap: {canonical_base.rstrip('/')}/sitemap.xml")
    return "\n".join(lines) + "\n"


def generate_not_found_page(canonical_base: str) -> str:
    """Produce the assembly's root 404 page.

    A project subtree carries its own 404 from its own build, but the site
    root has no build of its own, so a request that matches no project at
    all would otherwise be served the hosting provider's default.
    """
    base = canonical_base.rstrip("/")
    body = (
        '<main class="not-found">\n'
        "  <h1>Page not found</h1>\n"
        "  <p>The page you asked for is not on this site.</p>\n"
        "  <ul>\n"
        f'    <li><a href="{html.escape(base)}/">Projects</a></li>\n'
        f'    <li><a href="{html.escape(base)}/blog/">Blog</a></li>\n'
        "  </ul>\n"
        "</main>"
    )
    return wrap_shared_page(
        "Page not found", body, canonical_url=f"{base}/404.html",
    )


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


def page_target(project_slug: str, page_path: str) -> str:
    """Site-relative address of a project's page (``alpha/guide/``).

    This and :func:`post_target` are the one place that decides where a
    manifest entry lives on the assembled site.  The blog index, the
    sitemap, the feed, the cross-project link check and the deploy-time
    verifier all address pages through them, so they cannot disagree about
    where a page is.
    """
    return f"{project_slug}/{_page_path_to_url_segment(page_path)}"


def post_target(project_slug: str, post_slug: str) -> str:
    """Site-relative address of a project's post (``alpha/posts/hello``)."""
    return f"{project_slug}/{POSTS_SEGMENT}/{post_slug}"


def target_output_path(target: str) -> str:
    """The emitted file a site-relative *target* names.

    Both address forms land on the same file: a directory index.  The
    trailing slash a page target carries and the one a post target does not
    are a spelling difference, not two addresses.
    """
    path = target.strip("/")
    return f"{path}/index.html" if path else "index.html"


def output_path_target(rel_output: str) -> str:
    """The address form an emitted file has, as a link target.

    The inverse of :func:`target_output_path`, in the spelling
    :func:`validate_cross_project_links` recognises: a post keeps no
    trailing slash, everything else gets one.
    """
    path = rel_output.replace("\\", "/")
    if path.endswith("/index.html"):
        path = path[: -len("/index.html")]
    elif path == "index.html":
        path = ""
    segments = path.split("/")
    if len(segments) > 2 and segments[1] == POSTS_SEGMENT:
        return path
    return f"{path}/" if path else ""


def merge_project_posts(manifests: list[dict]) -> list[dict]:
    """Return every project's posts as one list, refusing a slug collision.

    Posts share one slug namespace across the whole assembled site, so two
    projects publishing ``hello`` would claim the same address and one
    would silently overwrite the other.  The unified build refuses that at
    build time; this is the same refusal on the assembly side, where the
    posts arrive as separate manifests written by separate deploys and no
    single build ever sees them together.

    Raises:
        RuntimeError: naming both projects that claim the slug.
    """
    check_post_slug_uniqueness([
        (str(post.get("slug") or ""), str(m.get("slug") or ""))
        for m in manifests
        for post in (m.get("posts") or [])
        if str(post.get("slug") or "")
    ])
    merged = []
    for m in manifests:
        manifest_slug = str(m.get("slug") or "")
        for post in m.get("posts") or []:
            merged.append({
                "date": str(post.get("date") or ""),
                "title": str(post.get("title") or ""),
                "slug": str(post.get("slug") or ""),
                "project_name": str(m.get("name") or ""),
                "manifest_slug": manifest_slug,
            })
    return merged


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
            known.add(page_target(manifest_slug, page.get("path") or ""))
        for post in m.get("posts") or []:
            known.add(post.get("path") or "")
            # Also add the slug-based post path
            known.add(post_target(manifest_slug, post.get("slug") or ""))

    errors = []
    for source, targets in sorted(link_registry.items()):
        for target in targets:
            if target not in known:
                errors.append(
                    f"Broken link in '{source}': target '{target}' "
                    f"not found in any project"
                )
    return errors
