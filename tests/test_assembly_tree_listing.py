"""The remote tree listing has to be a GET.

`_remote_blob_shas` asks the Trees API which blobs the assembly already has,
so a push can skip the files whose content did not change. It passed the
recursive flag as ``-f recursive=1``, and ``gh api -f`` attaches a request
BODY -- which makes gh issue a POST. ``POST /repos/{repo}/git/trees/{sha}``
is not a route, so GitHub answered 404 and every caller reported the
assembly as missing:

    Error: list tree: gh: Not Found (HTTP 404)

That took out `assembly sync-workflow` and the push path's unchanged-file
detection. The flag has to travel as a query parameter with the method
pinned to GET.
"""

import subprocess

import pytest

from selfblog.assembly import _remote_blob_shas


TREE = (
    '{"sha": "deadbeef", "truncated": false, "tree": ['
    '{"path": "site/index.html", "type": "blob", "sha": "aaa"},'
    '{"path": "site", "type": "tree", "sha": "bbb"}]}'
)


@pytest.fixture()
def recorded_gh(monkeypatch):
    """Capture the argv `_remote_blob_shas` hands to gh, and answer it."""
    seen = []

    def run(cmd, **kwargs):
        seen.append([str(c) for c in cmd])
        return subprocess.CompletedProcess(
            args=list(cmd), returncode=0, stdout=TREE, stderr="",
        )

    monkeypatch.setattr("selfblog.assembly.effects.run", run)
    return seen


def test_the_tree_listing_pins_the_method_to_get(recorded_gh):
    """Without an explicit GET, the recursive flag turns the call into a POST."""
    _remote_blob_shas("owner/assembly", "deadbeef")

    argv = recorded_gh[0]
    assert "--method" in argv or "-X" in argv, (
        "the Trees API call carries a parameter, so gh sends it as a POST "
        "body unless the method is pinned; POST is not a route on this "
        "endpoint and GitHub answers 404. argv was: " + " ".join(argv)
    )
    flag = "--method" if "--method" in argv else "-X"
    assert argv[argv.index(flag) + 1] == "GET"


def test_the_tree_listing_asks_for_the_whole_tree(recorded_gh):
    """A non-recursive listing returns only the top level, silently."""
    _remote_blob_shas("owner/assembly", "deadbeef")

    assert any("recursive=1" in arg for arg in recorded_gh[0])


def test_the_tree_listing_returns_blobs_only(recorded_gh):
    assert _remote_blob_shas("owner/assembly", "deadbeef") == {
        "site/index.html": "aaa",
    }
