"""The assembly's one set of page-chrome assets.

Every project's build emits its own ``style.css`` at its own output root,
and a standalone deploy of that project needs it -- a project published on
its own is a whole site and carries its own presentation.  Inside the
assembly that same file is one copy per subtree of the *same* stylesheet,
which makes a presentation fix a republish of every project rather than a
deploy.

This module is the assembly's answer: the shared generator writes one
site-level asset per theme actually in use, sourced from the theme files of
the toolchain running the deploy, and re-points every emitted page at it.
The pass runs on every deploy of any project, so a toolchain upgrade reaches
the whole site on the next deploy instead of waiting for each project to
publish again.

What this does *not* touch is a project's own build: constraint by design.
``selfdoc build`` keeps writing a self-contained ``style.css`` beside the
pages that reference it, because a standalone deploy has no assembly to
serve a site-level asset.  The re-pointing is assembly-mount behaviour and
lives here, on the assembly side of the line.

Names are content-hashed rather than version-stamped.  A toolchain version
changes on releases that do not touch the CSS, and the CSS changes during
development without a version change; the hash is the only name that is
exactly as stable as the bytes it addresses, which is what a cache needs.
Identical content also produces an identical name, so a deploy that changes
nothing about the chrome writes nothing about it either.

Themes are per project, so the asset set is theme-keyed: one asset per
distinct theme the roster's manifests declare, and a page references the
one its own project uses.  A page that is the site's rather than any
project's -- the shared pages, the home project's pages at the root, the
site-level blog -- references the home project's.  A manifest naming no
theme is every manifest published so far, and means ``minimal``, which is
what ``selfdoc build`` itself uses when a project's config names none.

Migrating the already-published site
------------------------------------

Nothing has to be republished, and nothing breaks in between.  The
subtrees on the live site reference their own ``style.css``, which is
still there -- the re-pointing rewrites the reference in the emitted HTML
and leaves the file alone, because the file is in each project's
published-file record and deleting it out from under that record is the
prune's business, not this pass's.  On the first deploy after this ships,
of any project, the shared generator runs over the whole tree and every
page in it moves to the site-level asset in one pass.  Until that deploy
the site is exactly as it was.
"""

from __future__ import annotations

import hashlib
import os
import re

from selfdoc_core import effects
from selfdoc_core.build import _minify_css
from selfdoc_core.html import generate_pygments_css, get_css
from selfdoc_core.themes import get_theme_meta
from selfdoc_core.utils import atomic_write

__all__ = [
    "CHROME_DIR",
    "DEFAULT_THEME",
    "chrome_asset_rel",
    "chrome_css",
    "chrome_href",
    "chrome_themes",
    "emitted_pages",
    "is_chrome_reference",
    "manifest_theme",
    "page_theme",
    "repoint_page",
    "repoint_pages",
    "site_root_prefix",
    "write_chrome_assets",
]

#: The site-level directory the chrome assets are served from.  It is one of
#: the assembly's own directories, so no project may claim it as a slug --
#: see ``SITE_RESERVED_DIRS`` in :mod:`selfblog.assembly`.
CHROME_DIR = "_chrome"

#: The theme a project gets when it names none.  This is not a choice made
#: here: it is the same default ``selfdoc build`` applies when a project's
#: ``selfdoc.json`` carries no ``theme`` key, and the two have to agree or a
#: page would be styled by a stylesheet its build never rendered against.
DEFAULT_THEME = "minimal"

#: How much of the digest goes in the file name.  Twelve hex characters is
#: 48 bits, which no site of this size collides in, and it keeps the name
#: readable in a diff.
_HASH_LENGTH = 12

#: Every ``href`` in a page, so a chrome reference can be recognised among
#: them.  The build writes three of them per page -- a preload, the async
#: stylesheet and the ``<noscript>`` fallback -- and all three name the same
#: file, so all three are rewritten by the same pass.
_HREF_RE = re.compile(r'href="([^"]*)"')

#: The rules the assembly's own shared pages need and the theme does not
#: carry.  The project listing, the blog index and the not-found page are
#: the assembly's pages, not any project's, so their classes are not in the
#: theme's class surface; they are styled here, appended to the theme, in
#: the same way the unified builder appends its project-grid rules.
#:
#: Everything else these pages use -- ``.content``, ``.site-footer``,
#: ``.version-badge`` -- is the theme's, and is reused rather than restated.
_SHARED_PAGE_CSS = """\
/* --- assembly shared pages --- */
.shared-page {
  max-width: 52rem;
  margin: 0 auto;
  padding: 2.5rem 1.5rem 3rem;
}
.shared-page > h1 {
  margin-bottom: 1.5rem;
}
.project-list, .blog-index {
  display: block;
}
.project-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.25rem 1.5rem;
  margin: 0 0 1rem;
}
/* The listing renders a card heading as h3 inside a category, the
   name-ordered fallback as h2 with no category around it. */
.project-card h2, .project-card h3 {
  margin: 0 0 0.35rem;
  font-size: 1.15rem;
}
.project-card p {
  margin: 0.35rem 0 0;
  color: var(--text-secondary);
}
.project-category {
  margin: 0 0 2rem;
}
.project-category > h2 {
  font-size: 1rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-secondary);
  margin: 0 0 0.75rem;
}
.external-badge, .project-repo {
  font-size: 0.85em;
  color: var(--text-secondary);
}
.blog-entry {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--border);
}
.blog-entry time {
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  min-width: 6.5rem;
}
.blog-entry .project-name {
  color: var(--text-secondary);
  font-size: 0.85em;
}
.not-found ul {
  margin: 0.75rem 0 0 1.25rem;
}
"""


def manifest_theme(manifest: dict) -> str:
    """The theme a loaded manifest declares, or the build's own default.

    A manifest that names no theme is every manifest published so far: the
    key is read here so a project that starts declaring one is honoured
    without another change on this side.
    """
    return str(manifest.get("theme") or "") or DEFAULT_THEME


def chrome_themes(manifests, home_slug: str) -> tuple[dict[str, str], str]:
    """Return ``(slug -> theme, home theme)`` for a roster's manifests.

    Theme choice is per project, so the site-level asset is theme-keyed
    rather than singular: the assembly emits one asset per distinct theme
    its projects declare, and a page references the one its own project
    uses.  Today every project leaves the key unset and the set has one
    member, which is the cheap case of the same rule rather than an
    assumption the rule depends on.
    """
    by_slug = {
        str(m.get("slug") or ""): manifest_theme(m)
        for m in manifests
        if m.get("slug")
    }
    return by_slug, by_slug.get(home_slug, DEFAULT_THEME)


def chrome_css(theme: str) -> str:
    """The full stylesheet the site-level asset for *theme* carries.

    The theme's own CSS plus the Pygments rules its metadata names -- the
    same two pieces, in the same order, that a project's build writes into
    its own ``style.css`` -- plus the assembly's shared-page rules.
    """
    meta = get_theme_meta(theme)
    css = get_css(theme)
    pygments_css = generate_pygments_css(
        light_style=meta.get("pygments_light", "default"),
        dark_style=meta.get("pygments_dark", "monokai"),
    )
    if pygments_css:
        css = css + "\n\n/* Pygments syntax highlighting */\n" + pygments_css
    css = css + "\n\n" + _SHARED_PAGE_CSS
    return _minify_css(css)


def chrome_asset_rel(theme: str, css: str) -> str:
    """The site-relative path the asset for *theme* with content *css* takes."""
    digest = hashlib.sha256(css.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
    return f"{CHROME_DIR}/{theme}-{digest}.css"


def write_chrome_assets(site_dir: str, themes) -> dict[str, str]:
    """Write one asset per theme in *themes*; return ``theme -> site path``.

    Any other file under :data:`CHROME_DIR` is deleted: an asset whose
    content changed took a new name, and the old name is a file no page
    references and every deploy would otherwise carry forever.
    """
    wanted: dict[str, str] = {}
    for theme in sorted(set(themes)):
        css = chrome_css(theme)
        rel = chrome_asset_rel(theme, css)
        wanted[theme] = rel
        path = os.path.join(site_dir, *rel.split("/"))
        effects.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_write(path, css)

    keep = set(wanted.values())
    chrome_dir = os.path.join(site_dir, CHROME_DIR)
    if os.path.isdir(chrome_dir):
        for name in sorted(os.listdir(chrome_dir)):
            rel = f"{CHROME_DIR}/{name}"
            if rel in keep:
                continue
            path = os.path.join(chrome_dir, name)
            if os.path.isfile(path):
                effects.remove(path)
    return wanted


def site_root_prefix(page_rel: str) -> str:
    """The hop from a site-relative page back to the site root.

    ``""`` at the root, ``"../"`` one level in.  The same fact the shared
    pages already carry as ``search_prefix``: references are relative
    because the assembled tree has to resolve under any mount point, so a
    site-level asset is addressed by hopping out rather than by a leading
    slash.
    """
    return "../" * page_rel.count("/")


def chrome_href(page_rel: str, asset_rel: str) -> str:
    """The reference *page_rel* writes to reach the chrome asset."""
    return site_root_prefix(page_rel) + asset_rel


def page_theme(page_rel: str, by_slug: dict[str, str], home_theme: str) -> str:
    """Which theme's asset a page at *page_rel* references.

    A page inside a project's subtree gets that project's theme.  Everything
    else -- the home project's pages at the site root, the site-level blog,
    and the assembly's own shared pages -- gets the home project's: those
    addresses belong to the site rather than to one project, and the site
    reads as the front page reads.
    """
    head = page_rel.split("/", 1)[0] if "/" in page_rel else ""
    if head and head in by_slug:
        return by_slug[head]
    return home_theme


def is_chrome_reference(ref: str) -> bool:
    """Whether *ref* is a page's reference to its page-chrome stylesheet.

    Two spellings are recognised, because both are on the live site at
    once: a project build's own ``style.css``, relative to the page, and an
    earlier deploy's site-level asset under :data:`CHROME_DIR`.  A custom
    stylesheet is neither and is left where it is -- ``custom.css`` is the
    project's content, not the chrome the assembly owns.
    """
    if not ref or ref.startswith(("http://", "https://", "//", "/", "#")):
        return False
    name = ref.rsplit("/", 1)[-1]
    if name == "style.css":
        return True
    return f"{CHROME_DIR}/" in ref and name.endswith(".css")


def repoint_page(page_html: str, page_rel: str, asset_rel: str) -> str:
    """Return *page_html* with every chrome reference aimed at *asset_rel*."""
    href = chrome_href(page_rel, asset_rel)

    def _swap(match: re.Match) -> str:
        ref = match.group(1)
        if not is_chrome_reference(ref):
            return match.group(0)
        return f'href="{href}"'

    return _HREF_RE.sub(_swap, page_html)


def repoint_pages(site_dir: str, pages, by_slug: dict[str, str],
                  assets: dict[str, str], home_theme: str) -> list[str]:
    """Re-point every page in *pages* at the site-level chrome asset.

    *pages* are site-relative HTML paths, *assets* is the ``theme -> path``
    mapping :func:`write_chrome_assets` returned.  Returns the paths that
    actually changed, so a caller can say what a deploy touched.

    A page whose theme has no asset is a page whose project declares a theme
    the assembly did not emit, and that is a hard error rather than a page
    left pointing at a file the graft no longer serves.
    """
    changed: list[str] = []
    for page_rel in sorted(pages):
        theme = page_theme(page_rel, by_slug, home_theme)
        asset_rel = assets.get(theme)
        if asset_rel is None:
            raise RuntimeError(
                f"site/{page_rel} needs the site-level chrome asset for the "
                f"theme {theme!r}, which this deploy did not emit. The asset "
                f"set is built from the themes the manifests declare, so a "
                f"page asking for another one means the manifest it belongs "
                f"to changed after the set was written."
            )
        path = os.path.join(site_dir, *page_rel.split("/"))
        with open(path, "r", encoding="utf-8") as f:
            page_html = f.read()
        repointed = repoint_page(page_html, page_rel, asset_rel)
        if repointed == page_html:
            continue
        atomic_write(path, repointed)
        changed.append(page_rel)
    return changed


def emitted_pages(site_dir: str) -> list[str]:
    """Every ``.html`` file under *site_dir*, site-relative and sorted."""
    found: list[str] = []
    for dirpath, dirs, files in os.walk(site_dir):
        dirs[:] = sorted(dirs)
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), site_dir)
            found.append(rel.replace(os.sep, "/"))
    return sorted(found)
