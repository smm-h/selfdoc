"""URL builder interface for decoupling URL generation from hardcoded base_url usage.

Project identification uses two canonical identifiers:
- slug: machine identifier (URL-safe, lowercase, hyphens) used in URLs,
  directory names, cross-references, frontmatter, and manifest keys.
- name: human-readable display name (may contain spaces, capitals, special
  characters) used in UI, homepages, and documentation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


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


class TopologyURLBuilder:
    """URLBuilder for topology-aware multi-project deployments.

    Generates URLs incorporating the project slug under a shared docs base.
    For example, with docs_base="https://docs.smmh.dev" and slug="selfdoc",
    page_url("guide/") returns "https://docs.smmh.dev/selfdoc/guide/".
    """

    def __init__(
        self,
        docs_base: str,
        slug: str,
        posts_base: str | None = None,
        projects: dict[str, str] | None = None,
    ) -> None:
        self._docs_base = docs_base.rstrip("/")
        self._slug = slug
        self._posts_base = posts_base.rstrip("/") if posts_base else None
        self._projects = projects or {}

    def page_url(self, path: str) -> str:
        """Return the absolute URL for a page path under this project's slug."""
        path = path.lstrip("/")
        if not path:
            return f"{self._docs_base}/{self._slug}/"
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
