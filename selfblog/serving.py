"""Static-file primitives shared by selfblog's two local servers.

The authoring app (:mod:`selfblog.editor_server`) and the assembly preview
(:mod:`selfblog.preview`) both hand bytes off a disk tree to a browser on
loopback.  Two questions are the same in both -- what content type a file
is served as, and what counts as a path inside the served root -- so they
are answered here once rather than twice, slightly differently.

Both servers bind :data:`HOST` and nothing else.  Neither authenticates
anything: the editor writes working trees and the preview serves an
unreleased site, so the bind address is not configurable.
"""

from __future__ import annotations

import mimetypes
import os

__all__ = ["CONTENT_TYPES", "HOST", "content_type", "resolve_under"]

#: The one address either server binds.
HOST = "127.0.0.1"

#: Content types the platform's mimetypes database gets wrong often enough
#: to be worth stating.  Anything absent falls through to ``mimetypes``.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".map": "application/json; charset=utf-8",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".xml": "application/xml; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".wasm": "application/wasm",
    ".webmanifest": "application/manifest+json",
}


def content_type(path: str) -> str:
    """Return the content type *path* is served as."""
    ext = os.path.splitext(path)[1].lower()
    if ext in CONTENT_TYPES:
        return CONTENT_TYPES[ext]
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def resolve_under(root: str, rel: str) -> str | None:
    """Join *rel* under *root*, or None when the result escapes *root*.

    Symlinks are resolved before the containment test, so a link inside the
    served tree cannot be followed out of it.  The caller decides what an
    escape looks like on the wire -- the editor answers a refusal, the
    preview answers its 404 page.
    """
    root = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root, *rel.split("/")))
    if full != root and not full.startswith(root + os.sep):
        return None
    return full
