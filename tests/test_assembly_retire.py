"""Tests for `selfblog assembly retire`, the one command that unpublishes.

Nothing in the assembly tooling could remove a project.  The Git Data API
push path could not delete, ``projects.json`` only ever gained keys, and a
retired project's section stayed at its URL, in the listing, in the feed, in
the sitemap and in the search index -- correctable only by hand-editing the
assembly repository.

Retirement is one operation now: the ``[[project]]`` block leaves the roster
and, in the same commit, every path the project owns is deleted; the
shared-only dispatch that follows regenerates the shared elements and the
index without it.
"""

import json

import pytest

from selfblog.assembly import (
    RosterEntry,
    generate_shared_files,
    parse_roster,
    project_paths,
    render_roster,
    retire_project,
)
from tests.test_docs_publish import AssemblyRemote

REPO = "owner/assembly"

ROSTER_TEXT = render_roster([
    RosterEntry("keeper", "owner/keeper"),
    RosterEntry("goner", "owner/goner"),
])

MEMBERSHIP = json.dumps({
    "keeper": {"repo": "owner/keeper", "ref": "v1.0.0", "version": "1.0.0"},
    "goner": {"repo": "owner/goner", "ref": "v0.4.0", "version": "0.4.0"},
}, indent=2) + "\n"


def _manifest(slug, name):
    return json.dumps({
        "schema_version": 1, "name": name, "slug": slug, "version": "1.0.0",
        "description": f"{name} docs", "language": "python",
        "base_url": f"https://docs.example.com/{slug}",
        "pages": [{"path": "index.md", "title": "Home"}],
        "posts": [{"slug": "hello", "title": f"{name} says hello",
                   "date": "2024-06-01"}],
        "last_gen": "2024-01-01T00:00:00+00:00",
    })


BLOBS = {
    "roster.toml": ROSTER_TEXT.encode(),
    "projects.json": MEMBERSHIP.encode(),
    "site/keeper/index.html": b"<html>keeper</html>",
    "site/goner/index.html": b"<html>goner</html>",
    "site/goner/guide/index.html": b"<html>goner guide</html>",
    "site/goner/posts/hello/index.html": b"<html>goner post</html>",
    "manifests/keeper.json": _manifest("keeper", "Keeper").encode(),
    "manifests/goner.json": _manifest("goner", "Goner").encode(),
    "manifests/goner-posts.json": _manifest("goner", "Goner").encode(),
    "manifests/goner-revisions.json": b"{}",
    "manifests/goner-files.json": b'{"schema_version": 1, "slug": "goner", "owners": {}}',
}


def _remote(**overrides):
    contents = {
        "roster.toml": ROSTER_TEXT,
        "projects.json": MEMBERSHIP,
    }
    contents.update(overrides.pop("contents", {}))
    blobs = dict(BLOBS)
    blobs.update(overrides.pop("blobs", {}))
    return AssemblyRemote(blobs=blobs, contents=contents)


def _retire(remote, slug="goner"):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("selfblog.assembly.effects.run", remote)
        return retire_project(REPO, slug)


# -- what a project owns ------------------------------------------------------


def test_a_project_owns_its_whole_subtree():
    owned = project_paths(list(BLOBS), "goner")
    assert "site/goner/index.html" in owned
    assert "site/goner/guide/index.html" in owned


def test_a_project_owns_every_manifest_kind():
    owned = project_paths(list(BLOBS), "goner")
    assert {p for p in owned if p.startswith("manifests/")} == {
        "manifests/goner.json", "manifests/goner-posts.json",
        "manifests/goner-revisions.json", "manifests/goner-files.json",
    }


def test_a_project_owns_nothing_of_another_projects():
    owned = project_paths(list(BLOBS), "goner")
    assert not [p for p in owned if "keeper" in p]


def test_a_slug_that_is_a_prefix_of_another_takes_only_its_own():
    paths = ["site/doc/index.html", "site/docs-site/index.html",
             "manifests/doc.json", "manifests/docs-site.json"]
    assert project_paths(paths, "doc") == ["manifests/doc.json", "site/doc/index.html"]


# -- the retirement -----------------------------------------------------------


def test_retirement_deletes_the_projects_section(tmp_path):
    remote = _remote()
    _retire(remote)
    assert "site/goner/index.html" in remote.deleted
    assert "site/goner/guide/index.html" in remote.deleted


def test_retirement_deletes_every_manifest_kind():
    remote = _remote()
    _retire(remote)
    assert {p for p in remote.deleted if p.startswith("manifests/")} == {
        "manifests/goner.json", "manifests/goner-posts.json",
        "manifests/goner-revisions.json", "manifests/goner-files.json",
    }


def test_retirement_leaves_the_other_project_alone():
    remote = _remote()
    _retire(remote)
    assert not [p for p in remote.deleted if "keeper" in p]


def test_retirement_removes_the_roster_block():
    remote = _remote()
    _retire(remote)
    assert list(parse_roster(remote.pushed["roster.toml"].decode())) == ["keeper"]


def test_retirement_removes_the_membership_record():
    remote = _remote()
    _retire(remote)
    assert list(json.loads(remote.pushed["projects.json"])) == ["keeper"]


def test_the_whole_retirement_is_one_commit():
    remote = _remote()
    _retire(remote)
    assert len(remote.commit_calls) == 1


def test_retirement_reports_what_remains():
    remote = _remote()
    summary = _retire(remote)
    assert summary["remaining"] == ["keeper"]
    assert summary["push"].changed is True


def test_retiring_an_undeclared_project_is_a_hard_error():
    remote = _remote()
    with pytest.raises(RuntimeError, match="nothing to retire"):
        _retire(remote, "never-existed")


def test_the_refusal_names_the_projects_that_are_declared():
    remote = _remote()
    with pytest.raises(RuntimeError, match="goner, keeper"):
        _retire(remote, "never-existed")


def test_retiring_without_a_roster_is_a_hard_error():
    remote = AssemblyRemote(blobs=dict(BLOBS), contents={})
    with pytest.raises(RuntimeError, match="does not exist"):
        _retire(remote)


# -- the listing rows ---------------------------------------------------------


def test_the_retired_project_loses_its_listing_rows(tmp_path):
    """What the shared-only dispatch regenerates after the deletion commit.

    The manifests below are what survives the retirement commit, so this is
    the real remaining input rather than a hand-picked subset.
    """
    remote = _remote()
    _retire(remote)
    gone = set(remote.deleted)

    manifests = tmp_path / "manifests"
    manifests.mkdir()
    for path, content in BLOBS.items():
        if path.startswith("manifests/") and path not in gone:
            (manifests / path.split("/", 1)[1]).write_bytes(content)

    site = tmp_path / "site"
    site.mkdir()
    generate_shared_files(str(site), str(manifests), "https://docs.example.com",
                          docs_base="https://docs.example.com")

    listing = (site / "index.html").read_text()
    blog = (site / "blog" / "index.html").read_text()
    nav = json.loads((site / "nav.json").read_text())
    feed = (site / "feed.xml").read_text()
    sitemap = (site / "sitemap.xml").read_text()

    assert "Keeper" in listing and "Goner" not in listing
    assert "Goner says hello" not in blog
    assert [p["slug"] for p in nav["projects"]] == ["keeper"]
    assert "goner" not in feed
    assert "goner" not in sitemap


# -- the CLI wrapper ----------------------------------------------------------


def _project(tmp_path, monkeypatch):
    (tmp_path / "selfdoc.json").write_text(json.dumps({
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "output": "docs/_build/", "docs": "docs/",
        "assembly": {"repo": REPO}, "topology": {"slug": "keeper"},
    }))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "docs").mkdir()
    monkeypatch.chdir(tmp_path)


def test_the_command_requires_a_slug(tmp_path, monkeypatch, capsys):
    from selfblog.cli import _cmd_assembly_retire

    _project(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        _cmd_assembly_retire(None, slug="")
    assert "--slug is required" in capsys.readouterr().err


def test_the_command_retires_and_dispatches(tmp_path, monkeypatch, capsys):
    from selfblog.cli import _cmd_assembly_retire

    _project(tmp_path, monkeypatch)
    remote = _remote()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)
    monkeypatch.setattr("selfblog.cli.effects.run", remote)

    assert _cmd_assembly_retire(None, slug="goner") == 0
    assert "site/goner/index.html" in remote.deleted
    payload = json.loads(remote.dispatches[0])
    assert payload["client_payload"]["scope"] == "shared-only"
    out = capsys.readouterr().out
    assert "Retired goner" in out
    assert "Remaining projects: keeper" in out


def test_the_command_reports_an_unknown_slug(tmp_path, monkeypatch, capsys):
    from selfblog.cli import _cmd_assembly_retire

    _project(tmp_path, monkeypatch)
    remote = _remote()
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)
    monkeypatch.setattr("selfblog.cli.effects.run", remote)

    with pytest.raises(SystemExit):
        _cmd_assembly_retire(None, slug="never-existed")
    assert "nothing to retire" in capsys.readouterr().err


def test_the_command_is_consequential():
    """It deletes published content; nothing else in either CLI does."""
    from selfblog.cli import app

    command = app.dump_schema_dict()["groups"]["assembly"]["commands"]["retire"]
    assert command["consequential"] is True
    assert command["effect"] == "mutating"
    assert sorted(g["name"] for g in command["grants"]) == [
        "assembly-commit", "assembly-dispatch",
    ]
