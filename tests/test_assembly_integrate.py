"""Tests for `selfblog assembly integrate` against a realistic assembly tree.

Everything this command does used to live as embedded shell and inline
interpreter snippets inside the generated deploy workflow, where the only way
to exercise it was to dispatch a real deploy and watch the live site.  The
fixture below is the shape the workflow actually works on: an assembly
checkout holding two project subtrees under ``site/``, their manifests, a
``projects.json`` membership file, and a freshly cloned source project whose
build output is waiting to be grafted in.
"""

import json
import os
import subprocess

import pytest

from selfblog.assembly import (
    RosterEntry,
    apply_project_files,
    detect_latest_version,
    integrate_project,
    load_files_manifest,
    prune_deploy_artifacts,
    record_membership,
    render_roster,
)

CANONICAL_BASE = "https://docs.example.com"

ROSTER = {
    # Every assembly declares exactly one home project: the one served at
    # the site root. It is an ordinary declared project in every other way.
    "home": RosterEntry("home", "owner/home"),
    "alpha": RosterEntry("alpha", "owner/alpha"),
    "beta": RosterEntry("beta", "owner/beta"),
}
HOME = "home"


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _page(title, address, marker="", version=""):
    """A page shaped the way a real build's pages are shaped.

    The deploy verifies the tree it assembled before it pushes any of it,
    and a page with no title or no canonical fails that verification -- so
    a fixture standing in for a built page carries both, exactly as the
    build's own output does.  *address* is the site-relative address the
    page is emitted at (``alpha/guide/``), and *marker* is the body text a
    test looks for to tell one build's output from another's.
    """
    version_attr = f' data-default-version="{version}"' if version else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        f"  <title>{title}</title>\n"
        f'  <link rel="canonical" href="{CANONICAL_BASE}/{address}">\n'
        "</head>\n"
        "<body>\n"
        f'  <dialog class="search-dialog" data-search-base="./"{version_attr}></dialog>\n'
        f"  <p>{marker or title}</p>\n"
        "</body>\n"
        "</html>\n"
    )


def _manifest(slug, name, version, posts=None):
    return {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "version": version,
        "description": f"{name} docs",
        "language": "python",
        "base_url": f"{CANONICAL_BASE}/{slug}",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "pages": [{"path": "index.md", "title": "Home"}],
        "posts": posts or [],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }


@pytest.fixture()
def assembly_tree(tmp_path):
    """A realistic assembly checkout plus a cloned, already-built source."""
    root = tmp_path / "assembly"

    # Two project subtrees already deployed.
    _write(str(root / "site" / "alpha" / "index.html"),
           _page("Alpha", "alpha/", marker="old alpha"))
    _write(str(root / "site" / "alpha" / "guide" / "index.html"),
           _page("Alpha Guide", "alpha/guide/", marker="old guide"))
    _write(str(root / "site" / "alpha" / "retired" / "index.html"),
           _page("Retired", "alpha/retired/", marker="gone upstream"))
    # A post published between releases, at the site-level address every
    # post has: nobody's build produced it, so no publisher is entitled to
    # prune it and it outlives a full build.
    _write(str(root / "site" / "blog" / "old-post" / "index.html"),
           _page("Old", "blog/old-post/", marker="old post"))
    _write(str(root / "site" / "beta" / "index.html"),
           _page("Beta", "beta/", marker="beta", version="2.0.0"))
    # The home project's front page, at the site root under no slug.
    _write(str(root / "site" / "index.html"),
           _page("Front page", "", marker="home"))

    # Manifests, including a stale posts overlay for alpha.
    _write(str(root / "manifests" / "alpha.json"),
           json.dumps(_manifest("alpha", "Alpha", "0.9.0")))
    _write(str(root / "manifests" / "alpha-posts.json"),
           json.dumps(_manifest("alpha", "Alpha", "0.9.0",
                                posts=[{"slug": "old-post", "title": "Old",
                                        "date": "2024-01-01"}])))
    _write(str(root / "manifests" / "beta.json"),
           json.dumps(_manifest("beta", "Beta", "2.0.0")))
    _write(str(root / "manifests" / "home.json"),
           json.dumps(_manifest("home", "Home", "0.1.0")))
    _write(str(root / "manifests" / "home-files.json"), json.dumps({
        "schema_version": 2, "slug": "home",
        "owners": {"release": ["index.html"]},
    }))
    # A declared home carries its curated listing: its deploy copies it in
    # beside the manifests, and shared generation refuses without it.
    # Curation is selection, so listing only alpha is legal -- and it keeps
    # the fixture usable by the tests that retire beta.
    _write(str(root / "manifests" / "home-listing.json"), json.dumps({
        "format_version": 1, "slug": "home",
        "categories": [{
            "name": "Projects",
            "projects": [{"slug": "alpha", "blurb": "Does the alpha thing.",
                          "url": "", "name": ""}],
        }],
    }))

    # Membership file with both projects, and the roster that declares them.
    _write(str(root / "projects.json"), json.dumps({
        "home": {"repo": "owner/home", "ref": "v0.1.0", "version": "0.1.0"},
        "alpha": {"repo": "owner/alpha", "ref": "v0.9.0", "version": "0.9.0"},
        "beta": {"repo": "owner/beta", "ref": "v2.0.0", "version": "2.0.0"},
    }, indent=2) + "\n")
    _write(str(root / "roster.toml"), render_roster(ROSTER.values(), home=HOME))

    # What the last release published for alpha, which is what a prune is
    # entitled to remove. Every path is site-relative, and the out-of-band
    # post is deliberately absent.
    _write(str(root / "manifests" / "alpha-files.json"), json.dumps({
        "schema_version": 2,
        "slug": "alpha",
        "owners": {"release": [
            "alpha/index.html", "alpha/guide/index.html",
            "alpha/retired/index.html",
        ]},
    }))

    # The cloned source project, as the workflow's second checkout leaves it,
    # with a build output tree as `selfdoc build` would have produced.
    source = root / "source" / "alpha"
    _write(str(source / "selfdoc.json"), json.dumps({
        "versions": [{"version": "0.9.0"}, {"version": "1.0.0"}],
    }))
    build = source / "docs" / "_build"
    _write(str(build / "index.html"),
           _page("Alpha", "alpha/", marker="new alpha", version="1.0.0"))
    _write(str(build / "guide" / "index.html"),
           _page("Alpha Guide", "alpha/guide/", marker="new guide",
                 version="1.0.0"))
    # The listing page the build renders for the project's own standalone
    # site. It is not grafted: the assembled site's blog index is written by
    # generate_shared_files and lists every project's posts.
    _write(str(build / "blog" / "index.html"),
           _page("Alpha Posts", "blog/", marker="standalone listing",
                 version="1.0.0"))
    _write(str(build / "blog" / "hello" / "index.html"),
           _page("Hello", "blog/hello/", marker="hello", version="1.0.0"))
    # Per-project deploy artifacts the assembly must not inherit.
    _write(str(build / "_headers"), "/*\\n  X-Frame-Options: DENY\\n")
    _write(str(build / "_redirects"), "/* /index.html 200\\n")
    _write(str(build / "_worker.js"), "export default {}\\n")
    _write(str(build / "index.html.gz"), "gzipped")
    _write(str(build / "guide" / "index.html.br"), "brotli")
    # A full build's manifest carries the posts the build rendered.
    _write(str(source / ".selfdoc" / "manifest.json"),
           json.dumps(_manifest("alpha", "Alpha", "1.0.0",
                                posts=[{"slug": "hello", "title": "Hello",
                                        "date": "2024-06-01"}])))
    _write(str(source / ".selfdoc" / "post-manifest.json"),
           json.dumps(_manifest("alpha", "Alpha", "1.0.0",
                                posts=[{"slug": "hello", "title": "Hello",
                                        "date": "2024-06-01"}])))
    return root


class RunRecorder:
    """Stands in for every subprocess the integrate run shells out to."""

    def __init__(self, push_failures=0):
        self.calls: list[list[str]] = []
        self.push_failures = push_failures
        self.pushes = 0

    def __call__(self, argv, *, cwd=None, env=None, timeout=None, check=False,
                 capture_output=False, text=False, input=None, read=False,
                 resource=None, skip_if_current=None, grant=None):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        if "pagefind" in argv and "--site" in argv:
            # What a real pagefind pass leaves: the runtime, the entry the
            # runtime fetches to find its index, and a fragment per indexed
            # page. Verification asserts the last two, so a stub that wrote
            # only the runtime would stand in for an index that answers
            # nothing.
            site = argv[argv.index("--site") + 1]
            _write(os.path.join(site, "pagefind", "pagefind.js"), "// index")
            # The UI bundle every page loads, which the indexer emits
            # alongside the index itself.
            _write(os.path.join(site, "pagefind", "pagefind-ui.js"), "// ui")
            _write(os.path.join(site, "pagefind", "pagefind-ui.css"), "/* ui */")
            _write(os.path.join(site, "pagefind", "pagefind-entry.json"),
                   json.dumps({
                       "version": "1.3.0",
                       "languages": {"en": {"hash": "en_abc", "wasm": "en",
                                            "page_count": 3}},
                   }))
            _write(os.path.join(site, "pagefind", "fragment",
                                "en_abc.pf_fragment"), "fragment")
        returncode = 0
        if argv[:2] == ["git", "push"]:
            self.pushes += 1
            if self.pushes <= self.push_failures:
                returncode = 1
        return subprocess.CompletedProcess(
            args=argv, returncode=returncode,
            stdout="" if capture_output else None,
            stderr="rejected" if (capture_output and returncode) else ("" if capture_output else None),
        )

    def of(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == list(prefix)]


@pytest.fixture()
def runner(monkeypatch):
    recorder = RunRecorder()
    monkeypatch.setattr("selfblog.assembly.effects.run", recorder)
    return recorder


def _integrate(root, runner=None, **overrides):
    kwargs = dict(
        slug="alpha",
        version="1.0.0",
        ref="v1.0.0",
        source_repo="owner/alpha",
        scope="full",
        canonical_base=CANONICAL_BASE,
        assembly_dir=str(root),
        retry_delay=0,
    )
    kwargs.update(overrides)
    return integrate_project(**kwargs)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -- unit pieces --------------------------------------------------------------


def test_detect_latest_version_reads_the_last_declared_version(assembly_tree):
    assert detect_latest_version(str(assembly_tree / "source" / "alpha")) == "1.0.0"


def test_detect_latest_version_is_empty_without_a_config(tmp_path):
    assert detect_latest_version(str(tmp_path)) == ""


def test_detect_latest_version_errors_on_a_versionless_multi_version_project(tmp_path):
    _write(str(tmp_path / "selfdoc.json"), json.dumps({"versions": [{}, {}]}))
    with pytest.raises(RuntimeError, match="newest 'versions' entry"):
        detect_latest_version(str(tmp_path))


def test_detect_latest_version_errors_on_a_single_versionless_entry(tmp_path):
    """One blank entry is the same failure as two, and errors identically.

    Returning "" here built the project unversioned -- silently publishing
    docs at the wrong address -- while two blank entries hard-errored.
    """
    _write(str(tmp_path / "selfdoc.json"), json.dumps({"versions": [{}]}))
    with pytest.raises(RuntimeError, match="newest 'versions' entry"):
        detect_latest_version(str(tmp_path))


def test_a_blank_newest_entry_errors_however_many_precede_it(tmp_path):
    _write(str(tmp_path / "selfdoc.json"),
           json.dumps({"versions": [{"version": "1.0.0"}, {}]}))
    with pytest.raises(RuntimeError, match="newest 'versions' entry"):
        detect_latest_version(str(tmp_path))


def test_no_versions_array_at_all_is_still_the_implicit_single_version(tmp_path):
    """A project that declares nothing builds unversioned, as before."""
    _write(str(tmp_path / "selfdoc.json"), json.dumps({}))
    assert detect_latest_version(str(tmp_path)) == ""


def test_prune_removes_every_deploy_artifact(assembly_tree):
    build = str(assembly_tree / "source" / "alpha" / "docs" / "_build")
    removed = prune_deploy_artifacts(build)
    names = {os.path.basename(p) for p in removed}
    assert names == {"_headers", "_redirects", "_worker.js",
                     "index.html.gz", "index.html.br"}
    assert not os.path.exists(os.path.join(build, "_worker.js"))
    assert os.path.exists(os.path.join(build, "index.html"))


def test_record_membership_keeps_other_members(assembly_tree):
    path = str(assembly_tree / "projects.json")
    data = record_membership(path, ROSTER, "alpha", "owner/alpha", "v1.0.0", "1.0.0")
    assert data["alpha"] == {"repo": "owner/alpha", "ref": "v1.0.0", "version": "1.0.0"}
    assert data["beta"]["version"] == "2.0.0"
    assert _read_json(path)["alpha"]["ref"] == "v1.0.0"


def test_record_membership_creates_the_file_when_absent(tmp_path):
    path = str(tmp_path / "projects.json")
    record_membership(path, ROSTER, "alpha", "owner/alpha", "v1", "1")
    assert list(_read_json(path)) == ["alpha"]


def test_record_membership_refuses_to_rewrite_a_corrupt_file(tmp_path):
    path = str(tmp_path / "projects.json")
    _write(path, "{not json")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        record_membership(path, ROSTER, "alpha", "owner/alpha", "v1", "1")


def test_record_membership_refuses_an_undeclared_slug(tmp_path):
    """A deploy cannot add a project; membership only comes from the roster."""
    path = str(tmp_path / "projects.json")
    with pytest.raises(RuntimeError, match="not declared in roster.toml"):
        record_membership(path, ROSTER, "gamma", "owner/gamma", "v1", "1")


def test_record_membership_refuses_a_slug_claimed_by_another_repo(tmp_path):
    path = str(tmp_path / "projects.json")
    with pytest.raises(RuntimeError, match="one slug has one owning repository|declares 'alpha'"):
        record_membership(path, ROSTER, "alpha", "someone/else", "v1", "1")


def test_apply_project_files_full_scope(assembly_tree):
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    site = assembly_tree / "site" / "alpha"
    assert not (site / "retired").exists()
    assert (assembly_tree / "site" / "blog" / "hello" / "index.html").exists()
    assert not (site / "_headers").exists()
    assert not (site / "index.html.gz").exists()
    assert _read_json(str(assembly_tree / "manifests" / "alpha.json"))["version"] == "1.0.0"


def test_a_grafted_post_lands_at_the_site_level_and_nowhere_else(assembly_tree):
    """The whole contract: `blog/<post-slug>/`, never under a project slug."""
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    assert (assembly_tree / "site" / "blog" / "hello" / "index.html").exists()
    assert not (assembly_tree / "site" / "alpha" / "blog").exists()
    assert not (assembly_tree / "site" / "alpha" / "posts").exists()


def test_the_projects_own_blog_listing_is_not_grafted(assembly_tree):
    """A project's standalone listing would claim the whole site's blog index."""
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    index = assembly_tree / "site" / "blog" / "index.html"
    if index.exists():
        with open(index, encoding="utf-8") as f:
            assert "standalone listing" not in f.read()


def test_apply_project_files_records_what_the_release_published(assembly_tree):
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    owners = load_files_manifest(str(assembly_tree / "manifests" / "alpha-files.json"))
    assert set(owners["release"]) == {
        "alpha/index.html", "alpha/guide/index.html", "blog/hello/index.html",
    }


def test_apply_project_files_keeps_the_posts_overlay(assembly_tree):
    """The overlay carries posts published between releases; it is merged now."""
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    assert (assembly_tree / "manifests" / "alpha-posts.json").exists()


def test_apply_project_files_posts_scope_touches_only_posts(assembly_tree):
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "posts")
    site = assembly_tree / "site" / "alpha"
    with open(site / "index.html", encoding="utf-8") as f:
        assert "old alpha" in f.read(), "posts scope must not touch project pages"
    with open(assembly_tree / "site" / "blog" / "hello" / "index.html",
              encoding="utf-8") as f:
        assert "hello" in f.read()
    overlay = _read_json(str(assembly_tree / "manifests" / "alpha-posts.json"))
    assert overlay["posts"][0]["slug"] == "hello"


def test_the_posts_scope_claims_the_site_level_paths_it_wrote(assembly_tree):
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "posts")
    owners = load_files_manifest(str(assembly_tree / "manifests" / "alpha-files.json"))
    assert owners["posts"] == ["blog/hello/index.html"]


def test_a_posts_scope_publish_with_no_posts_publishes_nothing(
    assembly_tree, capsys,
):
    """A build that emitted no posts is not an instruction to unpublish."""
    import shutil

    shutil.rmtree(assembly_tree / "source" / "alpha" / "docs" / "_build" / "blog")
    record = assembly_tree / "manifests" / "alpha-files.json"
    _write(str(record), json.dumps({
        "schema_version": 2, "slug": "alpha",
        "owners": {"posts": ["blog/old-post/index.html"]},
    }))

    touched = apply_project_files(
        str(assembly_tree), str(assembly_tree / "source" / "alpha"),
        "alpha", "posts",
    )

    assert touched == []
    assert (assembly_tree / "site" / "blog" / "old-post" / "index.html").exists()
    assert _read_json(str(record))["owners"]["posts"] == [
        "blog/old-post/index.html",
    ]
    assert "nothing to publish" in capsys.readouterr().err


def test_a_graft_refuses_to_overwrite_another_projects_post(assembly_tree):
    """Two projects, one post slug: the write is refused, naming both."""
    _write(str(assembly_tree / "manifests" / "beta-files.json"), json.dumps({
        "schema_version": 2, "slug": "beta",
        "owners": {"release": ["beta/index.html", "blog/hello/index.html"]},
    }))
    with pytest.raises(RuntimeError, match="claimed by 'beta'"):
        apply_project_files(
            str(assembly_tree), str(assembly_tree / "source" / "alpha"),
            "alpha", "full",
        )


def test_a_refused_graft_writes_nothing(assembly_tree):
    _write(str(assembly_tree / "manifests" / "beta-files.json"), json.dumps({
        "schema_version": 2, "slug": "beta",
        "owners": {"release": ["beta/index.html", "blog/hello/index.html"]},
    }))
    with pytest.raises(RuntimeError):
        apply_project_files(
            str(assembly_tree), str(assembly_tree / "source" / "alpha"),
            "alpha", "full",
        )
    assert not (assembly_tree / "site" / "blog" / "hello").exists()
    with open(assembly_tree / "site" / "alpha" / "index.html", encoding="utf-8") as f:
        assert "old alpha" in f.read()


# -- the full integrate run ---------------------------------------------------


def test_full_integrate_grafts_the_build_and_commits(assembly_tree, runner):
    summary = _integrate(assembly_tree, build=False)
    assert summary["committed"] is True
    assert summary["attempt"] == 1
    site = assembly_tree / "site" / "alpha"
    with open(site / "index.html", encoding="utf-8") as f:
        assert "new alpha" in f.read()
    assert not (site / "retired").exists()


def test_full_integrate_leaves_other_projects_alone(assembly_tree, runner):
    _integrate(assembly_tree, build=False)
    with open(assembly_tree / "site" / "beta" / "index.html", encoding="utf-8") as f:
        assert "beta" in f.read()
    assert _read_json(str(assembly_tree / "projects.json"))["beta"]["version"] == "2.0.0"


def test_full_integrate_records_membership(assembly_tree, runner):
    _integrate(assembly_tree, build=False)
    entry = _read_json(str(assembly_tree / "projects.json"))["alpha"]
    assert entry == {"repo": "owner/alpha", "ref": "v1.0.0", "version": "1.0.0"}


def test_full_integrate_regenerates_the_shared_files(assembly_tree, runner):
    summary = _integrate(assembly_tree, build=False)
    names = {os.path.relpath(p, str(assembly_tree / "site")) for p in summary["shared"]}
    assert names == {
        # The listing at its fixed address, the home project's front page
        # re-rendered in place, and the rest of the site-wide artifacts.
        # There is no generated root index.html: the site root is the home
        # project's page.
        os.path.join("projects", "index.html"), "index.html",
        os.path.join("blog", "index.html"), "nav.json",
        "feed.xml", "sitemap.xml", "robots.txt", "llms.txt", "404.html",
        "_headers", "_worker.js",
    }


def test_full_integrate_shared_files_see_the_new_manifest(assembly_tree, runner):
    _integrate(assembly_tree, build=False)
    nav = _read_json(str(assembly_tree / "site" / "nav.json"))
    versions = {p["slug"]: p.get("version") for p in nav["projects"]}
    assert versions["alpha"] == "1.0.0"
    assert versions["beta"] == "2.0.0"


def test_full_integrate_indexes_the_site(assembly_tree, runner):
    _integrate(assembly_tree, build=False)
    pagefind = [c for c in runner.calls if "pagefind" in " ".join(c)]
    assert pagefind, "expected the search index to be rebuilt"
    assert pagefind[0][-2:] == ["--site", str(assembly_tree / "site")]


def test_full_integrate_syncs_with_the_remote_before_writing(assembly_tree, runner):
    _integrate(assembly_tree, build=False)
    order = [" ".join(c[:3]) for c in runner.calls]
    assert order[0].startswith("git fetch")
    assert order[1].startswith("git reset")


def test_full_integrate_stages_and_pushes(assembly_tree, runner):
    _integrate(assembly_tree, build=False)
    assert runner.of("git", "add"), "expected the deploy tree to be staged"
    assert runner.of("git", "push"), "expected the deploy commit to be pushed"


def test_full_integrate_commit_message_names_the_release(assembly_tree, runner):
    _integrate(assembly_tree, build=False)
    commit = [c for c in runner.calls if "commit" in c][0]
    assert commit[-1] == "deploy: alpha v1.0.0"


def test_full_integrate_commits_with_an_explicit_identity(assembly_tree, runner):
    _integrate(assembly_tree, build=False)
    commit = [c for c in runner.calls if "commit" in c][0]
    assert "user.name=github-actions[bot]" in commit
    assert any(a.startswith("user.email=") for a in commit)


def test_integrate_builds_the_source_with_the_detected_version(assembly_tree, runner):
    _integrate(assembly_tree)
    builds = runner.of("selfdoc", "build")
    assert builds and builds[0] == [
        "selfdoc", "build", "--no-auto-commit", "--version", "1.0.0",
    ]


def test_posts_scope_builds_posts_only(assembly_tree, runner):
    _integrate(assembly_tree, scope="posts")
    assert runner.of("selfblog", "build", "--target", "posts")
    assert not runner.of("selfdoc", "build")


def test_posts_scope_replaces_only_the_posts_subtree(assembly_tree, runner):
    _integrate(assembly_tree, scope="posts", build=False)
    with open(assembly_tree / "site" / "alpha" / "index.html", encoding="utf-8") as f:
        assert "old alpha" in f.read()
    assert (assembly_tree / "site" / "blog" / "hello").exists()


def test_shared_only_scope_touches_no_project_files(assembly_tree, runner):
    before = _read_json(str(assembly_tree / "projects.json"))
    summary = _integrate(assembly_tree, scope="shared-only", slug="", build=False)
    with open(assembly_tree / "site" / "alpha" / "index.html", encoding="utf-8") as f:
        assert "old alpha" in f.read()
    assert _read_json(str(assembly_tree / "projects.json")) == before
    assert summary["shared"]


def test_shared_only_scope_still_regenerates_and_commits(assembly_tree, runner):
    _integrate(assembly_tree, scope="shared-only", slug="", build=False)
    commit = [c for c in runner.calls if "commit" in c][0]
    assert commit[-1] == "deploy: shared elements"


def test_empty_scope_means_a_full_build(assembly_tree, runner):
    summary = _integrate(assembly_tree, scope="", build=False)
    assert summary["scope"] == "full"


def test_unknown_scope_is_a_hard_error(assembly_tree, runner):
    with pytest.raises(ValueError, match="unknown scope"):
        _integrate(assembly_tree, scope="everything", build=False)


def test_the_home_projects_page_stays_the_site_root(assembly_tree, runner):
    """A deploy of another project leaves the front page where it is."""
    _integrate(assembly_tree, build=False)
    with open(assembly_tree / "site" / "index.html", encoding="utf-8") as f:
        assert "home" in f.read()
    assert (assembly_tree / "site" / "projects" / "index.html").exists()


def test_the_generated_listing_leaves_the_home_project_out(assembly_tree, runner):
    _integrate(assembly_tree, build=False)
    with open(assembly_tree / "site" / "projects" / "index.html",
              encoding="utf-8") as f:
        listing = f.read()
    assert "Alpha" in listing
    assert ">Home<" not in listing


# -- the retry loop -----------------------------------------------------------


def test_a_rejected_push_is_retried_after_a_re_sync(assembly_tree, monkeypatch):
    recorder = RunRecorder(push_failures=1)
    monkeypatch.setattr("selfblog.assembly.effects.run", recorder)
    summary = _integrate(assembly_tree, build=False)
    assert summary["attempt"] == 2
    assert len(recorder.of("git", "fetch")) == 2, "each attempt re-syncs first"
    assert recorder.pushes == 2


def test_exhausted_attempts_are_a_hard_error(assembly_tree, monkeypatch):
    recorder = RunRecorder(push_failures=99)
    monkeypatch.setattr("selfblog.assembly.effects.run", recorder)
    with pytest.raises(RuntimeError, match="failed after 3 attempt"):
        _integrate(assembly_tree, build=False)
    assert recorder.pushes == 3


def test_attempt_count_is_configurable(assembly_tree, monkeypatch):
    recorder = RunRecorder(push_failures=99)
    monkeypatch.setattr("selfblog.assembly.effects.run", recorder)
    with pytest.raises(RuntimeError):
        _integrate(assembly_tree, build=False, attempts=1)
    assert recorder.pushes == 1


def test_zero_attempts_is_rejected(assembly_tree, runner):
    with pytest.raises(ValueError, match="at least 1"):
        _integrate(assembly_tree, build=False, attempts=0)


# -- the CLI wrapper ----------------------------------------------------------


def test_integrate_command_requires_a_canonical_base(assembly_tree, monkeypatch, capsys):
    from selfblog.cli import _cmd_assembly_integrate

    monkeypatch.chdir(assembly_tree)
    with pytest.raises(SystemExit):
        _cmd_assembly_integrate(None, slug="alpha", canonical_base="")
    assert "--canonical-base is required" in capsys.readouterr().err


def test_integrate_command_runs_the_integration(assembly_tree, runner, monkeypatch, capsys):
    from selfblog.cli import _cmd_assembly_integrate

    monkeypatch.chdir(assembly_tree)
    rc = _cmd_assembly_integrate(
        None, slug="alpha", version="1.0.0", ref="v1.0.0",
        source_repo="owner/alpha", scope="full", canonical_base=CANONICAL_BASE,
        assembly_dir=str(assembly_tree),
    )
    assert rc == 0
    assert "Integrated full scope for alpha" in capsys.readouterr().out


def test_integrate_command_reports_a_bad_scope(assembly_tree, runner, monkeypatch, capsys):
    from selfblog.cli import _cmd_assembly_integrate

    monkeypatch.chdir(assembly_tree)
    with pytest.raises(SystemExit):
        _cmd_assembly_integrate(
            None, slug="alpha", scope="nonsense", canonical_base=CANONICAL_BASE,
            assembly_dir=str(assembly_tree),
        )
    assert "unknown scope" in capsys.readouterr().err


# -- verification blocks the deploy -------------------------------------------
#
# The deploy verifies the tree it assembled before it commits or pushes any
# of it. There is no flag that turns this off: a tree that fails is a tree
# that does not ship.


def _broken_build(root):
    """Put a page the assembly must not serve into the source build."""
    _write(str(root / "source" / "alpha" / "docs" / "_build" / "index.html"),
           "<html><head></head><body>no title, no canonical</body></html>")


def test_a_broken_tree_fails_the_deploy(assembly_tree, runner):
    _broken_build(assembly_tree)
    with pytest.raises(RuntimeError, match="failed verification"):
        _integrate(assembly_tree, build=False)


def test_a_broken_tree_names_every_offender(assembly_tree, runner):
    _broken_build(assembly_tree)
    with pytest.raises(RuntimeError) as exc:
        _integrate(assembly_tree, build=False)
    message = str(exc.value)
    assert "page-metadata" in message
    assert "site/alpha/index.html" in message


def test_nothing_is_deployed_when_verification_fails(assembly_tree, runner):
    """The whole point: the failure lands before the commit and the push."""
    _broken_build(assembly_tree)
    with pytest.raises(RuntimeError):
        _integrate(assembly_tree, build=False)
    assert not runner.of("git", "push"), "a failing tree must never be pushed"
    assert not [c for c in runner.calls if "commit" in c], (
        "a failing tree must not even be committed"
    )


def test_a_manifest_promising_a_page_the_build_dropped_fails_the_deploy(
    assembly_tree, runner,
):
    """A second defect, at the other end of the pipeline."""
    _write(str(assembly_tree / "manifests" / "beta.json"),
           json.dumps(_manifest("beta", "Beta", "2.0.0")
                      | {"pages": [{"path": "gone.md", "title": "Gone"}]}))
    with pytest.raises(RuntimeError, match="manifest-pages-emitted"):
        _integrate(assembly_tree, build=False)


def test_a_sound_tree_still_deploys(assembly_tree, runner):
    summary = _integrate(assembly_tree, build=False)
    assert summary["committed"] is True
    assert runner.of("git", "push")


def test_the_deploy_reports_which_checks_it_ran(assembly_tree, runner):
    summary = _integrate(assembly_tree, build=False)
    assert "roster-agreement" in summary["verified"]
    assert "cross-project-links" in summary["verified"]


def test_an_unconfigured_outbound_check_is_announced(assembly_tree, runner, capsys):
    _integrate(assembly_tree, build=False)
    assert "outbound-links was NOT checked" in capsys.readouterr().err


def test_the_deploy_keeps_the_outbound_results_it_produced(
    assembly_tree, runner, monkeypatch,
):
    """The store is the deploy's to write, so the next deploy inherits it."""
    from selfblog.verify import OUTBOUND_CACHE_PATH

    _write(str(assembly_tree / "outbound.toml"),
           'cache_days = 7\n\n[[page]]\npath = "beta/index.html"\n')
    _write(str(assembly_tree / "site" / "beta" / "index.html"),
           _page("Beta", "beta/", version="2.0.0",
                 marker='<a href="https://live.example.net/">x</a>'))

    asked = []

    def fetch(url):
        asked.append(url)
        return 200, ""

    monkeypatch.setattr("selfblog.verify.fetch_url", fetch)
    _integrate(assembly_tree, build=False)

    assert asked == ["https://live.example.net/"]
    stored = json.loads((assembly_tree / OUTBOUND_CACHE_PATH).read_text())
    assert "https://live.example.net/" in stored["entries"]
    assert any(OUTBOUND_CACHE_PATH in call for call in runner.of("git", "add"))
