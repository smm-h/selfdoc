"""`selfblog assembly preview`: the assembly built locally and served.

The command's whole claim is that what it shows you is what a deploy would
publish, so the tests assert against the tree the *production* functions
produce -- the same graft, the same shared generation, the same chrome
asset, the same verification -- rather than against anything the preview
does of its own.  The server half is asserted on the wire, against a real
``ThreadingHTTPServer`` on an ephemeral loopback port, because the
properties worth having are wire properties: a directory address serves its
index, a content type is right, and an address the tree does not carry
answers 404 with the tree's own page.

The output-directory refusal has both halves: a path git ignores is
accepted, the same path un-ignored is refused.
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import threading

import pytest

from selfblog.chrome import CHROME_DIR
from selfblog.preview import (
    enclosing_worktree,
    make_preview_server,
    out_dir_refusal,
    preview_assembly,
    read_slug,
    refuse_unsafe_out_dir,
    render_report,
)

CANONICAL_BASE = "https://docs.example.com"


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _page(title, canonical, body="", version=""):
    """A page shaped the way a real build's pages are shaped.

    The stylesheet names the project-local ``style.css`` a build writes at
    its own output root, which is what the graft really delivers; the
    shared generator re-points it at the site-level chrome asset.
    """
    version_attr = f' data-default-version="{version}"' if version else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        f"  <title>{title}</title>\n"
        f'  <link rel="canonical" href="{canonical}">\n'
        '  <link rel="stylesheet" href="style.css">\n'
        "</head>\n"
        "<body>\n"
        f'  <dialog class="search-dialog" data-search-base="./"{version_attr}></dialog>\n'
        f"  <main><p>{title} is a page with enough prose in it that the "
        f"search index has words to index and a fragment to render.</p>"
        f"{body}</main>\n"
        "</body>\n"
        "</html>\n"
    )


def _manifest(slug, name, version, pages, posts=()):
    return {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "version": version,
        "description": f"{name} docs",
        "language": "python",
        "base_url": f"{CANONICAL_BASE}/{slug}",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "pages": list(pages),
        "posts": list(posts),
        "last_gen": "2024-01-01T00:00:00+00:00",
    }


def _checkout(root, slug, name, version, *, home=False, pages=(), posts=(),
              listing=None):
    """A source checkout as the preview reads one: config, manifest, build.

    ``docs/_build`` is pre-populated rather than built, so the tests assert
    the graft and everything downstream of it without running a full
    documentation build per case.  Every path below is where a real build
    puts it, which is the only reason the production functions can be
    pointed at it unchanged.
    """
    os.makedirs(root, exist_ok=True)
    config = {
        "name": name,
        "base_url": f"{CANONICAL_BASE}/{slug}",
        "docs": "docs/",
        "output": "docs/_build/",
        "search_engine": "pagefind",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "locales": [{"code": "en", "label": "English", "default": True}],
        "topology": {"slug": slug},
    }
    if version:
        config["versions"] = [{"version": version}]
    else:
        config["unversioned"] = True
    _write(os.path.join(root, "selfdoc.json"), json.dumps(config, indent=2))

    _write(
        os.path.join(root, ".selfdoc", "manifest.json"),
        json.dumps(_manifest(slug, name, version, pages, posts)),
    )

    build = os.path.join(root, "docs", "_build")
    for page in pages:
        rel = page["path"]
        stem = rel[: -len(".md")]
        address = "" if stem == "index" else f"{stem}/"
        out = "index.html" if stem == "index" else f"{stem}/index.html"
        canonical = (
            f"{CANONICAL_BASE}/{address}" if home
            else f"{CANONICAL_BASE}/{slug}/{address}"
        )
        _write(os.path.join(build, *out.split("/")),
               _page(page["title"], canonical, version=version))
    for post in posts:
        _write(
            os.path.join(build, "blog", post["slug"], "index.html"),
            _page(post["title"], f"{CANONICAL_BASE}/blog/{post['slug']}/",
                  version=version),
        )
    # Every selfdoc build writes these for its own standalone hosting; the
    # graft is supposed to leave them behind.
    _write(os.path.join(build, "404.html"), _page("Not found", ""))
    _write(os.path.join(build, "_headers"), "/*\n  X-Test: 1\n")
    if listing is not None:
        _write(os.path.join(root, "docs", "projects.toml"), listing)
    return root


_LISTING = """\
[[category]]
name = "Projects"

[[category.project]]
slug = "alpha"
blurb = "Does the alpha thing."

[[category.project]]
slug = "beta"
blurb = "Does the beta thing."
"""


@pytest.fixture(scope="module")
def previewed(tmp_path_factory):
    """One preview of a home project and two others, assembled for real."""
    root = tmp_path_factory.mktemp("preview")
    home = _checkout(
        str(root / "src" / "home"), "home", "Home", "",
        home=True, listing=_LISTING,
        pages=[{"path": "index.md", "title": "Front page"},
               {"path": "cv.md", "title": "CV"}],
    )
    alpha = _checkout(
        str(root / "src" / "alpha"), "alpha", "Alpha", "1.0.0",
        pages=[{"path": "index.md", "title": "Alpha"},
               {"path": "guide.md", "title": "Alpha Guide"}],
        posts=[{"slug": "hello", "title": "Hello", "date": "2024-06-01",
                "path": "blog/hello.md", "tags": []}],
    )
    beta = _checkout(
        str(root / "src" / "beta"), "beta", "Beta", "2.0.0",
        pages=[{"path": "index.md", "title": "Beta"}],
    )
    out = str(root / "out")
    summary = preview_assembly(
        home_dir=home, project_dirs=[alpha, beta], out_dir=out,
        canonical_base=CANONICAL_BASE, build=False,
    )
    return summary


@pytest.fixture()
def live(previewed):
    """The preview server, on an ephemeral loopback port, torn down after."""
    server = make_preview_server(previewed["site_dir"], 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def _request(port, path, method="GET", follow=False):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request(method, path)
        response = conn.getresponse()
        body = response.read()
        status = response.status
        headers = dict(response.getheaders())
    finally:
        conn.close()
    if follow and status in (301, 302):
        return _request(port, headers["Location"], method=method)
    return status, headers, body


def _site(previewed, *parts):
    return os.path.join(previewed["site_dir"], *parts)


# -- the tree the preview builds -----------------------------------------------


class TestTheTree:
    def test_the_home_project_is_served_at_the_site_root(self, previewed):
        assert os.path.isfile(_site(previewed, "index.html"))
        assert os.path.isfile(_site(previewed, "cv", "index.html"))
        # ...and has no subtree of its own.
        assert not os.path.isdir(_site(previewed, "home"))

    def test_every_other_project_gets_its_own_subtree(self, previewed):
        assert os.path.isfile(_site(previewed, "alpha", "index.html"))
        assert os.path.isfile(_site(previewed, "alpha", "guide", "index.html"))
        assert os.path.isfile(_site(previewed, "beta", "index.html"))

    def test_a_post_is_site_level(self, previewed):
        assert os.path.isfile(_site(previewed, "blog", "hello", "index.html"))

    def test_the_shared_pages_exist(self, previewed):
        for rel in ("projects/index.html", "blog/index.html", "nav.json",
                    "feed.xml", "sitemap.xml", "robots.txt", "llms.txt",
                    "404.html", "_headers", "_worker.js"):
            assert os.path.isfile(_site(previewed, *rel.split("/"))), rel

    def test_the_chrome_asset_is_written_and_every_page_names_it(
            self, previewed):
        chrome_dir = _site(previewed, CHROME_DIR)
        assets = sorted(os.listdir(chrome_dir))
        assert assets, "the shared generator wrote no chrome asset"
        with open(_site(previewed, "alpha", "index.html"),
                  encoding="utf-8") as f:
            page = f.read()
        # The graft delivered a page naming its own style.css; the shared
        # generator re-pointed it at the site-level asset.
        assert f"../{CHROME_DIR}/" in page
        assert 'href="style.css"' not in page

    def test_the_generated_pages_are_styled(self, previewed):
        for rel in ("projects/index.html", "blog/index.html", "404.html"):
            with open(_site(previewed, *rel.split("/")), encoding="utf-8") as f:
                assert CHROME_DIR in f.read(), rel

    def test_the_standalone_deploy_artifacts_are_left_behind(self, previewed):
        # The home project's build wrote a 404.html and _headers for its own
        # hosting; the site's own are the assembly's, not that build's.
        with open(_site(previewed, "_headers"), encoding="utf-8") as f:
            assert "X-Test" not in f.read()
        assert not os.path.isfile(_site(previewed, "alpha", "404.html"))

    def test_the_roster_and_membership_record_are_written(self, previewed):
        with open(os.path.join(previewed["out_dir"], "roster.toml"),
                  encoding="utf-8") as f:
            roster = f.read()
        assert 'home = "home"' in roster
        for slug in ("home", "alpha", "beta"):
            assert f'slug = "{slug}"' in roster
        with open(os.path.join(previewed["out_dir"], "projects.json"),
                  encoding="utf-8") as f:
            membership = json.load(f)
        assert sorted(membership) == ["alpha", "beta", "home"]
        assert membership["alpha"]["version"] == "1.0.0"

    def test_the_manifests_are_copied_beside_the_site(self, previewed):
        manifests = os.path.join(previewed["out_dir"], "manifests")
        assert os.path.isfile(os.path.join(manifests, "alpha.json"))
        assert os.path.isfile(os.path.join(manifests, "home.json"))
        # The home project's curated listing rides along as a sidecar.
        assert os.path.isfile(os.path.join(manifests, "home-listing.json"))

    def test_the_search_index_is_built(self, previewed):
        entry = _site(previewed, "pagefind", "pagefind-entry.json")
        assert os.path.isfile(entry)
        with open(entry, encoding="utf-8") as f:
            assert json.load(f)["languages"]

    def test_the_summary_names_what_was_assembled(self, previewed):
        assert previewed["home"] == "home"
        assert previewed["slugs"] == ["alpha", "beta", "home"]
        assert previewed["shared"]


# -- verification runs against the tree ----------------------------------------


class TestVerification:
    def test_the_real_verification_runs(self, previewed):
        from selfblog.verify import CHECKS

        report = previewed["report"]
        # outbound-links is the one check a preview tree does not configure.
        assert set(report.ran) == set(CHECKS) - {"outbound-links"}

    def test_the_assembled_tree_passes(self, previewed):
        report = previewed["report"]
        assert report.ok, report.error_text()

    def test_the_report_names_the_tree_and_the_counts(self, previewed):
        text = render_report(previewed["report"],
                             out_dir=previewed["out_dir"])
        assert previewed["out_dir"] in text
        assert "check(s) ran" in text
        assert "Every check that ran passed." in text

    def test_a_failing_report_says_the_preview_serves_it_anyway(self):
        from selfblog.verify import Failure, VerifyReport

        report = VerifyReport(
            failures=[Failure("page-metadata", "site/x.html", "no title")],
            ran=["page-metadata"],
        )
        text = render_report(report, out_dir="/tmp/x")
        assert "no title" in text
        assert "serves this tree anyway" in text


# -- the server ----------------------------------------------------------------


class TestTheServer:
    def test_the_root_serves_the_home_projects_front_page(self, live):
        status, headers, body = _request(live, "/")
        assert status == 200
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert b"Front page" in body

    def test_a_project_page_is_served_under_its_slug(self, live):
        status, _headers, body = _request(live, "/alpha/guide/")
        assert status == 200
        assert b"Alpha Guide" in body

    def test_a_directory_without_a_trailing_slash_redirects(self, live):
        status, headers, _body = _request(live, "/alpha")
        assert status == 301
        assert headers["Location"] == "/alpha/"
        status, _headers, body = _request(live, "/alpha", follow=True)
        assert status == 200
        assert b"Alpha" in body

    def test_content_types_come_from_the_extension(self, live):
        for path, expected in (
            ("/nav.json", "application/json; charset=utf-8"),
            ("/feed.xml", "application/xml; charset=utf-8"),
            ("/robots.txt", "text/plain; charset=utf-8"),
            ("/sitemap.xml", "application/xml; charset=utf-8"),
        ):
            status, headers, _body = _request(live, path)
            assert status == 200, path
            assert headers["Content-Type"] == expected, path

    def test_the_chrome_asset_is_served_as_css(self, live, previewed):
        name = sorted(os.listdir(_site(previewed, CHROME_DIR)))[0]
        status, headers, body = _request(live, f"/{CHROME_DIR}/{name}")
        assert status == 200
        assert headers["Content-Type"] == "text/css; charset=utf-8"
        assert body

    def test_an_unknown_address_answers_the_trees_404_page(self, live):
        status, headers, body = _request(live, "/nothing/here/")
        assert status == 404
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert b"404" in body or b"not found" in body.lower()

    def test_the_404_body_is_the_sites_own_page(self, live, previewed):
        _status, _headers, body = _request(live, "/nothing/here/")
        with open(_site(previewed, "404.html"), "rb") as f:
            assert body == f.read()

    def test_a_path_escaping_the_root_is_not_served(self, live):
        status, _headers, _body = _request(live, "/../../etc/passwd")
        assert status == 404

    def test_head_answers_the_headers_without_a_body(self, live):
        status, headers, body = _request(live, "/", method="HEAD")
        assert status == 200
        assert int(headers["Content-Length"]) > 0
        assert body == b""


# -- the command surface -------------------------------------------------------


class TestTheCommand:
    """What `selfblog assembly preview` declares at registration.

    The declarations are the contract: which inputs have no default, that
    the command refuses to pretend it can preview itself, and that it is
    classified as the mutation it is.
    """

    def _command(self):
        import selfblog.cli

        return selfblog.cli.app._groups["assembly"].commands["preview"]

    def _flags(self):
        return {f.name: f for f in self._command().flags}

    def test_it_is_mutating_and_not_consequential(self):
        cmd = self._command()
        assert cmd.effect == "mutating"
        assert cmd.consequential is False

    def test_it_refuses_dry_run_with_a_reason(self):
        cmd = self._command()
        assert cmd.dry_run_supported is False
        assert "look at" in cmd.dry_run_unsupported_reason

    def test_every_input_that_decides_the_output_is_required(self):
        # Presence is declared, never derived: an absent default no longer
        # means anything on its own.
        flags = self._flags()
        for name in ("home", "out", "port", "canonical-base", "build"):
            assert flags[name].presence == "required", (
                f"--{name} must declare presence=required"
            )

    def test_the_build_choice_is_negatable_rather_than_defaulted(self):
        build = self._flags()["build"]
        assert build.type is bool
        assert build.negatable

    def test_repo_is_repeatable_and_deduplicated(self):
        repo = self._flags()["repo"]
        assert repo.repeatable
        assert repo.unique


# -- where a preview may be written --------------------------------------------


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class TestTheOutputDirectory:
    def test_a_directory_outside_every_repository_is_accepted(self, tmp_path):
        out = str(tmp_path / "preview")
        assert enclosing_worktree(out) == ""
        assert out_dir_refusal(out) == ""
        refuse_unsafe_out_dir(out)

    def test_an_untracked_path_inside_a_checkout_is_refused(self, tmp_path):
        repo = str(tmp_path / "repo")
        os.makedirs(repo)
        _git(repo, "init")
        out = os.path.join(repo, "preview")
        assert enclosing_worktree(out) == os.path.realpath(repo)
        reason = out_dir_refusal(out)
        assert "does not ignore it" in reason
        assert "preview" in reason
        with pytest.raises(RuntimeError, match="does not ignore it"):
            refuse_unsafe_out_dir(out)

    def test_the_same_path_gitignored_is_accepted(self, tmp_path):
        repo = str(tmp_path / "repo")
        os.makedirs(repo)
        _git(repo, "init")
        out = os.path.join(repo, "preview")
        assert out_dir_refusal(out) != ""
        _write(os.path.join(repo, ".gitignore"), "preview/\n")
        assert out_dir_refusal(out) == ""
        refuse_unsafe_out_dir(out)

    def test_the_root_of_a_checkout_is_refused_by_name(self, tmp_path):
        repo = str(tmp_path / "repo")
        os.makedirs(repo)
        _git(repo, "init")
        assert "is the root of the git working tree" in out_dir_refusal(repo)

    def test_the_pipeline_refuses_before_it_writes_anything(self, tmp_path):
        repo = str(tmp_path / "repo")
        os.makedirs(repo)
        _git(repo, "init")
        out = os.path.join(repo, "preview")
        home = _checkout(str(tmp_path / "home"), "home", "Home", "",
                         home=True, listing=_LISTING,
                         pages=[{"path": "index.md", "title": "Front page"}])
        with pytest.raises(RuntimeError, match="does not ignore it"):
            preview_assembly(
                home_dir=home, project_dirs=[], out_dir=out,
                canonical_base=CANONICAL_BASE, build=False,
            )
        assert not os.path.exists(out)


# -- what a checkout has to declare --------------------------------------------


class TestTheCheckouts:
    def test_a_checkout_with_no_config_is_refused(self, tmp_path):
        empty = str(tmp_path / "empty")
        os.makedirs(empty)
        with pytest.raises(RuntimeError, match="no selfdoc.json"):
            read_slug(empty)

    def test_a_checkout_with_no_slug_is_refused(self, tmp_path):
        root = str(tmp_path / "noslug")
        os.makedirs(root)
        _write(os.path.join(root, "selfdoc.json"), json.dumps({
            "name": "No Slug",
            "base_url": CANONICAL_BASE,
            "unversioned": True,
            "search_engine": "pagefind",
            "author": {"name": "Test Author", "url": "https://author.example"},
            "locales": [{"code": "en", "label": "English", "default": True}],
        }))
        with pytest.raises(RuntimeError, match="no topology.slug"):
            read_slug(root)

    def test_two_checkouts_with_the_same_slug_are_refused(self, tmp_path):
        home = _checkout(str(tmp_path / "home"), "home", "Home", "",
                         home=True, listing=_LISTING,
                         pages=[{"path": "index.md", "title": "Front page"}])
        twin = _checkout(str(tmp_path / "twin"), "home", "Twin", "1.0.0",
                         pages=[{"path": "index.md", "title": "Twin"}])
        with pytest.raises(RuntimeError, match="declare the slug 'home'"):
            preview_assembly(
                home_dir=home, project_dirs=[twin],
                out_dir=str(tmp_path / "out"),
                canonical_base=CANONICAL_BASE, build=False,
            )

    def test_a_canonical_base_is_required(self, tmp_path):
        home = _checkout(str(tmp_path / "home"), "home", "Home", "",
                         home=True, listing=_LISTING,
                         pages=[{"path": "index.md", "title": "Front page"}])
        with pytest.raises(ValueError, match="canonical_base is required"):
            preview_assembly(
                home_dir=home, project_dirs=[], out_dir=str(tmp_path / "out"),
                canonical_base="", build=False,
            )
