"""The authoring server: registry -> posts -> document read/write -> preview.

Everything here runs against a real ``ThreadingHTTPServer`` bound to an
ephemeral loopback port, because the properties worth asserting are the
wire ones: what the shell can ask for, what it gets back, what a refusal
looks like, and -- the one that the whole preview design exists for -- that
asking for a preview leaves the working tree untouched.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import threading

import pytest

from selfblog.editor_assets import TINYMOON_REQUIRED
from selfblog.editor_registry import load_registry
from selfblog.editor_server import (
    EditorError,
    EditorState,
    RemoteNotServed,
    make_server,
    read_post,
    render_preview,
    repo_posts,
    save_post,
)
from conftest import default_config

_POST = (
    "hello.md",
    "---\ntitle: Hello World\ndate: 2024-01-15\nslug: hello-world\n"
    "tags: [release]\ndraft: false\ndirectives: false\n---\n"
    "# Hello World\n\nThis is the post content.\n",
)

_DRAFT = (
    "later.md",
    "---\ntitle: Later\ndate: 2024-05-01\nslug: later\n"
    "tags: []\ndraft: true\ndirectives: false\n---\nNot yet.\n",
)


def _make_project(root, posts=(_POST,)):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(default_config(docs="docs/", output="docs/_build/"), f)

    src = os.path.join(root, "src")
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Example package."""\n')

    docs = os.path.join(root, "docs")
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test Project\n\nWelcome.\n")

    posts_dir = os.path.join(root, ".selfdoc", "posts")
    os.makedirs(posts_dir, exist_ok=True)
    for name, body in posts:
        with open(os.path.join(posts_dir, name), "w", encoding="utf-8") as f:
            f.write(body)
    return root


def _fake_tinymoon(root):
    for rel in TINYMOON_REQUIRED:
        full = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(f"/* {rel} */\n")
    return root


def _tree_fingerprint(root):
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            stat = os.stat(full)
            with open(full, "rb") as f:
                body = hashlib.sha256(f.read()).hexdigest()
            digest.update(
                repr((os.path.relpath(full, root), stat.st_size,
                      stat.st_mtime_ns, body)).encode()
            )
    return digest.hexdigest()


@pytest.fixture()
def workspace(tmp_path):
    """A registry naming one local project and one (unserved) remote."""
    project = _make_project(os.path.join(str(tmp_path), "proj"),
                            posts=(_POST, _DRAFT))
    assets = _fake_tinymoon(os.path.join(str(tmp_path), "assets"))
    registry_path = os.path.join(str(tmp_path), "registry.toml")
    with open(registry_path, "w", encoding="utf-8") as f:
        f.write(f"""
[[repo]]
name = "proj"
kind = "local"
path = "{project}"

[[repo]]
name = "afar"
kind = "remote"
repo = "smm-h/afar"
ref = "main"
cache = "{os.path.join(str(tmp_path), "cache")}"
render = true
""")
    state = EditorState(load_registry(registry_path), assets)
    return {"project": project, "assets": assets, "state": state}


@pytest.fixture()
def live(workspace):
    """The server, bound to an ephemeral loopback port and torn down."""
    server = make_server(workspace["state"], 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"port": server.server_port, **workspace}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def _request(port, method, path, body=None, timeout=10):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        payload = body.encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload)
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        conn.close()


def _json(port, method, path, body=None):
    status, text = _request(port, method, path, body)
    return status, json.loads(text)


class TestBinding:
    def test_the_server_binds_loopback_only(self, live):
        assert live["port"] > 0
        status, _ = _request(live["port"], "GET", "/api/repos")
        assert status == 200

    def test_the_host_is_hard_coded(self):
        from selfblog.editor_server import HOST

        assert HOST == "127.0.0.1"


class TestTheShell:
    def test_the_root_serves_the_shell(self, live):
        status, text = _request(live["port"], "GET", "/")
        assert status == 200
        assert "tinymoon" in text
        assert "/ui/app.js" in text

    def test_the_app_module_is_served(self, live):
        status, text = _request(live["port"], "GET", "/ui/app.js")
        assert status == 200
        assert "createEditor" in text

    def test_the_tinymoon_editor_tier_is_served(self, live):
        for rel in ("js/editor.js", "js/completion.js", "css/editor.css"):
            status, text = _request(live["port"], "GET", f"/tinymoon/{rel}")
            assert status == 200, rel
            assert rel in text

    def test_an_asset_outside_the_tree_is_refused(self, live):
        status, _ = _request(
            live["port"], "GET", "/tinymoon/../../etc/passwd",
        )
        assert status in (400, 404)

    def test_an_unknown_route_is_a_404(self, live):
        status, _ = _request(live["port"], "GET", "/nope")
        assert status == 404


class TestRepoListing:
    def test_every_registry_entry_is_listed(self, live):
        status, body = _json(live["port"], "GET", "/api/repos")
        assert status == 200
        assert [r["name"] for r in body["repos"]] == ["proj", "afar"]
        assert body["repos"][0]["kind"] == "local"
        assert body["repos"][1]["kind"] == "remote"

    def test_a_local_entry_lists_its_posts(self, live):
        status, body = _json(live["port"], "GET", "/api/repos/proj/posts")
        assert status == 200
        by_path = {p["path"]: p for p in body["posts"]}
        assert set(by_path) == {"hello.md", "later.md"}
        assert by_path["hello.md"]["title"] == "Hello World"
        assert by_path["hello.md"]["draft"] is False
        assert by_path["later.md"]["draft"] is True

    def test_an_unknown_repo_is_a_404(self, live):
        status, body = _json(live["port"], "GET", "/api/repos/ghost/posts")
        assert status == 404
        assert "ghost" in body["error"]


class TestRemoteEntriesAreNotServedYet:
    def test_listing_a_remote_entrys_posts_hard_errors(self, live):
        status, body = _json(live["port"], "GET", "/api/repos/afar/posts")
        assert status == 501
        assert "remote entries not yet served" in body["error"]

    def test_reading_a_remote_document_hard_errors(self, live):
        status, body = _json(
            live["port"], "GET", "/api/repos/afar/document?path=a.md",
        )
        assert status == 501
        assert "remote entries not yet served" in body["error"]

    def test_the_helper_refuses_directly(self, workspace):
        entry = workspace["state"].registry.get("afar")
        with pytest.raises(RemoteNotServed, match="remote entries not yet served"):
            repo_posts(entry)


class TestDocumentRead:
    def test_reading_a_post_returns_its_source(self, live):
        status, body = _json(
            live["port"], "GET", "/api/repos/proj/document?path=hello.md",
        )
        assert status == 200
        assert body["content"] == _POST[1]
        assert body["path"] == "hello.md"

    def test_a_missing_document_is_a_404(self, live):
        status, body = _json(
            live["port"], "GET", "/api/repos/proj/document?path=ghost.md",
        )
        assert status == 404
        assert "ghost.md" in body["error"]

    @pytest.mark.parametrize("bad", ["../secret.md", "/etc/passwd", ""])
    def test_a_path_outside_the_posts_directory_is_refused(self, live, bad):
        from urllib.parse import quote

        status, _ = _request(
            live["port"], "GET",
            f"/api/repos/proj/document?path={quote(bad, safe='')}",
        )
        assert status == 400

    def test_the_helper_refuses_an_escaping_path(self, workspace):
        entry = workspace["state"].registry.get("proj")
        with pytest.raises(EditorError, match=r"\.\."):
            read_post(entry, "../../etc/passwd")


class TestDocumentWrite:
    def test_a_put_saves_to_the_working_tree(self, live):
        edited = _POST[1].replace("post content", "SAVED content")
        status, body = _json(
            live["port"], "PUT",
            "/api/repos/proj/document?path=hello.md", edited,
        )
        assert status == 200
        assert body["saved"] is True

        on_disk = os.path.join(
            live["project"], ".selfdoc", "posts", "hello.md",
        )
        with open(on_disk, encoding="utf-8") as f:
            assert f.read() == edited

    def test_a_put_can_create_a_new_post(self, live):
        source = (
            "---\ntitle: Brand New\ndate: 2024-06-01\nslug: brand-new\n"
            "tags: []\ndraft: true\ndirectives: false\n---\nFresh.\n"
        )
        status, _ = _json(
            live["port"], "PUT",
            "/api/repos/proj/document?path=brand-new.md", source,
        )
        assert status == 200
        with open(os.path.join(live["project"], ".selfdoc", "posts",
                               "brand-new.md"), encoding="utf-8") as f:
            assert f.read() == source

    def test_a_put_to_a_remote_entry_hard_errors(self, live):
        status, body = _json(
            live["port"], "PUT",
            "/api/repos/afar/document?path=a.md", "x",
        )
        assert status == 501
        assert "remote entries not yet served" in body["error"]

    def test_the_helper_refuses_an_escaping_path(self, workspace):
        entry = workspace["state"].registry.get("proj")
        with pytest.raises(EditorError):
            save_post(entry, "../escape.md", "nope")


class TestPreviewWritesNothing:
    def test_the_preview_helper_leaves_the_tree_alone(self, workspace):
        entry = workspace["state"].registry.get("proj")
        edited = _POST[1].replace("post content", "buffer content")

        before = _tree_fingerprint(workspace["project"])
        html = render_preview(entry, "hello.md", edited)
        after = _tree_fingerprint(workspace["project"])

        assert "buffer content" in html
        assert after == before

    def test_the_preview_endpoint_leaves_the_tree_alone(self, live):
        edited = _POST[1].replace("post content", "over the wire")

        before = _tree_fingerprint(live["project"])
        status, body = _json(
            live["port"], "POST",
            "/api/repos/proj/preview?path=hello.md", edited,
        )
        after = _tree_fingerprint(live["project"])

        assert status == 200
        assert "over the wire" in body["html"]
        assert after == before, "the preview endpoint mutated the working tree"

    def test_a_draft_buffer_previews(self, workspace):
        """A draft has no published page, so previewing it is the only view."""
        entry = workspace["state"].registry.get("proj")
        html = render_preview(entry, "later.md", _DRAFT[1])
        assert "Not yet." in html

    def test_a_broken_buffer_reports_the_defect(self, live):
        broken = "---\ntitle: No Date\ndirectives: false\n---\nbody\n"
        status, body = _json(
            live["port"], "POST",
            "/api/repos/proj/preview?path=hello.md", broken,
        )
        assert status == 400
        assert "date" in body["error"].lower()

    def test_previewing_a_remote_entry_hard_errors(self, live):
        status, body = _json(
            live["port"], "POST",
            "/api/repos/afar/preview?path=a.md", "x",
        )
        assert status == 501
        assert "remote entries not yet served" in body["error"]


class TestTheEventStream:
    def test_a_preview_is_streamed_to_a_connected_client(self, live):
        conn = http.client.HTTPConnection("127.0.0.1", live["port"], timeout=20)
        conn.request("GET", "/events")
        response = conn.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "text/event-stream"

        edited = _POST[1].replace("post content", "streamed content")

        def _post():
            _request(live["port"], "POST",
                     "/api/repos/proj/preview?path=hello.md", edited)

        poster = threading.Thread(target=_post, daemon=True)
        poster.start()

        event_name = None
        payload = None
        try:
            while payload is None:
                line = response.fp.readline()
                if not line:
                    break
                line = line.decode("utf-8").rstrip("\n")
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and event_name == "preview":
                    payload = json.loads(line.split(":", 1)[1].strip())
        finally:
            poster.join(timeout=10)
            conn.close()

        assert payload is not None, "no preview event arrived on the stream"
        assert payload["repo"] == "proj"
        assert payload["path"] == "hello.md"
        assert "streamed content" in payload["html"]
