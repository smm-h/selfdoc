"""URL builder interface for decoupling URL generation from hardcoded base_url usage."""

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
