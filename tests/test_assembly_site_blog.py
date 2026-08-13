"""The site-level blog, end to end: two projects with posts, one deploy.

A post is not a project's page.  It is emitted at ``blog/<post-slug>/`` at
the site root, with no project segment, because the assembled site has one
blog whose slug namespace every project shares.  Three things used to
disagree about that: the graft copied a project's whole build into
``site/<slug>/`` (so posts landed at ``site/<slug>/blog/``), the blog index
linked ``<slug>/posts/<post>/``, and the posts-scope deploy read a
``posts/`` directory the build had stopped emitting -- so it published
nothing and then pruned the posts it had published before.

This file is the assertion that they agree now, on a tree shaped like a real
one: two declared projects that both publish posts, a post published between
releases by nobody's build, and a full deploy of one of the projects.  What
it checks is the whole contract at once -- where a post lands, what survives
a release that did not produce it, what the blog index links, and that the
deploy's own verification passes over the result.
"""

import json
import os

import pytest

from selfblog.assembly import (
    generate_shared_files,
    integrate_project,
    load_files_manifest,
)
from selfblog.verify import verify_assembly

from tests.test_assembly_integrate import (  # noqa: F401  (fixtures)
    CANONICAL_BASE,
    ROSTER,
    RunRecorder,
    _manifest,
    _page,
    _write,
    runner,
)


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _post(slug, title, date):
    return {"slug": slug, "title": title, "date": date,
            "path": f"blog/{slug}.md", "tags": []}


@pytest.fixture()
def blogging_assembly(tmp_path):
    """An assembly whose blog already carries two projects' posts.

    * ``beta`` released a post, ``beta-news``, and claims its file.
    * ``alpha`` published ``out-of-band`` between releases: it is in
      alpha's post overlay and in nobody's published-file record, so no
      publisher is entitled to remove it.
    * ``alpha``'s clone is built and waiting to be grafted, carrying a new
      post ``hello`` and the standalone blog listing its own build renders.
    """
    root = tmp_path / "assembly"
    site = root / "site"
    manifests = root / "manifests"

    from selfblog.assembly import render_roster

    _write(str(root / "roster.toml"), render_roster(ROSTER.values(), home="home"))
    _write(str(root / "projects.json"), json.dumps({
        "home": {"repo": "owner/home", "ref": "v0.1.0", "version": "0.1.0"},
        "alpha": {"repo": "owner/alpha", "ref": "v0.9.0", "version": "0.9.0"},
        "beta": {"repo": "owner/beta", "ref": "v2.0.0", "version": "2.0.0"},
    }, indent=2) + "\n")

    # Two project subtrees.
    _write(str(site / "alpha" / "index.html"),
           _page("Alpha", "alpha/", marker="old alpha"))
    _write(str(site / "beta" / "index.html"),
           _page("Beta", "beta/", marker="beta", version="2.0.0"))
    _write(str(site / "index.html"), _page("Front page", "", marker="home"))

    # Two posts already on the site-level blog, from two different projects
    # and two different publishers.
    _write(str(site / "blog" / "beta-news" / "index.html"),
           _page("Beta News", "blog/beta-news/", marker="beta news"))
    _write(str(site / "blog" / "out-of-band" / "index.html"),
           _page("Out Of Band", "blog/out-of-band/", marker="out of band"))

    _write(str(manifests / "alpha.json"),
           json.dumps(_manifest("alpha", "Alpha", "0.9.0")))
    _write(str(manifests / "alpha-posts.json"),
           json.dumps(_manifest("alpha", "Alpha", "0.9.0", posts=[
               _post("out-of-band", "Out Of Band", "2024-05-01"),
           ])))
    _write(str(manifests / "beta.json"),
           json.dumps(_manifest("beta", "Beta", "2.0.0", posts=[
               _post("beta-news", "Beta News", "2024-04-01"),
           ])))
    _write(str(manifests / "alpha-files.json"), json.dumps({
        "schema_version": 2, "slug": "alpha",
        "owners": {"release": ["alpha/index.html"]},
    }))
    _write(str(manifests / "beta-files.json"), json.dumps({
        "schema_version": 2, "slug": "beta",
        "owners": {"release": ["beta/index.html", "blog/beta-news/index.html"]},
    }))
    _write(str(manifests / "home.json"),
           json.dumps(_manifest("home", "Home", "0.1.0")))
    _write(str(manifests / "home-files.json"), json.dumps({
        "schema_version": 2, "slug": "home",
        "owners": {"release": ["index.html"]},
    }))
    # A declared home carries its curated listing: the deploy copies it in
    # beside the manifests, and shared generation refuses without it.
    _write(str(manifests / "home-listing.json"), json.dumps({
        "format_version": 1, "slug": "home",
        "categories": [{
            "name": "Projects",
            "projects": [
                {"slug": "alpha", "blurb": "Does the alpha thing.",
                 "url": "", "name": ""},
                {"slug": "beta", "blurb": "Does the beta thing.",
                 "url": "", "name": ""},
            ],
        }],
    }))

    # Alpha's clone, built and waiting.
    source = root / "source" / "alpha"
    _write(str(source / "selfdoc.json"),
           json.dumps({"versions": [{"version": "1.0.0"}]}))
    build = source / "docs" / "_build"
    _write(str(build / "index.html"),
           _page("Alpha", "alpha/", marker="new alpha", version="1.0.0"))
    _write(str(build / "guide" / "index.html"),
           _page("Alpha Guide", "alpha/guide/", marker="new guide",
                 version="1.0.0"))
    _write(str(build / "blog" / "index.html"),
           _page("Alpha Posts", "blog/", marker="standalone listing",
                 version="1.0.0"))
    _write(str(build / "blog" / "hello" / "index.html"),
           _page("Hello", "blog/hello/", marker="hello", version="1.0.0"))
    _write(str(source / ".selfdoc" / "manifest.json"),
           json.dumps(_manifest("alpha", "Alpha", "1.0.0", posts=[
               _post("hello", "Hello", "2024-06-01"),
           ])))
    return root


@pytest.fixture()
def deployed(blogging_assembly, runner):  # noqa: F811  (fixture)
    """The tree after a full deploy of alpha, and the deploy's summary."""
    summary = integrate_project(
        slug="alpha", version="1.0.0", ref="v1.0.0",
        source_repo="owner/alpha", scope="full",
        canonical_base=CANONICAL_BASE, assembly_dir=str(blogging_assembly),
        retry_delay=0, build=False,
    )
    return blogging_assembly, summary


# -- where a post lands --------------------------------------------------------


def test_the_released_post_lands_on_the_site_level_blog(deployed):
    root, _summary = deployed
    assert (root / "site" / "blog" / "hello" / "index.html").exists()
    assert "hello" in _read(str(root / "site" / "blog" / "hello" / "index.html"))


def test_no_post_lands_under_a_project_slug(deployed):
    root, _summary = deployed
    assert not (root / "site" / "alpha" / "blog").exists()
    assert not (root / "site" / "alpha" / "posts").exists()


def test_the_projects_own_blog_listing_never_reaches_the_site(deployed):
    """The site's blog index lists every project; a project's own would not."""
    root, _summary = deployed
    assert "standalone listing" not in _read(
        str(root / "site" / "blog" / "index.html")
    )


def test_the_release_claims_its_posts_at_their_site_level_address(deployed):
    root, _summary = deployed
    owners = load_files_manifest(str(root / "manifests" / "alpha-files.json"))
    assert "blog/hello/index.html" in owners["release"]
    assert "alpha/index.html" in owners["release"]


# -- what survives a deploy that did not produce it ----------------------------


def test_another_projects_post_survives(deployed):
    root, _summary = deployed
    survivor = root / "site" / "blog" / "beta-news" / "index.html"
    assert survivor.exists()
    assert "beta news" in _read(str(survivor))


def test_a_post_published_between_releases_survives(deployed):
    root, _summary = deployed
    survivor = root / "site" / "blog" / "out-of-band" / "index.html"
    assert survivor.exists()
    assert "out of band" in _read(str(survivor))


def test_another_projects_claim_is_left_alone(deployed):
    root, _summary = deployed
    owners = load_files_manifest(str(root / "manifests" / "beta-files.json"))
    assert owners["release"] == ["beta/index.html", "blog/beta-news/index.html"]


# -- what the blog index, the sitemap and the feed say -------------------------


def test_the_blog_index_links_every_post_at_the_site_level(deployed):
    root, _summary = deployed
    blog = _read(str(root / "site" / "blog" / "index.html"))
    for slug in ("hello", "beta-news", "out-of-band"):
        assert f'href="../blog/{slug}/"' in blog


def test_the_blog_index_names_the_project_each_post_came_from(deployed):
    """The project is metadata on the row, not part of the post's address."""
    root, _summary = deployed
    blog = _read(str(root / "site" / "blog" / "index.html"))
    assert "Alpha" in blog and "Beta" in blog
    assert "/alpha/blog/" not in blog and "/alpha/posts/" not in blog


def test_the_sitemap_lists_every_post_at_the_site_level(deployed):
    root, _summary = deployed
    sitemap = _read(str(root / "site" / "sitemap.xml"))
    for slug in ("hello", "beta-news", "out-of-band"):
        assert f"{CANONICAL_BASE}/blog/{slug}/" in sitemap


def test_the_feed_links_every_post_at_the_site_level(deployed):
    root, _summary = deployed
    feed = _read(str(root / "site" / "feed.xml"))
    for slug in ("hello", "beta-news", "out-of-band"):
        assert f'<link href="{CANONICAL_BASE}/blog/{slug}/"/>' in feed


# -- the deploy's own verification ---------------------------------------------


def test_the_deploy_verified_the_tree_it_pushed(deployed):
    root, summary = deployed
    assert summary["committed"] is True
    for check in ("manifest-posts-emitted", "sitemap-entries", "feed-links"):
        assert check in summary["verified"]


def test_the_assembled_tree_verifies_clean(deployed):
    """The same assertions again, by hand, over what the deploy left."""
    root, _summary = deployed
    report = verify_assembly(str(root), canonical_base=CANONICAL_BASE)
    assert report.ok, report.error_text()
    for check in ("manifest-posts-emitted", "sitemap-entries", "feed-links"):
        assert check in report.ran


def test_every_post_the_manifests_list_was_emitted(deployed):
    root, _summary = deployed
    report = verify_assembly(str(root), canonical_base=CANONICAL_BASE)
    assert report.failures_of("manifest-posts-emitted") == []
    emitted = sorted(
        name for name in os.listdir(root / "site" / "blog")
        if os.path.isdir(root / "site" / "blog" / name)
    )
    assert emitted == ["beta-news", "hello", "out-of-band"]


# -- one slug namespace, refused in both places --------------------------------


def test_two_projects_claiming_one_post_slug_is_refused_at_the_merge(
    blogging_assembly,
):
    """The merge reads the manifests, and names both projects."""
    _write(str(blogging_assembly / "manifests" / "beta.json"),
           json.dumps(_manifest("beta", "Beta", "2.0.0", posts=[
               _post("out-of-band", "Stolen", "2024-04-01"),
           ])))
    with pytest.raises(RuntimeError, match="Duplicate post slug 'out-of-band'"):
        generate_shared_files(
            str(blogging_assembly / "site"),
            str(blogging_assembly / "manifests"),
            CANONICAL_BASE, docs_base=CANONICAL_BASE,
        )


def test_the_refusal_names_the_site_level_address(blogging_assembly):
    _write(str(blogging_assembly / "manifests" / "beta.json"),
           json.dumps(_manifest("beta", "Beta", "2.0.0", posts=[
               _post("out-of-band", "Stolen", "2024-04-01"),
           ])))
    with pytest.raises(RuntimeError, match=r"blog/<slug>/"):
        generate_shared_files(
            str(blogging_assembly / "site"),
            str(blogging_assembly / "manifests"),
            CANONICAL_BASE, docs_base=CANONICAL_BASE,
        )


def test_a_deploy_refuses_to_overwrite_another_projects_post(
    blogging_assembly, runner,  # noqa: F811  (fixture)
):
    """The graft is checked too, before a byte is written over the other's."""
    _write(str(blogging_assembly / "manifests" / "beta-files.json"), json.dumps({
        "schema_version": 2, "slug": "beta",
        "owners": {"release": ["beta/index.html", "blog/hello/index.html"]},
    }))
    with pytest.raises(RuntimeError, match="claimed by 'beta'"):
        integrate_project(
            slug="alpha", version="1.0.0", ref="v1.0.0",
            source_repo="owner/alpha", scope="full",
            canonical_base=CANONICAL_BASE,
            assembly_dir=str(blogging_assembly), retry_delay=0, build=False,
        )
    assert not runner.of("git", "push")
