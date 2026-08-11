"""Tests for `selfblog docs publish`, the documentation counterpart of `post publish`.

A documentation fix used to have exactly one route to the live site: tag a
release and dispatch a rebuild.  Posts had a second route -- build locally,
push the built files straight into the assembly repository through the Git
Data API -- and this is that route for documentation, deletions included.

The last test in this file is the one the whole design is for: an edit
published with no tag and no release is still there after the project's next
full deploy.
"""

import json

import pytest

from selfblog.assembly import (
    RosterEntry,
    collect_site_files,
    publish_project_docs,
    render_roster,
)
from tests.test_assembly_push_path import PNG_BYTES, FakeRemote

ROSTER_TEXT = render_roster([
    RosterEntry("alpha", "owner/alpha"),
    RosterEntry("beta", "owner/beta"),
])

REPO = "owner/assembly"


class AssemblyRemote(FakeRemote):
    """A fake assembly repository: the Git Data API plus the Contents API.

    ``docs publish`` reads three files before it writes anything -- the
    roster, the published-file record and the membership record -- and those
    reads go through the Contents API, which the push-path fake knows nothing
    about.
    """

    def __init__(self, blobs=None, contents=None):
        super().__init__(blobs)
        self.contents = dict(contents or {})
        self.dispatches: list[str] = []

    def __call__(self, cmd, **kwargs):
        import base64
        import subprocess

        joined = " ".join(str(c) for c in cmd)
        if "/dispatches" in joined:
            self.dispatches.append(kwargs.get("input") or "")
            return subprocess.CompletedProcess(args=list(cmd), returncode=0,
                                               stdout="", stderr="")
        if "/contents/" in joined:
            path = joined.split("/contents/", 1)[1].split(" ")[0]
            self.calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
            if path not in self.contents:
                return subprocess.CompletedProcess(
                    args=list(cmd), returncode=1, stdout="",
                    stderr="gh: Not Found (HTTP 404)",
                )
            encoded = base64.b64encode(self.contents[path].encode()).decode()
            return subprocess.CompletedProcess(args=list(cmd), returncode=0,
                                               stdout=encoded, stderr="")
        return super().__call__(cmd, **kwargs)

    @property
    def pushed(self):
        """Path -> uploaded bytes for the one commit this fake accepted."""
        import base64
        uploads = [json.loads(c["input"]) for c in self.blob_uploads]
        entries = self.tree_payloads[0]["tree"] if self.tree_payloads else []
        blobs = {
            f"blob{i + 1}": base64.b64decode(u["content"])
            for i, u in enumerate(uploads)
        }
        return {
            e["path"]: blobs.get(e["sha"])
            for e in entries if e["sha"] is not None
        }

    @property
    def deleted(self):
        entries = self.tree_payloads[0]["tree"] if self.tree_payloads else []
        return sorted(e["path"] for e in entries if e["sha"] is None)


def _remote(blobs=None, roster=ROSTER_TEXT, record=None, membership=None):
    contents = {}
    if roster is not None:
        contents["roster.toml"] = roster
    if record is not None:
        contents["manifests/alpha-files.json"] = record
    if membership is not None:
        contents["projects.json"] = membership
    return AssemblyRemote(blobs=blobs, contents=contents)


def _build(tmp_path, pages=("index.html", "guide/index.html")):
    """A local documentation build, as `selfdoc build` leaves it."""
    output = tmp_path / "docs" / "_build"
    for page in pages:
        path = output / page
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"<html>{page}</html>")
    return str(output)


def _publish(remote, *args, **kwargs):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("selfblog.assembly.effects.run", remote)
        return publish_project_docs(*args, **kwargs)


# -- collecting a local build -------------------------------------------------


def test_collect_site_files_addresses_the_projects_subtree(tmp_path):
    files = collect_site_files(_build(tmp_path), "alpha")
    assert sorted(files) == ["site/alpha/guide/index.html", "site/alpha/index.html"]


def test_collect_site_files_reads_content_as_bytes(tmp_path):
    output = _build(tmp_path)
    (tmp_path / "docs" / "_build" / "logo.png").write_bytes(PNG_BYTES)
    files = collect_site_files(output, "alpha")
    assert files["site/alpha/logo.png"] == PNG_BYTES


def test_collect_site_files_applies_the_deploy_artifact_exclusions(tmp_path):
    output = _build(tmp_path)
    (tmp_path / "docs" / "_build" / "_headers").write_text("/*\n")
    (tmp_path / "docs" / "_build" / "_redirects").write_text("/* /x 200\n")
    (tmp_path / "docs" / "_build" / "index.html.gz").write_text("z")
    files = collect_site_files(output, "alpha")
    assert sorted(files) == ["site/alpha/guide/index.html", "site/alpha/index.html"]


# -- the publish --------------------------------------------------------------


def test_a_documentation_page_reaches_the_assembly(tmp_path):
    remote = _remote()
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    assert remote.pushed["site/alpha/index.html"] == b"<html>index.html</html>"


def test_a_binary_asset_survives_the_trip(tmp_path):
    output = _build(tmp_path)
    (tmp_path / "docs" / "_build" / "logo.png").write_bytes(PNG_BYTES)
    remote = _remote()
    _publish(remote, REPO, "alpha", output, version="1.0.0")
    assert remote.pushed["site/alpha/logo.png"] == PNG_BYTES


def test_the_manifest_travels_with_the_pages(tmp_path):
    manifest = tmp_path / ".selfdoc" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"slug": "alpha", "version": "1.0.0"}))
    remote = _remote()
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0",
             manifest_path=str(manifest))
    assert json.loads(remote.pushed["manifests/alpha.json"])["slug"] == "alpha"


def test_the_published_file_record_names_this_publisher(tmp_path):
    remote = _remote()
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    record = json.loads(remote.pushed["manifests/alpha-files.json"])
    assert record["owners"]["docs"] == ["guide/index.html", "index.html"]


def test_the_membership_record_is_refreshed(tmp_path):
    remote = _remote(membership=json.dumps({
        "alpha": {"repo": "owner/alpha", "ref": "v0.9.0", "version": "0.9.0"},
    }))
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    membership = json.loads(remote.pushed["projects.json"])
    assert membership["alpha"]["version"] == "1.0.0"


def test_the_membership_record_keeps_the_last_released_ref(tmp_path):
    """A documentation publish has no tag, so it invents none and drops none."""
    remote = _remote(membership=json.dumps({
        "alpha": {"repo": "owner/alpha", "ref": "v0.9.0", "version": "0.9.0"},
    }))
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    assert json.loads(remote.pushed["projects.json"])["alpha"]["ref"] == "v0.9.0"


def test_a_never_released_project_records_no_ref(tmp_path):
    remote = _remote()
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    assert "ref" not in json.loads(remote.pushed["projects.json"])["alpha"]


def test_other_projects_keep_their_membership_records(tmp_path):
    remote = _remote(membership=json.dumps({
        "beta": {"repo": "owner/beta", "ref": "v2.0.0", "version": "2.0.0"},
    }))
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    membership = json.loads(remote.pushed["projects.json"])
    assert membership["beta"]["version"] == "2.0.0"


def test_everything_travels_in_one_commit(tmp_path):
    remote = _remote()
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    assert len(remote.commit_calls) == 1


def test_an_unchanged_page_uploads_nothing(tmp_path):
    remote = _remote(blobs={"site/alpha/index.html": b"<html>index.html</html>"})
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    assert b"<html>index.html</html>" not in remote.uploaded


# -- deletions ----------------------------------------------------------------


def test_a_page_removed_locally_disappears_remotely(tmp_path):
    """The second publish no longer builds guide/, so guide/ goes."""
    remote = _remote(
        blobs={"site/alpha/guide/index.html": b"<html>guide/index.html</html>"},
        record=json.dumps({
            "schema_version": 1, "slug": "alpha",
            "owners": {"docs": ["index.html", "guide/index.html"]},
        }),
    )
    _publish(remote, REPO, "alpha", _build(tmp_path, pages=("index.html",)),
             version="1.0.0")
    assert remote.deleted == ["site/alpha/guide/index.html"]


def test_a_deletion_drops_out_of_the_published_file_record(tmp_path):
    remote = _remote(record=json.dumps({
        "schema_version": 1, "slug": "alpha",
        "owners": {"docs": ["index.html", "guide/index.html"]},
    }))
    _publish(remote, REPO, "alpha", _build(tmp_path, pages=("index.html",)),
             version="1.0.0")
    record = json.loads(remote.pushed["manifests/alpha-files.json"])
    assert record["owners"]["docs"] == ["index.html"]


def test_a_documentation_publish_never_deletes_a_release_page(tmp_path):
    """It prunes what it published, never what somebody else did."""
    remote = _remote(
        blobs={"site/alpha/reference/index.html": b"released"},
        record=json.dumps({
            "schema_version": 1, "slug": "alpha",
            "owners": {"release": ["reference/index.html"], "docs": []},
        }),
    )
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    assert remote.deleted == []


def test_a_documentation_publish_never_deletes_a_post(tmp_path):
    remote = _remote(
        blobs={"site/alpha/posts/hello/index.html": b"a post"},
        record=json.dumps({
            "schema_version": 1, "slug": "alpha",
            "owners": {"posts": ["posts/hello/index.html"],
                       "docs": ["posts/hello/index.html"]},
        }),
    )
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    assert remote.deleted == []


def test_the_first_publish_deletes_nothing(tmp_path):
    remote = _remote(blobs={"site/alpha/legacy.html": b"who wrote this"})
    _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")
    assert remote.deleted == []


# -- membership is declared, never created ------------------------------------


def test_publishing_into_an_undeclared_slug_is_a_hard_error(tmp_path):
    remote = _remote()
    with pytest.raises(RuntimeError, match="not declared in roster.toml"):
        _publish(remote, REPO, "gamma", _build(tmp_path), version="1.0.0")


def test_the_refusal_names_the_projects_that_are_declared(tmp_path):
    remote = _remote()
    with pytest.raises(RuntimeError, match="alpha, beta"):
        _publish(remote, REPO, "gamma", _build(tmp_path), version="1.0.0")


def test_publishing_without_a_roster_at_all_is_a_hard_error(tmp_path):
    remote = _remote(roster=None)
    with pytest.raises(RuntimeError, match="does not exist"):
        _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")


def test_a_corrupt_published_file_record_is_a_hard_error(tmp_path):
    remote = _remote(record="{not json")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        _publish(remote, REPO, "alpha", _build(tmp_path), version="1.0.0")


# -- the CLI wrapper ----------------------------------------------------------


def _project(tmp_path, monkeypatch):
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "output": "docs/_build/",
        "docs": "docs/",
        "assembly": {"repo": REPO},
        "topology": {"slug": "alpha"},
    }
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "docs").mkdir()
    monkeypatch.chdir(tmp_path)
    return config


def test_the_command_requires_an_assembly_repo(tmp_path, monkeypatch, capsys):
    from selfblog.cli import _cmd_docs_publish

    _project(tmp_path, monkeypatch)
    (tmp_path / "selfdoc.json").write_text(json.dumps({
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "output": "docs/_build/", "docs": "docs/",
        "assembly": {}, "topology": {"slug": "alpha"},
    }))
    with pytest.raises(SystemExit):
        _cmd_docs_publish(None)
    assert "assembly.repo" in capsys.readouterr().err


def test_the_command_requires_a_slug(tmp_path, monkeypatch, capsys):
    from selfblog.cli import _cmd_docs_publish

    _project(tmp_path, monkeypatch)
    (tmp_path / "selfdoc.json").write_text(json.dumps({
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "output": "docs/_build/", "docs": "docs/",
        "assembly": {"repo": REPO}, "topology": {},
    }))
    with pytest.raises(SystemExit):
        _cmd_docs_publish(None)
    assert "topology.slug" in capsys.readouterr().err


def test_the_command_builds_then_publishes_then_dispatches(tmp_path, monkeypatch, capsys):
    from selfblog.cli import _cmd_docs_publish

    _project(tmp_path, monkeypatch)
    remote = _remote()
    built = []

    def fake_build(source_dir, scope):
        built.append((source_dir, scope))
        _build(tmp_path)
        return []

    monkeypatch.setattr("selfblog.assembly.build_source_project", fake_build)
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)
    monkeypatch.setattr("selfblog.cli.effects.run", remote)

    assert _cmd_docs_publish(None) == 0
    assert built == [(".", "full")]
    assert "site/alpha/index.html" in remote.pushed
    payload = json.loads(remote.dispatches[0])
    assert payload["client_payload"]["scope"] == "shared-only"
    assert "Published 2 documentation file(s)" in capsys.readouterr().out


def test_the_command_reports_an_undeclared_slug(tmp_path, monkeypatch, capsys):
    from selfblog.cli import _cmd_docs_publish

    _project(tmp_path, monkeypatch)
    remote = _remote(roster=render_roster([RosterEntry("beta", "owner/beta")]))
    monkeypatch.setattr(
        "selfblog.assembly.build_source_project",
        lambda source_dir, scope: _build(tmp_path),
    )
    monkeypatch.setattr("selfblog.assembly.effects.run", remote)
    monkeypatch.setattr("selfblog.cli.effects.run", remote)

    with pytest.raises(SystemExit):
        _cmd_docs_publish(None)
    assert "not declared in roster.toml" in capsys.readouterr().err


def _declared(group, name):
    """Return a command's registered effects declaration from the CLI schema."""
    from selfblog.cli import app

    return app.dump_schema_dict()["groups"][group]["commands"][name]


def test_the_command_is_consequential():
    """Publishing makes private writing public; that needs consent, as posts do."""
    docs = _declared("docs", "publish")
    post = _declared("post", "publish")
    assert docs["consequential"] is True
    assert docs["effect"] == post["effect"] == "mutating"
    assert docs["grants"] == post["grants"], (
        "the documentation publish takes the same consent as its post equivalent"
    )


# -- the whole point ----------------------------------------------------------


def test_a_documentation_edit_survives_the_projects_next_full_deploy(
    tmp_path, monkeypatch,
):
    """2.1 and 2.2 together: publish with no tag, then release, still there.

    The page below is one the release does not build -- written after the tag
    was cut -- which is exactly the content a wipe destroyed and a prune
    keeps.  The assembly checkout is assembled from what the publish pushed,
    so the integrate sees the real thing rather than a hand-written stand-in.
    """
    import subprocess

    from selfblog.assembly import integrate_project

    # 1. Publish a documentation tree, one page of which the release will not
    #    carry, into a fake assembly repository.
    output = _build(tmp_path, pages=("index.html", "hotfix/index.html"))
    remote = _remote()
    _publish(remote, REPO, "alpha", output, version="1.0.0")

    # 2. Lay the pushed commit out as an assembly checkout.
    assembly = tmp_path / "assembly"
    for path, content in remote.pushed.items():
        target = assembly / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (assembly / "roster.toml").write_text(ROSTER_TEXT)
    manifests = assembly / "manifests"
    manifests.mkdir(exist_ok=True)
    (manifests / "alpha.json").write_text(json.dumps({
        "schema_version": 1, "name": "Alpha", "slug": "alpha",
        "version": "1.0.0", "description": "Alpha docs", "language": "python",
        "base_url": "https://docs.example.com/alpha",
        "pages": [{"path": "index.md", "title": "Home"}], "posts": [],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }))

    # 3. The project releases: a full build that knows nothing about hotfix/.
    source = assembly / "source" / "alpha"
    release_build = source / "docs" / "_build"
    (release_build).mkdir(parents=True)
    (release_build / "index.html").write_text("<html>released</html>")
    (source / ".selfdoc").mkdir()
    (source / ".selfdoc" / "manifest.json").write_text(
        (manifests / "alpha.json").read_text())

    def quiet(argv, **kwargs):
        return subprocess.CompletedProcess(
            args=[str(a) for a in argv], returncode=0,
            stdout="" if kwargs.get("capture_output") else None,
            stderr="" if kwargs.get("capture_output") else None,
        )

    monkeypatch.setattr("selfblog.assembly.effects.run", quiet)
    integrate_project(
        slug="alpha", version="1.1.0", ref="v1.1.0", source_repo="owner/alpha",
        scope="full", canonical_base="https://docs.example.com",
        assembly_dir=str(assembly), retry_delay=0, build=False,
    )

    survivor = assembly / "site" / "alpha" / "hotfix" / "index.html"
    assert survivor.exists(), "the release destroyed a page it never built"
    assert survivor.read_text() == "<html>hotfix/index.html</html>"
    with open(assembly / "site" / "alpha" / "index.html") as f:
        assert "released" in f.read(), "the release still supersedes its own pages"
