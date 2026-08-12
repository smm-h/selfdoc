"""Generate shared elements for multi-project documentation assembly including homepage, blog index, nav JSON, RSS feed, and sitemap."""

from __future__ import annotations

import html
import json
from datetime import datetime

from selfdoc_core.build import (
    POSTS_PREFIX,
    _make_feed_entry,
    check_post_slug_uniqueness,
)
from selfdoc_core.html import (
    pagefind_dialog_html,
    pagefind_head_tags,
    pagefind_init_script,
)
from selfdoc_core.robots import ROBOTS_AGENTS, render_robots_txt

__all__ = [
    "POSTS_SEGMENT",
    "ROBOTS_AGENTS",
    "generate_blog_index",
    "generate_homepage",
    "generate_llms_txt",
    "generate_nav_json",
    "generate_not_found_page",
    "generate_robots_txt",
    "generate_sitemap",
    "generate_unified_feed",
    "merge_project_posts",
    "output_path_target",
    "page_target",
    "post_target",
    "target_output_path",
    "validate_cross_project_links",
    "wrap_shared_page",
]

#: The site-level directory every post is served from: ``blog/<post-slug>/``,
#: at the assembly root and never under a project slug.  It is the build's
#: own ``POSTS_PREFIX`` because the two cannot be allowed to disagree: what
#: a project's build emits under ``blog/`` is what the assembly serves at
#: ``blog/``, moved across unchanged.
POSTS_SEGMENT = POSTS_PREFIX

def wrap_shared_page(
    title: str,
    body_html: str,
    css_url: str = "",
    canonical_url: str = "",
    *,
    search_prefix: str,
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
        search_prefix: The hop from this page back to the site root, where
            the assembly's one site-wide Pagefind index lives (``""`` for a
            page at the root, ``"../"`` one level in).  Required: a shared
            page carries the same search as every documentation page, and
            the hop is a fact about where the page sits.

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
        f"{pagefind_head_tags(search_prefix)}"
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
        f"{pagefind_dialog_html()}\n"
        f"{pagefind_init_script(search_prefix)}\n"
        "</body>\n"
        "</html>\n"
    )


def generate_homepage(manifests: list[dict], docs_base: str, *,
                      home_slug: str = "", listing=None) -> str:
    """Produce the project listing fragment the ``/projects/`` page serves.

    *listing* is the home project's curated listing.  When it is present it
    is the source: categories, order and blurbs are content the home project
    authors, and this page is one of its two renderings (the front page's
    cards directive is the other).  When it is absent -- an assembly whose
    home project has never deployed -- every served project is listed in
    name order, which is a listing nobody curated rather than no listing.

    The home project itself is never in either rendering: it is the page the
    listing is reached from, not one of the projects it lists.

    Args:
        manifests: List of loaded manifest dicts.
        docs_base: Base URL for the documentation site.
        home_slug: The roster's home project, left out of the listing.
        listing: The curated :class:`~selfblog.listing.Listing`, or None.

    Returns:
        HTML fragment with project cards.
    """
    if listing is not None:
        from selfblog.listing import render_listing_html

        return render_listing_html(
            listing, manifests, docs_base,
            home_slug=home_slug, heading="Projects",
        )

    sorted_manifests = sorted(
        (m for m in manifests if (m.get("slug") or "") != home_slug),
        key=lambda m: (m.get("name") or "").lower(),
    )
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
        href = f"{docs_base}/{post_target(post['slug'])}/"
        parts.append('  <article class="blog-entry">')
        parts.append(f"    <time>{date}</time>")
        parts.append(f'    <span class="project-name">{project_name}</span>')
        parts.append(f"    <a href=\"{href}\">{title}</a>")
        parts.append("  </article>")
    parts.append("</section>")
    return "\n".join(parts)


def generate_nav_json(manifests: list[dict], blog_path: str = "/blog/", *,
                      home_slug: str = "") -> str:
    """Produce a JSON string with navigation data for all projects.

    The home project is not one of them: it is the site root every nav
    already points back to, not an entry in the project set.

    Args:
        manifests: List of loaded manifest dicts.
        blog_path: URL path for the blog link in navigation.
        home_slug: The roster's home project, left out of the project set.

    Returns:
        Pretty-printed JSON string.
    """
    sorted_manifests = sorted(
        (m for m in manifests if (m.get("slug") or "") != home_slug),
        key=lambda m: (m.get("name") or "").lower(),
    )
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
        post_url = f"{docs_base}/{post_target(post['slug'])}/"
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


def generate_sitemap(manifests: list[dict], docs_base: str, *,
                     home_slug: str = "") -> str:
    """Produce a sitemap XML listing all pages and posts from all projects.

    Args:
        manifests: List of loaded manifest dicts.
        docs_base: Absolute base URL for the documentation site.  Required
            and absolute: the sitemap protocol has no relative ``<loc>``,
            and a crawler reading ``/alpha/guide/`` where an absolute URL
            belongs drops the entry.  An empty or root-relative base is a
            hard error rather than a sitemap that silently indexes nothing.
        home_slug: The roster's home project, whose pages are addressed
            from the site root rather than from a project segment.

    Returns:
        Complete sitemap XML string.
    """
    if not docs_base or not docs_base.startswith(("http://", "https://")):
        raise ValueError(
            f"generate_sitemap needs an absolute base URL, got "
            f"{docs_base!r}. Every <loc> is an absolute URL -- the sitemap "
            f"protocol has no relative form -- so a root-relative or empty "
            f"base produces entries every crawler discards."
        )
    urls = []
    for m in manifests:
        manifest_slug = m.get("slug") or ""
        is_home = bool(home_slug) and manifest_slug == home_slug
        for page in m.get("pages") or []:
            url = (
                f"{docs_base}/"
                f"{page_target(manifest_slug, page.get('path') or '', home=is_home)}"
            )
            # Ensure trailing slash unless already present
            if not url.endswith("/"):
                url += "/"
            urls.append(url)
    for post in merge_project_posts(manifests):
        urls.append(f"{docs_base}/{post_target(post['slug'])}/")

    urls.sort()

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        parts.append(f"  <url><loc>{html.escape(url)}</loc></url>")
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


#: The address of the sitemap the site-wide robots.txt names.  The sitemap is
#: written at the site root by :func:`~selfblog.assembly.generate_shared_files`
#: and this is the same file, so the two cannot name different documents.
SITEMAP_PATH = "sitemap.xml"

#: Where the composed, site-wide llms.txt is served from.
LLMS_PATH = "llms.txt"


def generate_robots_txt(canonical_base: str) -> str:
    """Produce the assembly's robots.txt, naming the site-wide sitemap.

    Each constituent project's own build writes a robots.txt at its own
    output root, which ends up buried at ``<slug>/robots.txt`` where no
    crawler reads it.  The one that is served is this one, and it carries
    the same crawler policy -- :data:`ROBOTS_AGENTS`, read from the build
    that writes the per-project ones, so the site cannot allow a crawler
    its projects disallow or the other way round.
    """
    return render_robots_txt(f"{canonical_base.rstrip('/')}/{SITEMAP_PATH}")


def generate_llms_txt(manifests: list[dict], canonical_base: str, *,
                      home_slug: str = "") -> str:
    """Produce the assembly's llms.txt, composed by reference.

    Every constituent project's build writes its own ``llms.txt`` listing
    its own pages, and the graft keeps it at ``<slug>/llms.txt``.  The
    site-wide file links to each of those rather than restating them: an
    inlined copy would be a second, staler rendering of a document the
    project already publishes, and it would go out of date on every deploy
    that is not this one.

    The home project is left out for the same reason it is left out of the
    listing: it is the site root the file is served from, not one of the
    projects it points at.

    Args:
        manifests: Loaded per-project manifests.
        canonical_base: Absolute base URL of the assembly site.
        home_slug: The roster's home project, left out of the list.
    """
    base = canonical_base.rstrip("/")
    listed = sorted(
        (m for m in manifests if (m.get("slug") or "") != home_slug),
        key=lambda m: (m.get("name") or "").lower(),
    )

    lines = [
        "# Documentation",
        "",
        "> Every project's documentation is published here. Each entry below "
        "links to that project's own llms.txt, which lists its pages.",
        "",
        "## Projects",
        "",
    ]
    if not listed:
        lines.append("- No projects are published yet.")
    for m in listed:
        name = m.get("name") or m.get("slug") or ""
        slug = m.get("slug") or ""
        description = (m.get("description") or "").strip().splitlines()
        summary = description[0] if description else ""
        entry = f"- [{name}]({base}/{slug}/{LLMS_PATH})"
        lines.append(f"{entry}: {summary}" if summary else entry)

    lines.extend([
        "",
        "## Blog",
        "",
        f"- [Blog]({base}/{POSTS_SEGMENT}/): posts from every project, "
        f"newest first.",
        "",
    ])
    return "\n".join(lines)


def generate_not_found_page(canonical_base: str) -> str:
    """Produce the assembly's root 404 page.

    A project subtree carries its own 404 from its own build, but the site
    root has no build of its own, so a request that matches no project at
    all would otherwise be served the hosting provider's default.

    It is served through the hosting provider's ``404.html`` convention:
    a request matching no asset gets this body with a 404 status.  That is
    why its body has to differ from the front page -- an unknown address
    that renders the front page is a soft 404, and a crawler reads it as a
    duplicate of the home page rather than as a dead link.
    """
    base = canonical_base.rstrip("/")
    body = (
        '<main class="not-found">\n'
        "  <h1>Page not found</h1>\n"
        "  <p>There is no page at this address. It may have moved, or the "
        "link that brought you here may be wrong.</p>\n"
        "  <p>These three are always here:</p>\n"
        "  <ul>\n"
        f'    <li><a href="{html.escape(base)}/">Home</a></li>\n'
        f'    <li><a href="{html.escape(base)}/projects/">Projects</a></li>\n'
        f'    <li><a href="{html.escape(base)}/{POSTS_SEGMENT}/">Blog</a></li>\n'
        "  </ul>\n"
        "  <p>Or search the whole site from any documentation page.</p>\n"
        "</main>"
    )
    return wrap_shared_page(
        "Page not found", body, canonical_url=f"{base}/404.html",
        search_prefix="",
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


def page_target(project_slug: str, page_path: str, *, home: bool = False) -> str:
    """Site-relative address of a project's page (``alpha/guide/``).

    This and :func:`post_target` are the one place that decides where a
    manifest entry lives on the assembled site.  The blog index, the
    sitemap, the feed, the cross-project link check and the deploy-time
    verifier all address pages through them, so they cannot disagree about
    where a page is.

    *home* is the roster's home project: its content root is the site root,
    so its pages carry no project segment at all -- ``cv.md`` is at ``cv/``
    and its ``index.md`` is the site's front page.
    """
    if home:
        return _page_path_to_url_segment(page_path)
    return f"{project_slug}/{_page_path_to_url_segment(page_path)}"


def post_target(post_slug: str) -> str:
    """Site-relative address of a post (``blog/hello``).

    A post has no project segment: the blog is the site's, one slug
    namespace shared by every project, and ``blog/<post-slug>/`` is where
    the build emits a post and where the assembly serves it.  Which project
    wrote it is metadata the blog index prints, not part of its address.
    """
    return f"{POSTS_SEGMENT}/{post_slug}"


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
    if len(segments) == 2 and segments[0] == POSTS_SEGMENT:
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
            # Also add the site-level post address
            known.add(post_target(post.get("slug") or ""))

    errors = []
    for source, targets in sorted(link_registry.items()):
        for target in targets:
            if target not in known:
                errors.append(
                    f"Broken link in '{source}': target '{target}' "
                    f"not found in any project"
                )
    return errors
