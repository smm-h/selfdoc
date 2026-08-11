"""Tests for the Git Data API push path: bytes, skipping and deletion.

``push_files_to_repo`` used to be text-only (``str.encode`` on every value),
upload-everything (no comparison against what the branch already held) and
add-only (no way to remove a path).  A binary asset could not travel through
it at all, a regenerated artifact re-uploaded itself on every run, and a file
that should disappear stayed forever.
"""

import base64
import hashlib
import json
import subprocess

import pytest

from selfblog.assembly import git_blob_sha1, push_files_to_repo

# A tiny real PNG: the bytes below are not valid UTF-8 anywhere in the middle,
# so anything that round-trips them through str is guaranteed to fail.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeRemote:
    """A mocked GitHub Git Data API holding one branch's blobs."""

    def __init__(self, blobs: dict[str, bytes] | None = None):
        self.blobs = dict(blobs or {})
        self.truncated = False
        self.calls: list[dict] = []
        self.uploaded: list[bytes] = []
        self.tree_payloads: list[dict] = []
        self.commits: list[dict] = []

    def __call__(self, cmd, *, input=None, capture_output=True, text=True,
                 timeout=30, read=False, resource=None, grant=None,
                 cwd=None, env=None, check=False, skip_if_current=None):
        joined = " ".join(str(c) for c in cmd)
        self.calls.append({"cmd": list(cmd), "input": input})
        stdout = ""
        if "/git/ref/heads/" in joined:
            stdout = "headsha"
        elif "/git/commits/headsha" in joined:
            stdout = "basetree"
        elif "/git/trees/basetree" in joined:
            stdout = json.dumps({
                "sha": "basetree",
                "truncated": self.truncated,
                "tree": [
                    {"path": path, "type": "blob", "mode": "100644",
                     "sha": git_blob_sha1(data)}
                    for path, data in sorted(self.blobs.items())
                ],
            })
        elif "/git/blobs" in joined:
            payload = json.loads(input)
            self.uploaded.append(base64.b64decode(payload["content"]))
            stdout = f"blob{len(self.uploaded)}"
        elif "/git/trees" in joined:
            self.tree_payloads.append(json.loads(input))
            stdout = "newtree"
        elif "/git/commits" in joined:
            self.commits.append(json.loads(input))
            stdout = "newcommit"
        elif "/git/refs/heads/" in joined:
            stdout = "newcommit"
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout=stdout, stderr="",
        )

    @property
    def blob_uploads(self):
        return [c for c in self.calls if "/git/blobs" in " ".join(str(x) for x in c["cmd"])]

    @property
    def commit_calls(self):
        return [c for c in self.calls
                if "/git/commits" in " ".join(str(x) for x in c["cmd"])
                and "--method" in c["cmd"]]


def _push(remote, *args, **kwargs):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("selfblog.assembly.effects.run", remote)
        return push_files_to_repo(*args, **kwargs)


# -- git blob hashing ---------------------------------------------------------


def test_git_blob_sha1_matches_gits_own_object_id():
    """The local hash is git's, so it is comparable with the API's shas."""
    # `printf 'hello\n' | git hash-object --stdin`
    assert git_blob_sha1(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_git_blob_sha1_hashes_the_header_and_the_bytes():
    data = PNG_BYTES
    expected = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    assert git_blob_sha1(data) == expected


# -- binary content -----------------------------------------------------------


def test_bytes_content_round_trips_byte_identically():
    remote = FakeRemote()
    _push(remote, "owner/repo", {"site/logo.png": PNG_BYTES}, "add image")
    assert remote.uploaded == [PNG_BYTES]


def test_bytes_and_text_travel_in_one_commit():
    remote = FakeRemote()
    result = _push(
        remote, "owner/repo",
        {"site/logo.png": PNG_BYTES, "site/index.html": "<html/>"},
        "mixed",
    )
    assert result.changed is True
    assert sorted(remote.uploaded) == sorted([PNG_BYTES, b"<html/>"])
    assert len(remote.commit_calls) == 1


def test_binary_content_survives_a_round_trip_through_the_tree_payload():
    """The path the image travels by is base64 of the raw bytes, not of text."""
    remote = FakeRemote()
    _push(remote, "owner/repo", {"a.png": PNG_BYTES}, "img")
    blob_payload = json.loads(remote.blob_uploads[0]["input"])
    assert blob_payload["encoding"] == "base64"
    assert base64.b64decode(blob_payload["content"]) == PNG_BYTES


# -- unchanged files ----------------------------------------------------------


def test_unchanged_file_uploads_no_blob():
    remote = FakeRemote({"site/index.html": b"<html/>"})
    result = _push(remote, "owner/repo", {"site/index.html": "<html/>"}, "noop")
    assert remote.uploaded == []
    assert result.changed is False
    assert result.sha == "headsha"


def test_unchanged_push_creates_no_commit():
    remote = FakeRemote({"a.txt": b"same"})
    _push(remote, "owner/repo", {"a.txt": "same"}, "noop")
    assert remote.commit_calls == []
    assert remote.tree_payloads == []


def test_unchanged_binary_file_uploads_no_blob():
    remote = FakeRemote({"site/logo.png": PNG_BYTES})
    result = _push(remote, "owner/repo", {"site/logo.png": PNG_BYTES}, "noop")
    assert remote.uploaded == []
    assert result.changed is False


def test_only_the_changed_file_of_a_pair_uploads():
    remote = FakeRemote({"a.txt": b"same", "b.txt": b"old"})
    result = _push(
        remote, "owner/repo", {"a.txt": "same", "b.txt": "new"}, "one change",
    )
    assert remote.uploaded == [b"new"]
    assert [e["path"] for e in remote.tree_payloads[0]["tree"]] == ["b.txt"]
    assert result.uploaded == ("b.txt",)


def test_a_truncated_remote_tree_is_a_hard_error():
    """Unchanged-file detection cannot be silently skipped."""
    remote = FakeRemote({"a.txt": b"x"})
    remote.truncated = True
    with pytest.raises(RuntimeError, match="too large"):
        _push(remote, "owner/repo", {"a.txt": "y"}, "msg")


# -- deletion -----------------------------------------------------------------


def test_deleted_path_disappears_in_one_commit():
    remote = FakeRemote({"site/old.html": b"gone soon", "site/keep.html": b"stay"})
    result = _push(
        remote, "owner/repo", {}, "remove", delete_paths=["site/old.html"],
    )
    entries = remote.tree_payloads[0]["tree"]
    assert entries == [
        {"path": "site/old.html", "mode": "100644", "type": "blob", "sha": None},
    ]
    assert len(remote.commit_calls) == 1
    assert result.deleted == ("site/old.html",)
    assert result.changed is True


def test_deletion_and_upload_share_one_commit():
    remote = FakeRemote({"site/old.html": b"gone", "site/index.html": b"old"})
    _push(
        remote, "owner/repo", {"site/index.html": "new"}, "replace",
        delete_paths=["site/old.html"],
    )
    entries = {e["path"]: e["sha"] for e in remote.tree_payloads[0]["tree"]}
    assert entries["site/old.html"] is None
    assert entries["site/index.html"] == "blob1"
    assert len(remote.commit_calls) == 1


def test_deleting_an_absent_path_is_not_an_error_and_not_a_commit():
    remote = FakeRemote({"a.txt": b"x"})
    result = _push(remote, "owner/repo", {}, "msg", delete_paths=["never/here.txt"])
    assert result.changed is False
    assert remote.commit_calls == []


def test_deletion_only_push_is_accepted_without_files():
    remote = FakeRemote({"a.txt": b"x"})
    result = _push(remote, "owner/repo", {}, "msg", delete_paths=["a.txt"])
    assert result.changed is True


def test_nothing_to_push_at_all_still_raises():
    remote = FakeRemote()
    with pytest.raises(ValueError, match="empty"):
        _push(remote, "owner/repo", {}, "msg")
