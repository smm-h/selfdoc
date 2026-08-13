"""Site-level directives: the generated parts of the home project's authored pages.

The front page is authored -- prose, structure and design belong to whoever
writes it -- but two of its parts are mechanical: the curated project cards
with each project's live version, and the recent posts.  Those arrive through
directives so the authored page can never go stale.

Where resolution happens
------------------------

Two moments, and both are the same code:

* **Build time**, when the home project is built for the assembly.  The build
  needs the assembly's manifests to know any project's live version, so it is
  run as ``selfblog build --target home --site-manifests <dir>``.  Without
  that context the command refuses to build at all, naming what is missing.
  A plain ``selfdoc build`` of the home project refuses too: selfdoc's
  catalogue has no ``projects-cards``, so it stops at an unknown directive.
  Neither path ever emits an empty region.

* **Assembly time**, on every deploy, inside ``generate_shared_files``.  Each
  resolved region is left in the emitted HTML inside a wrapper element, so
  the assembly can re-render it from the manifests it holds without going
  back to the source.  This is what keeps the front page's
  version badges current when *another* project deploys: the home project's
  own build may be months old, the region is not.

Both moments render a region's links against the *rendering page's* hop back
to the site root, never against the site's base URL.  A region on the front
page and the same region on a page one level down need different hrefs, and
an absolute one would need neither -- it would work on the deployed host and
walk a reader off any preview or mirror.  Directive resolution never learns
which page it is writing into, so the build resolves regions first and then
re-addresses them per page; :func:`page_context` is the one place that turns
a page path into that hop.

The region wrapper is the whole mechanism.  It is a custom element,
``<selfblog-region data-directive="...">``, and not an HTML comment: the
build minifies its output and strips every comment, so a comment-delimited
region would survive the markdown conversion and then vanish on the way to
disk.  A custom element survives both, carries its directive's attributes as
data attributes so a re-render uses the same ones, and is nothing a browser
has to be told about.  A region that opens and never closes is a hard error,
never a half-rendered page.
"""

from __future__ import annotations

import dataclasses
import html
import re

from selfblog.listing import Listing, render_listing_html

#: The directives this module resolves, in one place so the CLI, the build
#: and the verifier all name the same set.
SITE_DIRECTIVES = ("projects-cards", "blog-highlights")

#: The element one region is wrapped in, and the attribute naming which
#: directive wrote it.  A directive's own attributes ride as ``data-arg-*``.
REGION_TAG = "selfblog-region"
_NAME_ATTR = "data-directive"
_ARG_PREFIX = "data-arg-"

_OPEN = '<{tag} {name_attr}="{name}"{attrs}>'
_CLOSE = "</{tag}>"

#: One rendered region, with the paragraph a markdown converter may have
#: wrapped around it.  The wrapper is absorbed on re-render: a block element
#: inside a ``<p>`` is not what any browser would keep.  A region never
#: contains another, so the non-greedy body is unambiguous.
_REGION_RE = re.compile(
    rf"(?:<p>\s*)?<{REGION_TAG}\b(?P<attrs>[^>]*)>"
    r"(?P<body>.*?)"
    rf"</{REGION_TAG}>(?:\s*</p>)?",
    re.DOTALL,
)

_OPEN_RE = re.compile(rf"<{REGION_TAG}\b(?P<attrs>[^>]*)>")
_CLOSE_RE = re.compile(rf"</{REGION_TAG}>")

_ATTR_RE = re.compile(r'([a-z][a-z0-9-]*)="([^"]*)"')


@dataclasses.dataclass(frozen=True)
class SiteContext:
    """Everything a site-level directive reads.

    manifests: every project manifest the assembly holds.
    site_hop: the hop from the page being rendered back to the site root
        (``""`` at the root, ``"../"`` one level in).  Every link a region
        writes is relative to it, so a region resolves under any mount --
        the deployed host, a local preview, a mirror -- instead of only
        under the one base URL the site was configured with.  The refresh
        pass sets it per page, which is the only place the page is known.
    listing: the home project's curated listing, or None when it declares
        none -- which ``projects-cards`` refuses, naming the file.
    home_slug: the home project, which the listing never includes.
    """

    manifests: list[dict]
    site_hop: str = ""
    listing: Listing | None = None
    home_slug: str = ""


#: The config key ``selfblog build --target home`` puts the context under, so
#: the directive shims can read it.  A build with no context under this key
#: cannot resolve a site-level directive and says so.
CONTEXT_KEY = "site_directives"


def _render_attrs(attrs: dict[str, str]) -> str:
    return "".join(
        f' {_ARG_PREFIX}{key}="{html.escape(str(value), quote=True)}"'
        for key, value in sorted(attrs.items())
    )


def _parse_attrs(text: str) -> dict[str, str]:
    """Return a region's directive attributes, from its ``data-arg-*`` set."""
    return {
        key[len(_ARG_PREFIX):]: html.unescape(value)
        for key, value in _ATTR_RE.findall(text or "")
        if key.startswith(_ARG_PREFIX)
    }


def _region_name(attrs_text: str) -> str:
    """Return the directive a region declares, or "" when it declares none."""
    for key, value in _ATTR_RE.findall(attrs_text or ""):
        if key == _NAME_ATTR:
            return html.unescape(value)
    return ""


def render_blog_highlights(manifests, site_hop: str, limit: int) -> str:
    """Return the *limit* most recent posts across every project.

    *site_hop* is the rendering page's hop back to the site root; every
    post link is written against it rather than against the site's base
    URL, so the highlights lead into the tree the reader is on.
    """
    from selfblog.shared import merge_project_posts, post_target

    posts = merge_project_posts(manifests)
    posts.sort(key=lambda p: (p["date"], p["slug"]), reverse=True)
    parts = ['<section class="blog-highlights">']
    if not posts:
        parts.append("  <p>No posts yet.</p>")
    for post in posts[:limit]:
        href = f"{site_hop}{post_target(post['slug'])}/"
        parts.append('  <article class="blog-entry">')
        parts.append(f"    <time>{html.escape(post['date'])}</time>")
        parts.append(
            f'    <span class="project-name">'
            f"{html.escape(post['project_name'])}</span>"
        )
        parts.append(
            f'    <a href="{html.escape(href)}">'
            f"{html.escape(post['title'])}</a>"
        )
        parts.append("  </article>")
    parts.append(
        f'  <p><a href="{html.escape(site_hop)}blog/">All posts</a></p>'
    )
    parts.append("</section>")
    return "\n".join(parts)


def render_directive_body(name: str, attrs: dict[str, str],
                          context: SiteContext) -> str:
    """Return the HTML a site-level directive's region holds.

    Raises:
        RuntimeError: for an unknown name, a missing required attribute, or
            a context that cannot answer the directive (no curated listing).
    """
    if name == "projects-cards":
        unknown = sorted(set(attrs))
        if unknown:
            raise RuntimeError(
                f"directive 'projects-cards' takes no attributes, got "
                f"{', '.join(unknown)}. The listing's content is declared in "
                f"the home project's docs/projects.toml, not on the marker."
            )
        if context.listing is None:
            raise RuntimeError(
                "directive 'projects-cards' renders the curated project "
                "listing, which the home project declares in "
                "docs/projects.toml. This project declares none."
            )
        return render_listing_html(
            context.listing, context.manifests, context.site_hop,
            home_slug=context.home_slug,
        )

    if name == "blog-highlights":
        unknown = sorted(set(attrs) - {"limit"})
        if unknown:
            raise RuntimeError(
                f"directive 'blog-highlights' declares unknown attribute(s) "
                f"{', '.join(unknown)}. It takes 'limit'."
            )
        raw = attrs.get("limit", "")
        if not raw:
            raise RuntimeError(
                "directive 'blog-highlights' requires limit=\"N\": how many "
                "recent posts the front page shows is an editorial decision "
                "with no default."
            )
        try:
            limit = int(raw)
        except ValueError:
            raise RuntimeError(
                f"directive 'blog-highlights': limit must be a whole number, "
                f"got {raw!r}."
            ) from None
        if limit < 1:
            raise RuntimeError(
                f"directive 'blog-highlights': limit must be at least 1, got "
                f"{limit}."
            )
        return render_blog_highlights(context.manifests, context.site_hop, limit)

    raise RuntimeError(
        f"unknown site-level directive {name!r}; selfblog resolves "
        f"{', '.join(SITE_DIRECTIVES)}."
    )


def render_region(name: str, attrs: dict[str, str], context: SiteContext) -> str:
    """Return a resolved region: the body between its two sentinels."""
    body = render_directive_body(name, attrs, context)
    return (
        _OPEN.format(
            tag=REGION_TAG, name_attr=_NAME_ATTR, name=name,
            attrs=_render_attrs(attrs),
        )
        + "\n" + body + "\n"
        + _CLOSE.format(tag=REGION_TAG)
    )


def resolve_for_build(name: str, attrs: dict[str, str], config) -> str:
    """Resolve a site-level directive during a build of the home project.

    This is what the shipped directive shims call.  The context comes from
    the config the ``--target home`` build injects; a build that never
    injected one cannot resolve the directive and says which command does.
    """
    context = (config or {}).get(CONTEXT_KEY)
    if not isinstance(context, SiteContext):
        raise RuntimeError(
            f"directive '{name}' is site-level: it renders from the "
            f"assembled site's manifests, which no single project's build "
            f"can see on its own. Build the home project with "
            f"`selfblog build --target home --site-manifests <dir>`, "
            f"which supplies them."
        )
    return render_region(name, attrs, context)


def home_listing_path(dir_path: str, config) -> str:
    """Return where the home project declares its curated listing."""
    import os

    docs_dir = (config.get("docs") or "docs/").rstrip("/")
    return os.path.join(dir_path, docs_dir, "projects.toml")


def build_home_project(dir_path: str, config, *, site_manifests: str,
                       include_drafts: bool = False, theme: str = ""):
    """Build the home project with the assembly's data in scope.

    This is the only build that can resolve a site-level directive, and the
    refusals below are why: the manifests are what a version badge and a
    post highlight are read from, and no project's own repository holds
    them.  A missing context stops the build before a page is written --
    there is no rendering of an empty region and no placeholder.

    Directive resolution happens per markdown source and never learns which
    emitted page it is writing into, so the regions come out of the build
    addressed from the output root.  :func:`refresh_output_regions` then
    re-renders each one against its own page's hop -- the same pass the
    assembly runs on every deploy, run here so the home project's own build
    output is correct on its own.
    """
    import os

    from selfblog.assembly import load_assembly_manifests
    from selfblog.listing import load_listing_source
    from selfblog.site_directives import SHIM_SCRIPTS
    from selfdoc_core.build import build

    if not site_manifests:
        raise RuntimeError(
            "--site-manifests is required by --target home: the home "
            "project's pages carry site-level directives "
            f"({', '.join(SITE_DIRECTIVES)}) that render from the "
            "assembly's manifests, and this repository holds none of them. "
            "Point it at the assembly checkout's manifests/ directory."
        )
    if not os.path.isdir(site_manifests):
        raise RuntimeError(
            f"--site-manifests names {site_manifests!r}, which is not a "
            f"directory. It is the assembly checkout's manifests/ directory."
        )
    listing_path = home_listing_path(dir_path, config)
    listing = (
        load_listing_source(listing_path)
        if os.path.isfile(listing_path) else None
    )
    home_slug = str((config.get("topology") or {}).get("slug") or "")

    build_config = dict(config)
    build_config["directives"] = {
        **(config.get("directives") or {}), **SHIM_SCRIPTS,
    }
    context = SiteContext(
        manifests=load_assembly_manifests(site_manifests),
        listing=listing,
        home_slug=home_slug,
    )
    build_config[CONTEXT_KEY] = context
    written = build(
        dir_path, config=build_config, include_drafts=include_drafts,
        theme=theme,
    )

    output_dir = os.path.join(
        dir_path, (config.get("output") or "docs/_build/").rstrip("/"),
    )
    refresh_output_regions(output_dir, context)
    return written


def find_unclosed_regions(page_html: str) -> list[str]:
    """Return the directives whose region opens and never closes."""
    opened = [_region_name(m.group("attrs")) for m in _OPEN_RE.finditer(page_html)]
    closed = len(_CLOSE_RE.findall(page_html))
    if closed >= len(opened):
        return []
    # The unclosed ones are the trailing openings: a region never nests, so
    # the openings pair with the closings in order.
    return sorted(set(opened[closed:]))


def region_names(page_html: str) -> list[str]:
    """Return every site-level directive region the page carries."""
    return [_region_name(m.group("attrs")) for m in _REGION_RE.finditer(page_html)]


def refresh_regions(page_html: str, context: SiteContext, *,
                    source: str = "") -> str:
    """Re-render every site-level region in *page_html* from *context*.

    Idempotent by construction: the sentinels stay in the output, so the
    next deploy finds the same regions and rewrites their bodies again.  A
    page with no region comes back unchanged.

    Raises:
        RuntimeError: naming *source* when a region opens and never closes,
            or when a region cannot be re-rendered.
    """
    where = f"{source}: " if source else ""
    unclosed = find_unclosed_regions(page_html)
    if unclosed:
        raise RuntimeError(
            f"{where}the site-level region(s) "
            f"{', '.join(repr(n) for n in unclosed)} open and never close. "
            f"A region is written by selfblog and delimited by a pair of "
            f"sentinel comments; an unpaired one means the emitted page was "
            f"edited by hand."
        )

    def _replace(match: re.Match) -> str:
        name = _region_name(match.group("attrs"))
        attrs = _parse_attrs(match.group("attrs"))
        try:
            return render_region(name, attrs, context)
        except RuntimeError as exc:
            raise RuntimeError(f"{where}{exc}") from exc

    return _REGION_RE.sub(_replace, page_html)


def page_context(context: SiteContext, page_rel: str) -> SiteContext:
    """*context* addressed from the page at *page_rel*.

    ``page_rel`` is the page's path relative to the root it is served
    from, and the hop back to that root is how many directories deep it
    sits.  Every caller that renders a region into a known page goes
    through here, so the build-time pass and the deploy-time pass cannot
    disagree about where a region's links point.
    """
    return dataclasses.replace(
        context, site_hop="../" * page_rel.count("/"),
    )


def refresh_output_regions(output_dir: str, context: SiteContext) -> list[str]:
    """Re-render every region in every HTML page under *output_dir*.

    Returns the output-relative paths that changed.  The paths are also
    the addresses: the home project's output root is the site root, both
    in its own build and after the graft, so a page's depth in this tree
    is the hop its links need.
    """
    import os

    from selfdoc_core.utils import atomic_write

    changed: list[str] = []
    for dirpath, dirs, files in os.walk(output_dir):
        dirs[:] = sorted(dirs)
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, output_dir).replace(os.sep, "/")
            with open(path, "r", encoding="utf-8") as f:
                page_html = f.read()
            refreshed = refresh_regions(
                page_html, page_context(context, rel), source=rel,
            )
            if refreshed != page_html:
                atomic_write(path, refreshed)
                changed.append(rel)
    return changed
