"""The authoring app's local server: registry, documents, preview, stream.

A single-user, local-only HTTP server on the standard library alone -- no new
runtime dependency enters selfblog for a command that only ever talks to
127.0.0.1.  It serves four things:

* the shell (the editor's own page and module, plus tinymoon's asset tree);
* the registry, and each local entry's posts;
* document read and write -- a write lands in the working tree, atomically;
* previews, rendered in memory and pushed down one server-sent-events channel.

The preview is the part with a property worth stating.  It goes through
``selfdoc_core.render.render_post``, which is the *publish* renderer handed an
in-memory buffer instead of a file: same directive resolution, same HTML pass,
same site-level addressing, and no write anywhere.  So what the author
approves on screen is the bytes readers get, and asking for a preview cannot
change the tree it previews.  Both halves are asserted by the suite.

Remote registry entries are validated but not served.  Every path that would
have to reach one refuses with "remote entries not yet served" rather than
half-working.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from selfdoc_core import effects
from selfdoc_core.utils import atomic_write

#: The editor writes working trees and answers with no authentication of any
#: kind, so the bind address is not configurable: loopback, always.
HOST = "127.0.0.1"

#: How often an idle event stream emits a comment, so a client that went away
#: is noticed rather than held forever.
_HEARTBEAT_SECONDS = 15

_CONTENT_TYPES = {
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
}


class EditorError(RuntimeError):
    """A request cannot be served, for a reason the message states."""

    status = 400


class NotFound(EditorError):
    """The thing asked for does not exist here."""

    status = 404


class RemoteNotServed(EditorError):
    """A remote registry entry was reached.  Validated, not yet served."""

    status = 501


# -- repository access --------------------------------------------------------


def require_local(entry):
    """Return *entry* if it is a local working tree, or refuse."""
    if getattr(entry, "kind", "") != "local":
        raise RemoteNotServed(
            f"remote entries not yet served: {entry.name!r} points at "
            f"{getattr(entry, 'repo', '?')}. The registry validates remote "
            f"entries in full, but serving one is not implemented -- register "
            f"a local working tree instead."
        )
    return entry


def repo_config(entry):
    """The project config of a local entry, or a refusal naming the entry."""
    from selfdoc_core.config import ConfigError, load_config

    require_local(entry)
    try:
        config = load_config(entry.path)
    except ConfigError as exc:
        raise EditorError(f"{entry.name}: {exc}") from None
    if config is None:
        raise EditorError(
            f"{entry.name}: no selfdoc.json in {entry.path}. The editor edits "
            f"selfdoc projects; this path is not one."
        )
    return config


def posts_dir_of(entry, config=None):
    """The absolute posts directory of a local entry."""
    config = config if config is not None else repo_config(entry)
    configured = (config.get("posts") or {}).get("dir", ".selfdoc/posts/")
    return os.path.join(entry.path, configured)


def repo_posts(entry):
    """Every post a local entry declares, newest first.

    Returns plain dicts carrying only what a sidebar needs -- the post bodies
    are fetched one at a time, when one is opened.
    """
    from selfblog.posts import PostError, discover_posts

    config = repo_config(entry)
    posts_dir = posts_dir_of(entry, config)
    manifest_path = os.path.join(entry.path, ".selfdoc", "manifest.json")
    try:
        posts = discover_posts(posts_dir, manifest_path=manifest_path)
    except PostError as exc:
        raise EditorError(f"{entry.name}: {exc}") from None

    return [
        {
            "path": post["path"],
            "title": post["title"],
            "date": post["date"],
            "slug": post["slug"],
            "draft": post["draft"],
            "tags": list(post["tags"]),
        }
        for post in posts
    ]


def _safe_rel(rel):
    """A post path relative to the posts directory, or a refusal.

    The editor addresses documents by a path the browser supplies, so this is
    the boundary where a path that leaves the posts directory has to stop.
    """
    if not rel:
        raise EditorError("a document path is required")
    normalized = rel.replace("\\", "/")
    if os.path.isabs(normalized) or normalized.startswith("/"):
        raise EditorError(
            f"document path {rel!r} must be relative to the posts directory"
        )
    parts = normalized.split("/")
    if ".." in parts or "." in parts or "" in parts:
        raise EditorError(
            f"document path {rel!r} must not contain '..' or empty segments"
        )
    if not normalized.endswith(".md"):
        raise EditorError(f"document path {rel!r} must name a .md file")
    return normalized


def post_path_of(entry, rel):
    """The absolute path of one post inside a local entry."""
    return os.path.join(posts_dir_of(entry), *_safe_rel(rel).split("/"))


def read_post(entry, rel):
    """The saved source of one post."""
    full = post_path_of(entry, rel)
    if not os.path.isfile(full):
        raise NotFound(f"{entry.name}: no post at {rel}")
    with open(full, encoding="utf-8") as handle:
        return handle.read()


def save_post(entry, rel, content):
    """Write a buffer to the working tree, atomically.

    Atomic because the tree is shared with everything else that reads it -- a
    build, a check, another editor -- and a half-written post is a post that
    fails to parse for whatever looked at it mid-write.
    """
    full = post_path_of(entry, rel)
    effects.makedirs(os.path.dirname(full), exist_ok=True)
    atomic_write(full, content)
    return full


def post_slug(rel, content):
    """The slug a buffer would publish under."""
    from selfblog.posts import PostError, parse_post

    try:
        return parse_post(content, _safe_rel(rel))["slug"]
    except PostError as exc:
        raise EditorError(str(exc)) from None


def render_preview(entry, rel, content):
    """Render a buffer to the exact HTML publishing it would produce.

    One renderer: this is ``selfdoc_core.render.render_post``, which is the
    build's own page pass over an in-memory overlay.  The bytes equal what
    ``build(target="posts")`` writes for the same source saved to disk, and
    nothing is written anywhere.

    Drafts are the one case with no published counterpart to equal, so a
    buffer that declares ``draft: true`` is rendered as the drafts build
    renders it.  The decision is read off the buffer, never off a mode the
    server carries: the same buffer previews the same way every time.
    """
    from selfblog.posts import PostError
    from selfdoc_core.render import render_post

    require_local(entry)
    rel = _safe_rel(rel)
    config = repo_config(entry)

    from selfdoc_core.utils import parse_frontmatter

    frontmatter, _ = parse_frontmatter(content)
    is_draft = bool(frontmatter.get("draft", False))

    try:
        return render_post(
            entry.path, rel, content,
            config=config, include_drafts=is_draft,
        )
    except PostError as exc:
        raise EditorError(str(exc)) from None
    except RuntimeError as exc:
        raise EditorError(f"{entry.name}: {exc}") from None


def preview_address(slug):
    """Where a previewed post is served, mirroring its published address."""
    return f"blog/{slug}/index.html"


# -- server state -------------------------------------------------------------


class SSEChannel:
    """The one event stream every connected shell listens on."""

    def __init__(self):
        self._clients = []
        self._lock = threading.Lock()

    def add(self, writer):
        with self._lock:
            self._clients.append(writer)

    def remove(self, writer):
        with self._lock:
            if writer in self._clients:
                self._clients.remove(writer)

    def count(self):
        with self._lock:
            return len(self._clients)

    def broadcast(self, event, payload):
        """Push one event to every client, dropping the ones that went away."""
        frame = (
            f"event: {event}\n"
            f"data: {json.dumps(payload)}\n\n"
        ).encode("utf-8")
        with self._lock:
            clients = list(self._clients)
        for writer in clients:
            try:
                writer.write(frame)
                writer.flush()
            except (BrokenPipeError, ConnectionResetError, ValueError, OSError):
                self.remove(writer)


class EditorState:
    """Everything one running editor holds: registry, assets, live previews."""

    def __init__(self, registry, tinymoon_dir, ui_dir=None):
        from selfblog.editor_assets import ui_assets_path

        self.registry = registry
        self.tinymoon_dir = tinymoon_dir
        self.ui_dir = ui_dir or ui_assets_path()
        self.channel = SSEChannel()
        self.stopping = threading.Event()
        # (repo name, published address) -> rendered HTML.  The preview pane
        # loads the document from here by URL rather than through srcdoc, so
        # the page's own relative links -- its stylesheet, its feed, its
        # siblings -- resolve against the repository's built output instead of
        # against the editor.
        self._previews = {}
        self._preview_lock = threading.Lock()

    def store_preview(self, repo_name, address, html):
        with self._preview_lock:
            self._previews[(repo_name, address)] = html

    def get_preview(self, repo_name, address):
        with self._preview_lock:
            return self._previews.get((repo_name, address))


# -- HTTP ---------------------------------------------------------------------


def _content_type(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in _CONTENT_TYPES:
        return _CONTENT_TYPES[ext]
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def _resolve_under(root, rel):
    """Join *rel* under *root*, refusing anything that escapes it."""
    root = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root, *rel.split("/")))
    if full != root and not full.startswith(root + os.sep):
        raise NotFound(f"{rel} is outside the served directory")
    return full


class EditorHandler(BaseHTTPRequestHandler):
    """One request.  ``state`` is set on the subclass by :func:`make_server`."""

    state: EditorState = None
    server_version = "selfblog-editor"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
        """Quiet: the editor's console is for the editor's own messages."""

    # -- plumbing ------------------------------------------------------------

    def _send(self, status, body, content_type):
        payload = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, status, payload):
        self._send(status, json.dumps(payload), "application/json; charset=utf-8")

    def _send_error_json(self, exc):
        status = getattr(exc, "status", 400)
        self._send_json(status, {"error": str(exc)})

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return ""
        return self.rfile.read(length).decode("utf-8")

    def _entry(self, name):
        from selfblog.editor_registry import RegistryError

        try:
            return self.state.registry.get(name)
        except RegistryError as exc:
            raise NotFound(str(exc)) from None

    def _serve_file(self, root, rel):
        full = _resolve_under(root, rel)
        if not os.path.isfile(full):
            raise NotFound(f"no such file: {rel}")
        with open(full, "rb") as handle:
            self._send(200, handle.read(), _content_type(full))

    # -- dispatch ------------------------------------------------------------

    def do_GET(self):  # noqa: N802 - stdlib signature
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        query = parse_qs(parts.query)
        try:
            self._get(path, query)
        except EditorError as exc:
            self._send_error_json(exc)
        except Exception as exc:  # pragma: no cover - defensive
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_PUT(self):  # noqa: N802 - stdlib signature
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        query = parse_qs(parts.query)
        try:
            self._put(path, query, self._read_body())
        except EditorError as exc:
            self._send_error_json(exc)
        except Exception as exc:  # pragma: no cover - defensive
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self):  # noqa: N802 - stdlib signature
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        query = parse_qs(parts.query)
        try:
            self._post(path, query, self._read_body())
        except EditorError as exc:
            self._send_error_json(exc)
        except Exception as exc:  # pragma: no cover - defensive
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})

    # -- routes --------------------------------------------------------------

    def _get(self, path, query):
        if path in ("/", "/index.html"):
            self._serve_file(self.state.ui_dir, "index.html")
            return
        if path.startswith("/ui/"):
            self._serve_file(self.state.ui_dir, path[len("/ui/"):])
            return
        if path.startswith("/tinymoon/"):
            if not self.state.tinymoon_dir:
                raise NotFound("no tinymoon assets are configured")
            self._serve_file(self.state.tinymoon_dir, path[len("/tinymoon/"):])
            return
        if path == "/events":
            self._stream_events()
            return
        if path == "/api/repos":
            self._send_json(200, {"repos": _repos_payload(self.state.registry)})
            return
        if path.startswith("/api/repos/"):
            name, _, tail = path[len("/api/repos/"):].partition("/")
            entry = self._entry(name)
            if tail == "posts":
                self._send_json(
                    200, {"repo": name, "posts": repo_posts(entry)},
                )
                return
            if tail == "document":
                rel = _one(query, "path")
                content = read_post(require_local(entry), rel)
                self._send_json(
                    200, {"repo": name, "path": rel, "content": content},
                )
                return
        if path.startswith("/preview/"):
            self._serve_preview(path[len("/preview/"):])
            return
        raise NotFound(f"no route for GET {path}")

    def _put(self, path, query, body):
        if path.startswith("/api/repos/"):
            name, _, tail = path[len("/api/repos/"):].partition("/")
            entry = self._entry(name)
            if tail == "document":
                rel = _one(query, "path")
                full = save_post(require_local(entry), rel, body)
                self._send_json(200, {
                    "repo": name, "path": rel, "saved": True,
                    "bytes": len(body.encode("utf-8")),
                    "file": full,
                })
                return
        raise NotFound(f"no route for PUT {path}")

    def _post(self, path, query, body):
        if path.startswith("/api/repos/"):
            name, _, tail = path[len("/api/repos/"):].partition("/")
            entry = self._entry(name)
            if tail == "preview":
                self._preview(name, entry, _one(query, "path"), body)
                return
        raise NotFound(f"no route for POST {path}")

    # -- preview -------------------------------------------------------------

    def _preview(self, name, entry, rel, content):
        require_local(entry)
        rel = _safe_rel(rel)
        slug = post_slug(rel, content)
        html = render_preview(entry, rel, content)

        address = preview_address(slug)
        self.state.store_preview(name, address, html)

        payload = {
            "repo": name,
            "path": rel,
            "slug": slug,
            "url": f"/preview/{name}/{address}",
            "html": html,
        }
        self.state.channel.broadcast("preview", payload)
        self._send_json(200, payload)

    def _serve_preview(self, rest):
        """Serve a previewed page, and the built assets its links reach for.

        The rendered document is the publish bytes, so its stylesheet, feed
        and sibling links are the published relative ones.  Serving the page
        at the address it publishes to, with the repository's build output
        underneath, is what makes those links resolve -- and keeps the
        document itself byte-for-byte what was rendered.
        """
        name, _, tail = rest.partition("/")
        entry = require_local(self._entry(name))
        if tail.endswith("/") or not tail:
            tail = tail + "index.html"

        stored = self.state.get_preview(name, tail)
        if stored is not None:
            self._send(200, stored, "text/html; charset=utf-8")
            return

        config = repo_config(entry)
        output_dir = os.path.join(entry.path, config["output"].rstrip("/"))
        if not os.path.isdir(output_dir):
            raise NotFound(
                f"{name}: no build output at {output_dir}. Run a posts build "
                f"there for the preview to load its stylesheet and assets."
            )
        self._serve_file(output_dir, tail)

    # -- events --------------------------------------------------------------

    def _stream_events(self):
        """Hold the connection open as the one server-sent-events channel."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        channel = self.state.channel
        channel.add(self.wfile)
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            waited = 0
            while not self.state.stopping.is_set():
                if self.state.stopping.wait(timeout=1.0):
                    break
                waited += 1
                if waited >= _HEARTBEAT_SECONDS:
                    waited = 0
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ValueError, OSError):
            pass
        finally:
            channel.remove(self.wfile)
        self.close_connection = True


def _one(query, key):
    """The single value of a query parameter, or the empty string."""
    values = query.get(key) or []
    return values[0] if values else ""


def _repos_payload(registry):
    """The registry as the shell sees it."""
    payload = []
    for entry in registry:
        if entry.kind == "local":
            payload.append({
                "name": entry.name, "kind": "local", "path": entry.path,
                "served": True,
            })
        else:
            payload.append({
                "name": entry.name, "kind": "remote", "repo": entry.repo,
                "ref": entry.ref, "render": entry.render, "served": False,
            })
    return payload


class EditorHTTPServer(ThreadingHTTPServer):
    """A threading server that also releases its held event streams."""

    daemon_threads = True
    allow_reuse_address = True

    state: EditorState = None

    def shutdown(self):
        if self.state is not None:
            self.state.stopping.set()
        super().shutdown()


def make_server(state, port):
    """Bind the editor server to loopback on *port*.

    ``port`` 0 binds an ephemeral port, which is what the suite uses; the
    command itself requires an explicit one.
    """

    class BoundHandler(EditorHandler):
        pass

    BoundHandler.state = state
    server = EditorHTTPServer((HOST, port), BoundHandler)
    server.state = state
    return server


def serve(state, port, on_ready=None):
    """Run the editor until interrupted, then stop cleanly.

    Ctrl-C is the graceful stop: the accept loop ends, every held event
    stream is released, and the listening socket is closed.
    """
    server = make_server(state, port)
    if on_ready is not None:
        on_ready(server.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0
