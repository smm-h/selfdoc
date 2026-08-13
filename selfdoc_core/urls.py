"""URL builder interface for decoupling URL generation from hardcoded base_url usage, supporting locale-prefixed and versioned paths.

Project identification uses two canonical identifiers:
- slug: machine identifier (URL-safe, lowercase, hyphens) used in URLs,
  directory names, cross-references, frontmatter, and manifest keys.
- name: human-readable display name (may contain spaces, capitals, special
  characters) used in UI, homepages, and documentation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from selfdoc_core.address import is_site_level


@runtime_checkable
class URLBuilder(Protocol):
    """Protocol for building absolute URLs from relative paths."""

    def page_url(self, path: str) -> str:
        """Return the absolute URL for a page path (e.g. 'guide/' -> 'https://example.com/guide/')."""
        ...

    def asset_url(self, path: str) -> str:
        """Return the absolute URL for an asset path (e.g. 'og-index.png')."""
        ...

    def feed_url(self) -> str:
        """Return the absolute URL for the Atom feed."""
        ...

    def base(self) -> str:
        """Return the base URL string (no trailing slash)."""
        ...

    def mounted(self) -> bool:
        """Whether this project is served under a shared site's mount.

        A mounted project's own output root is not the served root: the
        site serves it under its slug, and serves the site-level pages
        (posts) from the site root instead.  The two roots are different
        directories, so a reference crossing between them has to climb out
        of one and back into the other.  Every surface that writes such a
        reference asks here rather than sniffing config.
        """
        ...

    def mount_prefix(self) -> str:
        """The path segments the site serves this project under.

        ``""`` for a project that is its own site; ``"<slug>/"`` for one the
        site mounts.  This is what turns a hop to the *project's* output
        root into a hop to the *site's* root, and back: a reference crossing
        the mount boundary is still document-relative, which is what lets
        the same tree resolve on production, on a local preview and on a
        mirror.  An absolute URL there resolves on exactly one host.
        """
        ...

    def site_root(self) -> str:
        """Return the URL of the served site's root, with a trailing slash.

        For a standalone project that is its own base; for a mounted one
        it is the shared site's base, above this project's slug.  Absolute,
        so it belongs to metadata -- a visible link crosses the mount with
        :meth:`mount_prefix` instead.
        """
        ...


class SimpleURLBuilder:
    """Straightforward URLBuilder that joins a base URL with paths.

    Strips trailing slashes from the base URL and handles path joining
    so that ``base_url + "/" + path`` never produces double slashes.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def page_url(self, path: str) -> str:
        """Return the absolute URL for a page path."""
        path = path.lstrip("/")
        if not path:
            return f"{self._base_url}/"
        return f"{self._base_url}/{path}"

    def asset_url(self, path: str) -> str:
        """Return the absolute URL for an asset path."""
        path = path.lstrip("/")
        if not path:
            return f"{self._base_url}/"
        return f"{self._base_url}/{path}"

    def feed_url(self) -> str:
        """Return the absolute URL for the Atom feed."""
        return f"{self._base_url}/feed.xml"

    def base(self) -> str:
        """Return the base URL string (no trailing slash)."""
        return self._base_url

    def mounted(self) -> bool:
        """A standalone project is not mounted: its output root is served."""
        return False

    def mount_prefix(self) -> str:
        """No mount: the project's output root already is the site root."""
        return ""

    def site_root(self) -> str:
        """The served root, which for a standalone project is its own base."""
        return f"{self._base_url}/"


class TopologyURLBuilder:
    """URLBuilder for topology-aware multi-project deployments.

    Generates URLs incorporating the project slug under a shared docs base.
    For example, with docs_base="https://docs.smmh.dev" and slug="selfdoc",
    page_url("guide/") returns "https://docs.smmh.dev/selfdoc/guide/".

    Site-level pages are the exception, and the reason this class rather
    than its callers decides: a post is a citizen of the site, not of the
    project that wrote it.  The site serves every project's posts from one
    shared ``blog/`` at the site root, so ``page_url("blog/hello/")``
    returns "https://docs.smmh.dev/blog/hello/" with no slug segment.
    Assets keep the slug -- a post's OG card, stylesheet and search index
    are the project's own files and stay in the project's subtree.
    """

    def __init__(
        self,
        docs_base: str,
        slug: str,
        projects: dict[str, str] | None = None,
    ) -> None:
        self._docs_base = docs_base.rstrip("/")
        self._slug = slug
        self._projects = projects or {}

    def page_url(self, path: str) -> str:
        """Return the absolute URL for a page path.

        Under this project's slug, unless the path is site-level -- see
        the class docstring.
        """
        path = path.lstrip("/")
        if not path:
            return f"{self._docs_base}/{self._slug}/"
        if is_site_level(path):
            return f"{self._docs_base}/{path}"
        return f"{self._docs_base}/{self._slug}/{path}"

    def asset_url(self, path: str) -> str:
        """Return the absolute URL for an asset path under this project's slug."""
        path = path.lstrip("/")
        if not path:
            return f"{self._docs_base}/{self._slug}/"
        return f"{self._docs_base}/{self._slug}/{path}"

    def feed_url(self) -> str:
        """Return the absolute URL for the Atom feed."""
        return f"{self._docs_base}/{self._slug}/feed.xml"

    def base(self) -> str:
        """Return the base URL string (docs_base/slug, no trailing slash)."""
        return f"{self._docs_base}/{self._slug}"

    def mounted(self) -> bool:
        """A topology project is mounted: the site serves it under its slug."""
        return True

    def mount_prefix(self) -> str:
        """The slug segment the site serves this project's output under."""
        return f"{self._slug}/"

    def site_root(self) -> str:
        """The shared site's root, above this project's slug."""
        return f"{self._docs_base}/"

    def cross_project_url(self, project_slug: str, path: str = "") -> str:
        """Generate a URL to another project's content using the projects dict.

        Falls back to docs_base/project_slug if the project is not in the
        explicit projects mapping.
        """
        base = self._projects.get(project_slug)
        if base is None:
            base = f"{self._docs_base}/{project_slug}"
        else:
            base = base.rstrip("/")
        path = path.lstrip("/")
        if not path:
            return f"{base}/"
        return f"{base}/{path}"
