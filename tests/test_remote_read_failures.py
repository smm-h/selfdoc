"""A failed read of the assembly is never the same thing as an absent file.

``fetch_remote_text(..., missing_ok=True)`` used to map *every* gh failure --
a rate limit, an expired token, a 502, a DNS failure -- to the empty string,
which is exactly what a genuinely absent file returns.  Every caller then read
that empty string as "this file does not exist yet", which is the initial
state of the published-file record and the membership record.

The consequence was silent destruction of another party's state.  With the
claims-record read failing transiently, ``publish_project_docs`` believed the
project had never published anything, wrote a record naming only the docs
owner, and destroyed the release owner's claims -- so the next release pruned
nothing it should have pruned and retirement no longer knew about the pages.
Under the same failure ``retire_project`` saw no claims at all and left the
project's posts on the blog forever.

Absence is now one outcome (an explicit HTTP 404) and failure is another (a
hard error naming the operation and what gh said).  Nothing is written when a
read fails.
"""

import base64
import json
import subprocess

import pytest

from selfblog.assembly import (
    RemoteReadError,
    RosterEntry,
    fetch_remote_text,
    load_remote_roster,
    publish_project_docs,
    render_roster,
    retire_project,
)
from tests.test_docs_publish import AssemblyRemote, _build, _shape

REPO = "owner/assembly"

ROSTER_TEXT = render_roster([
    RosterEntry("alpha", "owner/alpha"),
    RosterEntry("beta", "owner/beta"),
])

RATE_LIMIT = (
    "gh: API rate limit exceeded for user ID 1234. "
    "(HTTP 403)"
)


class FailingReads(AssemblyRemote):
    """An assembly whose Contents API fails for the paths named in *failing*.

    Every other read behaves exactly as the healthy fake does, so a test can
    fail one read and leave the rest of the publish's reads intact -- which
    is the shape of a real transient failure.
    """

    def __init__(self, failing, stderr=RATE_LIMIT, **kwargs):
        super().__init__(**kwargs)
        self.failing = set(failing)
        self.fail_stderr = stderr

    def __call__(self, cmd, **kwargs):
        joined = " ".join(str(c) for c in cmd)
        if "/contents/" in joined:
            path = joined.split("/contents/", 1)[1].split(" ")[0]
            if path in self.failing:
                self.calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
                return subprocess.CompletedProcess(
                    args=list(cmd), returncode=1, stdout="",
                    stderr=self.fail_stderr,
                )
        return super().__call__(cmd, **kwargs)


def _remote(cls=AssemblyRemote, *, blobs=None, contents=None, **kwargs):
    base = {"roster.toml": ROSTER_TEXT}
    base.update(contents or {})
    return cls(blobs=blobs, contents=base, **kwargs)


def _run(remote, fn, *args, **kwargs):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("selfblog.assembly.effects.run", remote)
        return fn(*args, **kwargs)


def _publishable(tmp_path):
    output = _build(tmp_path, pages=("index.html",))
    _shape(output, "index.html", "Alpha", "alpha/")
    return output


# -- the classification itself ------------------------------------------------


def test_an_explicit_404_is_absence(tmp_path):
    remote = _remote()
    text = _run(remote, fetch_remote_text, REPO, "manifests/alpha-files.json",
                missing_ok=True, operation="read alpha's claims")
    assert text == ""


def test_a_rate_limit_is_not_absence():
    remote = _remote(FailingReads, failing={"manifests/alpha-files.json"})
    with pytest.raises(RemoteReadError) as exc:
        _run(remote, fetch_remote_text, REPO, "manifests/alpha-files.json",
             missing_ok=True, operation="read alpha's claims")
    assert "read alpha's claims" in str(exc.value)
    assert "rate limit exceeded" in str(exc.value)


def test_an_unclassifiable_failure_is_not_absence():
    """No HTTP status at all -- a DNS failure, gh missing -- is still failure."""
    remote = _remote(FailingReads, failing={"projects.json"},
                     stderr="dial tcp: lookup api.github.com: no such host")
    with pytest.raises(RemoteReadError) as exc:
        _run(remote, fetch_remote_text, REPO, "projects.json",
             missing_ok=True, operation="read the membership record")
    assert "no such host" in str(exc.value)


def test_a_5xx_is_not_absence():
    remote = _remote(FailingReads, failing={"projects.json"},
                     stderr="gh: Server Error (HTTP 502)")
    with pytest.raises(RemoteReadError):
        _run(remote, fetch_remote_text, REPO, "projects.json",
             missing_ok=True, operation="read the membership record")


def test_a_404_without_missing_ok_is_still_an_error():
    remote = _remote()
    with pytest.raises(RemoteReadError) as exc:
        _run(remote, fetch_remote_text, REPO, "manifests/nope.json",
             operation="read a required file")
    assert "read a required file" in str(exc.value)


# -- the roster loader, which is the model ------------------------------------


def test_a_failed_roster_read_does_not_read_as_a_missing_roster():
    remote = _remote(FailingReads, failing={"roster.toml"})
    with pytest.raises(RemoteReadError) as exc:
        _run(remote, load_remote_roster, REPO)
    assert "rate limit exceeded" in str(exc.value)


# -- docs publish -------------------------------------------------------------


def test_a_failed_claims_read_aborts_the_docs_publish(tmp_path):
    """The defect itself: a transient failure used to erase the claims."""
    remote = _remote(FailingReads, failing={"manifests/alpha-files.json"})
    with pytest.raises(RemoteReadError):
        _run(remote, publish_project_docs, REPO, "alpha", _publishable(tmp_path),
             version="1.0.0")
    assert remote.commits == []
    assert remote.tree_payloads == []
    assert remote.uploaded == []


def test_a_failed_membership_read_aborts_the_docs_publish(tmp_path):
    """A rewritten membership record naming only this project destroys the rest."""
    remote = _remote(FailingReads, failing={"projects.json"})
    with pytest.raises(RemoteReadError):
        _run(remote, publish_project_docs, REPO, "alpha", _publishable(tmp_path),
             version="1.0.0")
    assert remote.commits == []


def test_a_genuine_404_is_still_a_first_publish(tmp_path):
    """Nothing regressed: an assembly holding no record for alpha publishes."""
    remote = _remote()
    summary = _run(remote, publish_project_docs, REPO, "alpha",
                   _publishable(tmp_path), version="1.0.0")
    assert summary["deleted"] == []
    record = json.loads(remote.pushed["manifests/alpha-files.json"])
    assert record["owners"]["docs"] == ["alpha/index.html"]


def test_a_failed_read_leaves_the_existing_claims_untouched(tmp_path):
    """The release owner's claims survive the failed publish."""
    record = json.dumps({
        "schema_version": 2,
        "slug": "alpha",
        "owners": {"release": ["alpha/index.html", "alpha/api/index.html"]},
    })
    remote = _remote(
        FailingReads, failing={"manifests/alpha-files.json"},
        contents={"manifests/alpha-files.json": record},
    )
    with pytest.raises(RemoteReadError):
        _run(remote, publish_project_docs, REPO, "alpha", _publishable(tmp_path),
             version="1.0.0")
    # Nothing was pushed, so what the remote holds is what it held.
    assert remote.tree_payloads == []
    assert json.loads(remote.contents["manifests/alpha-files.json"])["owners"] == {
        "release": ["alpha/index.html", "alpha/api/index.html"],
    }


# -- retire -------------------------------------------------------------------


def test_a_failed_claims_read_aborts_a_retirement():
    """Retiring on a failed read left the project's posts on the blog forever."""
    remote = _remote(
        FailingReads, failing={"manifests/alpha-files.json"},
        blobs={"site/blog/hello/index.html": b"<html>post</html>"},
    )
    with pytest.raises(RemoteReadError):
        _run(remote, retire_project, REPO, "alpha")
    assert remote.commits == []


def test_a_failed_membership_read_aborts_a_retirement():
    remote = _remote(FailingReads, failing={"projects.json"})
    with pytest.raises(RemoteReadError):
        _run(remote, retire_project, REPO, "alpha")
    assert remote.commits == []


def test_a_retirement_with_no_record_at_all_still_works():
    remote = _remote(blobs={"site/alpha/index.html": b"<html>doc</html>"})
    summary = _run(remote, retire_project, REPO, "alpha")
    assert summary["deleted"] == ["site/alpha/index.html"]
    assert summary["remaining"] == ["beta"]


# -- the decoded payload ------------------------------------------------------


def test_a_successful_read_still_decodes(tmp_path):
    remote = _remote(contents={"projects.json": '{"alpha": {}}'})
    text = _run(remote, fetch_remote_text, REPO, "projects.json",
                missing_ok=True, operation="read the membership record")
    assert json.loads(text) == {"alpha": {}}
    assert base64.b64encode(text.encode())  # sanity: it round-trips
