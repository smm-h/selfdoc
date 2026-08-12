"""The remote publishers refuse to overwrite another project's post.

The site-level blog is one namespace: a post is emitted at
``blog/<post-slug>/`` with no project segment, so two projects that pick the
same post slug address the same file.  The integrate graft has always refused
that -- it reads the published-file records in the assembly clone and stops
before copying anything over another project's claim.

The publishers that write through the Git Data API never ran that check.
``docs publish`` and ``post publish`` both push post-addressed files straight
onto the branch the site serves, so either could silently replace a post
another project published, and the record each one then wrote made the theft
look legitimate.  Both now read the other declared projects' records off the
assembly and refuse, naming both projects.
"""

import json
import subprocess

import pytest

from selfblog.assembly import (
    RosterEntry,
    publish_project_docs,
    remote_post_claims,
    render_roster,
)
from tests.test_docs_publish import AssemblyRemote, _shape

REPO = "owner/assembly"

ROSTER_TEXT = render_roster([
    RosterEntry("alpha", "owner/alpha"),
    RosterEntry("beta", "owner/beta"),
])


def _record(slug, owner, paths):
    return json.dumps({
        "schema_version": 2,
        "slug": slug,
        "owners": {owner: sorted(paths)},
    })


def _remote(contents=None, blobs=None):
    base = {"roster.toml": ROSTER_TEXT}
    base.update(contents or {})
    return AssemblyRemote(blobs=blobs, contents=base)


def _run(remote, fn, *args, **kwargs):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("selfblog.assembly.effects.run", remote)
        return fn(*args, **kwargs)


# -- reading the claims off the assembly --------------------------------------


def test_remote_post_claims_names_the_claimant():
    remote = _remote({
        "manifests/beta-files.json": _record(
            "beta", "posts", ["blog/hello/index.html"]),
    })
    claims = _run(remote, remote_post_claims, REPO, "alpha", ["alpha", "beta"])
    assert claims == {"blog/hello/index.html": "beta"}


def test_remote_post_claims_ignores_the_publishing_project():
    remote = _remote({
        "manifests/alpha-files.json": _record(
            "alpha", "posts", ["blog/hello/index.html"]),
    })
    claims = _run(remote, remote_post_claims, REPO, "alpha", ["alpha", "beta"])
    assert claims == {}


def test_remote_post_claims_ignores_documentation_paths():
    """Only site-level posts share a namespace; a subtree page cannot collide."""
    remote = _remote({
        "manifests/beta-files.json": _record(
            "beta", "release", ["beta/index.html", "beta/guide/index.html"]),
    })
    claims = _run(remote, remote_post_claims, REPO, "alpha", ["alpha", "beta"])
    assert claims == {}


def test_a_project_with_no_record_yet_claims_nothing():
    claims = _run(_remote(), remote_post_claims, REPO, "alpha", ["alpha", "beta"])
    assert claims == {}


# -- docs publish -------------------------------------------------------------


def _docs_build_with_post(tmp_path, post_slug="hello"):
    """A full documentation build that also carries a post."""
    output = tmp_path / "docs" / "_build"
    (output / "blog" / post_slug).mkdir(parents=True)
    (output / "index.html").write_text("<html>alpha</html>")
    (output / "blog" / post_slug / "index.html").write_text("<html>post</html>")
    _shape(str(output), "index.html", "Alpha", "alpha/")
    _shape(str(output), f"blog/{post_slug}/index.html", "Hello",
           f"blog/{post_slug}/")
    return str(output)


def test_docs_publish_refuses_to_overwrite_a_foreign_post(tmp_path):
    remote = _remote({
        "manifests/beta-files.json": _record(
            "beta", "posts", ["blog/hello/index.html"]),
    })
    with pytest.raises(RuntimeError) as exc:
        _run(remote, publish_project_docs, REPO, "alpha",
             _docs_build_with_post(tmp_path), version="1.0.0")
    message = str(exc.value)
    assert "'alpha'" in message
    assert "'beta'" in message
    assert "site/blog/hello/index.html" in message


def test_docs_publish_writes_nothing_when_it_refuses(tmp_path):
    remote = _remote({
        "manifests/beta-files.json": _record(
            "beta", "posts", ["blog/hello/index.html"]),
    })
    with pytest.raises(RuntimeError):
        _run(remote, publish_project_docs, REPO, "alpha",
             _docs_build_with_post(tmp_path), version="1.0.0")
    assert remote.commits == []
    assert remote.uploaded == []


def test_docs_publish_allows_a_post_slug_nobody_claims(tmp_path):
    remote = _remote({
        "manifests/beta-files.json": _record(
            "beta", "posts", ["blog/other/index.html"]),
    })
    summary = _run(remote, publish_project_docs, REPO, "alpha",
                   _docs_build_with_post(tmp_path), version="1.0.0")
    assert "blog/hello/index.html" in summary["published"]


def test_docs_publish_may_republish_its_own_post(tmp_path):
    """The project's own claim is not a collision with itself."""
    remote = _remote({
        "manifests/alpha-files.json": _record(
            "alpha", "posts", ["blog/hello/index.html"]),
    })
    summary = _run(remote, publish_project_docs, REPO, "alpha",
                   _docs_build_with_post(tmp_path), version="1.0.0")
    assert "blog/hello/index.html" in summary["published"]


# -- post publish -------------------------------------------------------------


def _post_project(tmp_path, slug="alpha", post_slug="hello"):
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "output": "docs/_build/",
        "docs": "docs/",
        "assembly": {"repo": REPO},
        "topology": {"slug": slug},
    }
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "docs").mkdir(exist_ok=True)
    posts_dir = tmp_path / ".selfdoc" / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    (posts_dir / f"2026-06-01-{post_slug}.md").write_text(
        "---\ntitle: Hello World\ndate: 2026-06-01\n"
        f"slug: {post_slug}\ndraft: false\ndirectives: false\n"
        "tags: []\n---\n\nHello world content.\n"
    )
    output = tmp_path / "docs" / "_build"
    (output / "blog" / post_slug).mkdir(parents=True)
    (output / "blog" / post_slug / "index.html").write_text("<html>post</html>")
    (output / "blog" / "index.html").write_text("<html>listing</html>")
    return {
        str(output / "blog" / post_slug / "index.html"): True,
        str(output / "blog" / "index.html"): True,
    }


def _post_publish(tmp_path, monkeypatch, remote):
    from selfblog.cli import _cmd_post_publish

    written = _post_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("selfdoc_core.build._build_posts_only",
                        lambda *a, **kw: written)
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)
    monkeypatch.setattr("selfblog.cli.effects.run", remote)
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    return _cmd_post_publish(None)


def test_post_publish_refuses_to_overwrite_a_foreign_post(
        tmp_path, monkeypatch, capsys):
    remote = _remote({
        "manifests/beta-files.json": _record(
            "beta", "posts", ["blog/hello/index.html"]),
    })
    with pytest.raises(SystemExit) as exc:
        _post_publish(tmp_path, monkeypatch, remote)
    assert exc.value.code == 1
    message = capsys.readouterr().err
    assert "'alpha'" in message
    assert "'beta'" in message
    assert "site/blog/hello/index.html" in message


def test_post_publish_writes_nothing_when_it_refuses(tmp_path, monkeypatch):
    remote = _remote({
        "manifests/beta-files.json": _record(
            "beta", "posts", ["blog/hello/index.html"]),
    })
    with pytest.raises(SystemExit):
        _post_publish(tmp_path, monkeypatch, remote)
    assert remote.commits == []
    assert remote.uploaded == []
    assert remote.dispatches == []


def test_post_publish_allows_a_post_slug_nobody_claims(tmp_path, monkeypatch):
    remote = _remote({
        "manifests/beta-files.json": _record(
            "beta", "posts", ["blog/other/index.html"]),
    })
    assert _post_publish(tmp_path, monkeypatch, remote) == 0
    assert remote.commits


def test_post_publish_may_republish_its_own_post(tmp_path, monkeypatch):
    remote = _remote({
        "manifests/alpha-files.json": _record(
            "alpha", "posts", ["blog/hello/index.html"]),
    })
    assert _post_publish(tmp_path, monkeypatch, remote) == 0
    assert remote.commits
