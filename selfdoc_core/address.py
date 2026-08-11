"""The single addressing authority for built pages.

One function -- :func:`page_address` -- decides, for a page and the
locale/project/version it belongs to, all four things the rest of the
build needs:

* ``output_key``  -- where the page file lands under the output root
  (``guide/index.html`` for the current version, ``v/1.0.0/guide/index.html``
  for a superseded one).
* ``stable``      -- the version-free URL path for the page (``guide/``).
  This is where the *current* version of every page lives, and it is what
  every version of the page declares canonical.
* ``pinned``      -- the version-pinned URL path (``v/1.0.0/guide/``).  A
  superseded version is emitted there; the current version's pinned
  address is the address it will occupy once a newer version supersedes
  it.
* ``depth``       -- how many directory levels the output key sits below
  the output root, and from it the two relative hops every page needs:
  ``to_site_root`` (back to the output root, where the shared assets
  live) and ``to_mount_root`` (back to this page's own mount, where its
  sibling pages live).

The scheme
----------

The current version of every page lives at a stable, unversioned address::

    <locale>/<project>/<page>/

Superseded versions live beside it under the archive prefix ``v/``::

    <locale>/<project>/v/<version>/<page>/

The locale segment is dropped entirely while a site has one locale --
:func:`locale_segment` is the one place that decides it -- and the project
segment exists only on a unified site.  A single-locale standalone site
therefore mounts its current version at the output root: ``guide/``.

``v`` is reserved.  A top-level page named ``v`` would collide with the
archive tree, so :func:`page_address` refuses it.

Why its own module rather than ``urls.py``: ``urls.py`` turns a path into
an absolute URL against a configured base (``base_url``, or a docs base
plus a slug).  That is a deployment concern -- it answers "what does the
world call this page".  Addressing answers "where does this page sit in
the output tree, and how does it reach its neighbours", which has to be
correct with no base URL at all and identical under every mount point.
Mixing the two is what produced the depth defect this module replaces:
a site's own asset links must never depend on where the site is served
from, so they are always document-relative and always derived here.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ARCHIVE_PREFIX",
    "PageAddress",
    "locale_segment",
    "page_address",
    "root_page_link",
]

#: URL segment every archived (superseded) version is emitted under.
ARCHIVE_PREFIX = "v"


@dataclass(frozen=True, slots=True)
class PageAddress:
    """Every address a single built page has.

    Attributes:
        page_path: The mount-relative HTML path (e.g. ``guide/index.html``).
        locale: Locale segment of the mount (``""`` when the site has one
            locale, which is when the segment is dropped).
        project: Constituent-project segment of the mount (``""`` on a
            standalone site).
        version: Version this page was built from (``""`` for pages that
            are not version-scoped).  A version does not imply a version
            segment: the current version has none.
        archived: Whether this page is a superseded version, emitted under
            the archive prefix instead of at the stable address.
        mount: The output prefix this page is built under.
        output_key: Path of the page file relative to the output root.
        stable: Version-free URL path for the page -- where its current
            version lives, and what every version canonicalizes to.
        pinned: Version-pinned URL path for the page.  Equals ``stable``
            for a page that is not version-scoped.
        depth: Directory levels between the page and the output root.
    """

    page_path: str
    locale: str
    project: str
    version: str
    archived: bool
    mount: str
    output_key: str
    stable: str
    pinned: str
    depth: int

    @property
    def url(self) -> str:
        """The URL path this page is actually emitted at."""
        return self.pinned if self.archived else self.stable

    @property
    def stable_mount(self) -> str:
        """The version-free mount: where the current version's pages sit."""
        return _join(self.locale, self.project)

    @property
    def archive_mount(self) -> str:
        """The mount superseded copies of this page's version sit under."""
        if not self.version:
            return self.stable_mount
        return _join(self.locale, self.project, ARCHIVE_PREFIX, self.version)

    @property
    def to_site_root(self) -> str:
        """Relative hop from this page's directory to the output root."""
        return "../" * self.depth

    @property
    def to_mount_root(self) -> str:
        """Relative hop from this page's directory to its own mount root."""
        return "../" * self.page_path.count("/")

    @property
    def to_stable_mount_root(self) -> str:
        """Relative hop from this page's directory to the version-free mount.

        On a page emitted at the stable address this is the same hop as
        :attr:`to_mount_root`.  On an archive page it climbs two levels
        further, over ``v/<version>/``.
        """
        mount_depth = len([p for p in self.stable_mount.split("/") if p])
        return "../" * (self.depth - mount_depth)


def root_page_link(md_filename: str) -> str:
    """Link written on one root-level docs page to another root-level page.

    Every root-level page except ``index.md`` is emitted at
    ``<stem>/index.html``, so a page writing a link is itself inside a
    directory and a sibling is one level up: ``../<stem>/``.  Writing the
    bare ``<stem>/`` -- correct back when pages were flat ``<stem>.html``
    files -- now resolves inside the writing page's own directory and
    names nothing.

    The generated index pages (the API reference and the CLI reference)
    are the callers: both are always at the docs root, which is what makes
    the single hop the right one.
    """
    stem = md_filename[:-3] if md_filename.endswith(".md") else md_filename
    if stem == "index":
        return "../"
    return f"../{stem}/"


def locale_segment(locale_code: str, locales) -> str:
    """The locale segment a mount carries for *locale_code*.

    A site with one locale has nothing to disambiguate, so it emits no
    locale segment at all; a multi-locale site emits the code.  Every
    caller that turns a configured locale into a mount coordinate goes
    through here, so the two cases can never disagree.

    Args:
        locale_code: The locale being built (e.g. ``"en"``).
        locales: The project's full ``locales`` config list.

    Returns:
        The locale code, or ``""`` while the site has a single locale.
    """
    return locale_code if locales and len(locales) > 1 else ""


def _to_url(html_path: str) -> str:
    """Turn an HTML file path into its directory-index URL path.

    ``index.html`` -> ``""``, ``guide/index.html`` -> ``guide/``,
    ``404.html`` -> ``404.html``.
    """
    if html_path == "index.html":
        return ""
    if html_path.endswith("/index.html"):
        return html_path[: -len("index.html")]
    return html_path


def _join(*parts: str) -> str:
    """Join non-empty path segments with a single slash."""
    return "/".join(p for p in parts if p)


def _mount_url(mount: str, page_url: str) -> str:
    """URL path for *page_url* under *mount*, keeping the mount's slash.

    Not ``_join``: an index page's URL segment is empty and the mount
    still needs its trailing slash (``en/``, not ``en``).
    """
    return f"{mount}/{page_url}" if mount else page_url


def page_address(
    page_path: str,
    *,
    locale: str = "",
    project: str = "",
    version: str = "",
    archived: bool = False,
) -> PageAddress:
    """Map a page and its mount coordinates to every address it has.

    Args:
        page_path: Mount-relative HTML path, e.g. ``guide/index.html``.
            Must be relative, non-empty, and must not start with the
            reserved archive segment ``v/``.
        locale: Locale segment for this build.  ``""`` on a single-locale
            site -- see :func:`locale_segment`.
        project: Constituent project slug on a unified site (``""`` on a
            standalone site).
        version: Version this page was built from (``""`` for pages that
            are not version-scoped).
        archived: True when this page is a superseded version, which is
            emitted under ``v/<version>/`` instead of at the stable
            address.  Requires a version.

    Returns:
        A :class:`PageAddress`.
    """
    if not page_path:
        raise ValueError("page_path must be a non-empty relative HTML path")
    if page_path.startswith("/"):
        raise ValueError(
            f"page_path must be relative to the mount root, got {page_path!r}"
        )
    first_segment = page_path.split("/", 1)[0]
    if first_segment == ARCHIVE_PREFIX:
        raise ValueError(
            f"page path {page_path!r} starts with the reserved segment "
            f"{ARCHIVE_PREFIX!r}/, which is where superseded versions are "
            f"emitted. Rename the page."
        )
    if archived and not version:
        raise ValueError(
            "archived=True needs a version: an archive address is "
            f"{ARCHIVE_PREFIX}/<version>/<page>/ and there is no version to "
            "name"
        )

    stable_mount = _join(locale, project)
    archive_mount = (
        _join(locale, project, ARCHIVE_PREFIX, version)
        if version
        else stable_mount
    )
    mount = archive_mount if archived else stable_mount
    output_key = _join(mount, page_path)
    page_url = _to_url(page_path)

    return PageAddress(
        page_path=page_path,
        locale=locale,
        project=project,
        version=version,
        archived=archived,
        mount=mount,
        output_key=output_key,
        stable=_mount_url(stable_mount, page_url),
        pinned=_mount_url(archive_mount, page_url),
        depth=output_key.count("/"),
    )
