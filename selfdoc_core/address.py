"""The single addressing authority for built pages.

One function -- :func:`page_address` -- decides, for a page and the
locale/project/version it belongs to, all four things the rest of the
build needs:

* ``output_key``  -- where the page file lands under the output root
  (``en/1.0.0/guide/index.html``).
* ``pinned``      -- the version-pinned URL path for that page
  (``en/1.0.0/guide/``).  This is what the site emits today.
* ``stable``      -- the version-free URL path for the same page
  (``en/guide/``).  Not emitted yet; a later scheme change swaps the
  emitted address from ``pinned`` to ``stable`` *inside this function*
  instead of across the codebase.
* ``depth``       -- how many directory levels the output key sits below
  the output root, and from it the two relative hops every page needs:
  ``to_site_root`` (back to the output root, where the shared assets
  live) and ``to_mount_root`` (back to this page's own mount, where its
  sibling pages live).

The mount is composed from three ordered coordinates -- locale, project,
version -- so a standalone site mounts at ``en/1.0.0`` and a unified site
mounts each constituent at ``en/<slug>/1.0.0``.  Nothing outside this
module assembles those segments into a path.

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

__all__ = ["PageAddress", "page_address"]


@dataclass(frozen=True, slots=True)
class PageAddress:
    """Every address a single built page has.

    Attributes:
        page_path: The mount-relative HTML path (e.g. ``guide/index.html``).
        locale: Locale segment of the mount (``""`` when unlocalized).
        project: Constituent-project segment of the mount (``""`` on a
            standalone site).
        version: Version segment of the mount (``""`` for pages that are
            not version-scoped).
        mount: The output prefix this page is built under (``en/1.0.0``,
            ``en/core/1.0.0``, ``en``, or ``""``).
        output_key: Path of the page file relative to the output root.
        pinned: Version-pinned URL path for the page.
        stable: Version-free URL path for the page.
        depth: Directory levels between the page and the output root.
    """

    page_path: str
    locale: str
    project: str
    version: str
    mount: str
    output_key: str
    pinned: str
    stable: str
    depth: int

    @property
    def stable_mount(self) -> str:
        """The version-free mount: where unversioned pages of this site sit."""
        return _join(self.locale, self.project)

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

        Unversioned pages (``versioned: false``) are built at
        ``<locale>/<project>/`` with no version segment, so a versioned
        page reaching one has to climb one level further than
        :attr:`to_mount_root`.  On an unversioned page the two hops are
        the same.
        """
        mount_depth = len([p for p in self.stable_mount.split("/") if p])
        return "../" * (self.depth - mount_depth)


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


def page_address(
    page_path: str,
    *,
    locale: str = "",
    project: str = "",
    version: str = "",
) -> PageAddress:
    """Map a page and its mount coordinates to every address it has.

    Args:
        page_path: Mount-relative HTML path, e.g. ``guide/index.html``.
            Must be relative and non-empty.
        locale: Locale code for this build (``""`` for an unlocalized build).
        project: Constituent project slug on a unified site (``""`` on a
            standalone site).
        version: Version string (``""`` for pages that are not
            version-scoped).  A version requires a locale, because the
            emitted scheme always starts with the locale segment.

    Returns:
        A :class:`PageAddress`.
    """
    if not page_path:
        raise ValueError("page_path must be a non-empty relative HTML path")
    if page_path.startswith("/"):
        raise ValueError(
            f"page_path must be relative to the mount root, got {page_path!r}"
        )
    if version and not locale:
        raise ValueError(
            f"version {version!r} was given without a locale; the emitted "
            f"scheme starts at the locale segment, so a bare version has no "
            f"address"
        )
    if project and not locale:
        raise ValueError(
            f"project {project!r} was given without a locale; the emitted "
            f"scheme starts at the locale segment"
        )

    mount = _join(locale, project, version)
    stable_mount = _join(locale, project)
    output_key = _join(mount, page_path)
    page_url = _to_url(page_path)

    return PageAddress(
        page_path=page_path,
        locale=locale,
        project=project,
        version=version,
        mount=mount,
        output_key=output_key,
        # Not _join: an index page's URL segment is empty, and the mount
        # still needs its trailing slash ("en/1.0.0/", not "en/1.0.0").
        pinned=f"{mount}/{page_url}" if mount else page_url,
        stable=f"{stable_mount}/{page_url}" if stable_mount else page_url,
        depth=output_key.count("/"),
    )
