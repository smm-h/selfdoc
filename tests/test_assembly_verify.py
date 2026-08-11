"""Tests for `selfblog assembly verify` -- the assertions that block a deploy.

Every test here works the same way: the fixture builds an assembly tree
that passes verification, one test injects exactly one defect, and the
assertion that owns that defect is the one that fails.  A check with no
test that can fail it is a check nobody has shown to work, so there is one
injected defect per asserted property.
"""

import json
import os

import pytest

from selfblog.assembly import RosterEntry, generate_shared_files, render_roster
from selfblog.verify import (
    CHECKS,
    OUTBOUND_CACHE_PATH,
    OUTBOUND_PATH,
    extract_link_registry,
    load_outbound,
    parse_outbound,
    read_tree,
    render_outbound_cache,
    verify_assembly,
)

CANONICAL_BASE = "https://docs.example.com"

ROSTER = {
    "alpha": RosterEntry("alpha", "owner/alpha"),
    "beta": RosterEntry("beta", "owner/beta"),
}


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _page(title, canonical, body="", version=""):
    """A page shaped the way a real build's pages are shaped."""
    version_attr = f' data-default-version="{version}"' if version else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        f"  <title>{title}</title>\n"
        f'  <link rel="canonical" href="{canonical}">\n'
        "</head>\n"
        "<body>\n"
        f'  <dialog class="search-dialog" data-search-base="./"{version_attr}></dialog>\n'
        f"{body}\n"
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
        "pages": list(pages),
        "posts": list(posts),
        "last_gen": "2024-01-01T00:00:00+00:00",
    }


@pytest.fixture()
def assembly(tmp_path):
    """An assembled tree that passes every assertion.

    Two declared projects, one of them with a post and a cross-project
    link, the shared files as the deploy's own generator writes them, and
    a search index as pagefind leaves one.
    """
    root = tmp_path / "assembly"
    site = root / "site"
    manifests = root / "manifests"

    _write(str(root / "roster.toml"), render_roster(ROSTER.values()))
    _write(str(root / "projects.json"), json.dumps({
        "alpha": {"repo": "owner/alpha", "ref": "v1.0.0", "version": "1.0.0"},
        "beta": {"repo": "owner/beta", "ref": "v2.0.0", "version": "2.0.0"},
    }, indent=2) + "\n")

    _write(str(manifests / "alpha.json"), json.dumps(_manifest(
        "alpha", "Alpha", "1.0.0",
        pages=[{"path": "index.md", "title": "Home"},
               {"path": "guide.md", "title": "Guide"}],
        posts=[{"slug": "hello", "title": "Hello", "date": "2024-06-01",
                "path": "blog/hello.md", "tags": []}],
    )))
    _write(str(manifests / "beta.json"), json.dumps(_manifest(
        "beta", "Beta", "2.0.0",
        pages=[{"path": "index.md", "title": "Home"}],
    )))
    _write(str(manifests / "alpha-files.json"), json.dumps({
        "schema_version": 1, "slug": "alpha",
        "owners": {"release": ["index.html", "guide/index.html"]},
    }))

    _write(str(site / "alpha" / "index.html"),
           _page("Alpha", f"{CANONICAL_BASE}/alpha/",
                 body='  <a href="guide/">Guide</a>', version="1.0.0"))
    _write(str(site / "alpha" / "guide" / "index.html"),
           _page("Alpha Guide", f"{CANONICAL_BASE}/alpha/guide/",
                 body='  <a href="../../beta/">Beta</a>', version="1.0.0"))
    _write(str(site / "alpha" / "posts" / "hello" / "index.html"),
           _page("Hello", f"{CANONICAL_BASE}/alpha/posts/hello/",
                 version="1.0.0"))
    _write(str(site / "beta" / "index.html"),
           _page("Beta", f"{CANONICAL_BASE}/beta/", version="2.0.0"))

    # The search index, as pagefind leaves it.
    _write(str(site / "pagefind" / "pagefind.js"), "// index")

    generate_shared_files(
        str(site), str(manifests), CANONICAL_BASE, docs_base=CANONICAL_BASE,
    )
    return root


def _verify(root, **kwargs):
    kwargs.setdefault("canonical_base", CANONICAL_BASE)
    return verify_assembly(str(root), **kwargs)


def _checks_that_failed(report):
    return {f.check for f in report.failures}


# -- the clean tree ------------------------------------------------------------


def test_a_sound_tree_passes_every_assertion(assembly):
    report = _verify(assembly)
    assert report.ok, report.error_text()


def test_every_check_but_outbound_ran(assembly):
    report = _verify(assembly)
    assert set(report.ran) == set(CHECKS) - {"outbound-links"}


def test_a_canonical_base_is_required(assembly):
    with pytest.raises(ValueError, match="canonical_base is required"):
        verify_assembly(str(assembly), canonical_base="")


# -- roster, subtrees and manifests agree in both directions -------------------


def test_an_undeclared_subtree_fails(assembly):
    _write(str(assembly / "site" / "gamma" / "index.html"),
           _page("Gamma", f"{CANONICAL_BASE}/gamma/"))
    report = _verify(assembly)
    assert "roster-agreement" in _checks_that_failed(report)
    assert any("gamma" in f.offender for f in report.failures_of("roster-agreement"))


def test_a_declared_project_with_no_subtree_fails(assembly):
    roster = dict(ROSTER)
    roster["gamma"] = RosterEntry("gamma", "owner/gamma")
    _write(str(assembly / "roster.toml"), render_roster(roster.values()))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("roster-agreement")]
    assert any("gamma" in m and "no site/ subtree" in m for m in messages)


def test_an_orphan_manifest_fails(assembly):
    _write(str(assembly / "manifests" / "gamma-posts.json"), json.dumps(
        _manifest("gamma", "Gamma", "1.0.0", pages=[])))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("roster-agreement")]
    assert any("gamma-posts.json" in m for m in messages)


def test_an_orphan_files_sidecar_fails(assembly):
    """A sidecar of any kind counts: it is not a manifest, but it is a trace."""
    _write(str(assembly / "manifests" / "gamma-files.json"), json.dumps({
        "schema_version": 1, "slug": "gamma", "owners": {},
    }))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("roster-agreement")]
    assert any("gamma-files.json" in m for m in messages)


def test_a_declared_project_with_no_manifest_fails(assembly):
    os.remove(str(assembly / "manifests" / "beta.json"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("roster-agreement")]
    assert any("beta" in m and "manifests/<slug>.json" in m for m in messages)


def test_a_membership_record_for_an_undeclared_project_fails(assembly):
    _write(str(assembly / "projects.json"), json.dumps({
        "alpha": {"repo": "owner/alpha", "ref": "v1", "version": "1.0.0"},
        "beta": {"repo": "owner/beta", "ref": "v2", "version": "2.0.0"},
        "gamma": {"repo": "owner/gamma", "ref": "v3", "version": "3.0.0"},
    }))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("roster-agreement")]
    assert any("gamma" in m for m in messages)


# -- a manifest describes the tree it sits next to -----------------------------


def test_a_manifest_naming_another_slug_fails(assembly):
    data = _manifest("elsewhere", "Beta", "2.0.0",
                     pages=[{"path": "index.md", "title": "Home"}])
    _write(str(assembly / "manifests" / "beta.json"), json.dumps(data))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("manifest-identity")]
    assert any("elsewhere" in m for m in messages)


def test_a_manifest_version_the_pages_disagree_with_fails(assembly):
    """Manifest and tree from different builds is the classic stale deploy."""
    _write(str(assembly / "site" / "beta" / "index.html"),
           _page("Beta", f"{CANONICAL_BASE}/beta/", version="1.9.0"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("manifest-identity")]
    assert any("1.9.0" in m and "2.0.0" in m for m in messages)


def test_the_current_version_sitting_in_the_archive_fails(assembly):
    _write(str(assembly / "site" / "alpha" / "v" / "1.0.0" / "index.html"),
           _page("Alpha", f"{CANONICAL_BASE}/alpha/", version="1.0.0"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("manifest-identity")]
    assert any("v/1.0.0" in m for m in messages)


# -- every page and post a manifest lists was emitted --------------------------


def test_a_listed_page_that_was_not_emitted_fails(assembly):
    os.remove(str(assembly / "site" / "alpha" / "guide" / "index.html"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("manifest-pages-emitted")]
    assert any("guide.md" in m for m in messages)


def test_a_listed_post_that_was_not_emitted_fails(assembly):
    os.remove(str(assembly / "site" / "alpha" / "posts" / "hello" / "index.html"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("manifest-posts-emitted")]
    assert any("hello" in m for m in messages)


def test_a_post_overlay_is_verified_too(assembly):
    """The overlay replaces the manifest's posts, so it is what is checked."""
    overlay = _manifest("alpha", "Alpha", "1.0.0", pages=[], posts=[
        {"slug": "out-of-band", "title": "Out of band", "date": "2024-07-01",
         "path": "blog/out-of-band.md", "tags": []},
    ])
    _write(str(assembly / "manifests" / "alpha-posts.json"), json.dumps(overlay))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("manifest-posts-emitted")]
    assert any("out-of-band" in m for m in messages)


# -- the shared artifacts ------------------------------------------------------


@pytest.mark.parametrize("rel", [
    "index.html", "blog/index.html", "robots.txt", "404.html", "nav.json",
])
def test_a_missing_shared_artifact_fails(assembly, rel):
    os.remove(str(assembly / "site" / rel.replace("/", os.sep)))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("shared-artifacts")]
    assert any(rel in m for m in messages)


def test_an_unparsable_sitemap_fails(assembly):
    _write(str(assembly / "site" / "sitemap.xml"), "<urlset><url></urlset>")
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("shared-artifacts")]
    assert any("sitemap.xml" in m and "does not parse" in m for m in messages)


def test_an_unparsable_feed_fails(assembly):
    _write(str(assembly / "site" / "feed.xml"), "<feed><entry></feed>")
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("shared-artifacts")]
    assert any("feed.xml" in m and "does not parse" in m for m in messages)


def test_an_unparsable_nav_json_fails(assembly):
    _write(str(assembly / "site" / "nav.json"), "{not json")
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("shared-artifacts")]
    assert any("nav.json" in m and "does not parse" in m for m in messages)


def test_an_empty_search_index_fails(assembly):
    os.remove(str(assembly / "site" / "pagefind" / "pagefind.js"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("shared-artifacts")]
    assert any("pagefind" in m for m in messages)


def test_a_portfolio_moves_the_listing_and_the_listing_is_checked(assembly):
    """With a portfolio at the apex, the project listing is /projects/."""
    _write(str(assembly / "portfolio" / "index.html"),
           "<html><head><title>Me</title></head><body>portfolio</body></html>")
    generate_shared_files(
        str(assembly / "site"), str(assembly / "manifests"), CANONICAL_BASE,
        docs_base=CANONICAL_BASE,
        portfolio_file=str(assembly / "portfolio" / "index.html"),
        portfolio_canonical="https://apex.example.com/",
    )
    assert _verify(assembly).ok

    os.remove(str(assembly / "site" / "projects" / "index.html"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("shared-artifacts")]
    assert any("projects/index.html" in m for m in messages)


# -- every reference resolves --------------------------------------------------


def test_a_link_to_a_page_that_was_not_written_fails(assembly):
    _write(str(assembly / "site" / "alpha" / "index.html"),
           _page("Alpha", f"{CANONICAL_BASE}/alpha/",
                 body='  <a href="missing/">Missing</a>', version="1.0.0"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("internal-references")]
    assert any("missing/" in m for m in messages)


def test_a_sitemap_entry_with_no_page_fails(assembly):
    sitemap = assembly / "site" / "sitemap.xml"
    text = sitemap.read_text().replace(
        "</urlset>",
        f"  <url><loc>{CANONICAL_BASE}/alpha/ghost/</loc></url>\n</urlset>",
    )
    _write(str(sitemap), text)
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("sitemap-entries")]
    assert any("ghost" in m for m in messages)


def test_a_feed_link_with_no_page_fails(assembly):
    feed = assembly / "site" / "feed.xml"
    text = feed.read_text().replace(
        "</feed>",
        f'  <entry><link href="{CANONICAL_BASE}/alpha/posts/ghost/"/></entry>\n</feed>',
    )
    _write(str(feed), text)
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("feed-links")]
    assert any("ghost" in m for m in messages)


# -- every page is addressable -------------------------------------------------


def test_a_page_with_no_title_fails(assembly):
    _write(str(assembly / "site" / "beta" / "index.html"),
           '<html><head><title></title>'
           f'<link rel="canonical" href="{CANONICAL_BASE}/beta/">'
           "</head><body>b</body></html>")
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("page-metadata")]
    assert any("beta/index.html" in m and "no title" in m for m in messages)


def test_a_page_with_no_canonical_fails(assembly):
    _write(str(assembly / "site" / "beta" / "index.html"),
           "<html><head><title>Beta</title></head><body>b</body></html>")
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("page-metadata")]
    assert any("rel=canonical" in m for m in messages)


def test_a_canonical_pointing_off_the_site_fails(assembly):
    _write(str(assembly / "site" / "beta" / "index.html"),
           _page("Beta", "https://elsewhere.example.net/beta/", version="2.0.0"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("page-metadata")]
    assert any("elsewhere.example.net" in m for m in messages)


# -- nothing half-built or per-project leaked in -------------------------------


def test_an_unresolved_directive_marker_fails(assembly):
    _write(str(assembly / "site" / "beta" / "index.html"),
           _page("Beta", f"{CANONICAL_BASE}/beta/", version="2.0.0",
                 body="<blockquote><em>[selfdoc: python_ref target=x "
                      "— not yet resolved]</em></blockquote>"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("unresolved-directives")]
    assert any("not yet resolved" in m for m in messages)


def test_a_raw_directive_marker_in_prose_fails(assembly):
    _write(str(assembly / "site" / "beta" / "index.html"),
           _page("Beta", f"{CANONICAL_BASE}/beta/", version="2.0.0",
                 body="<p>\n:-: python_ref target=selfdoc.build\n</p>"))
    report = _verify(assembly)
    assert "unresolved-directives" in _checks_that_failed(report)


def test_a_directive_quoted_in_a_code_block_is_not_a_defect(assembly):
    """The directive documentation quotes every marker there is."""
    _write(str(assembly / "site" / "beta" / "index.html"),
           _page("Beta", f"{CANONICAL_BASE}/beta/", version="2.0.0",
                 body="<pre><code>:-: python_ref target=x\n"
                      ":&lt;: cli_ref\n:&gt;:</code></pre>"))
    report = _verify(assembly)
    assert report.failures_of("unresolved-directives") == []


@pytest.mark.parametrize("rel", [
    "alpha/_headers", "alpha/_redirects", "alpha/_worker.js",
    "alpha/index.html.gz", "alpha/guide/index.html.br",
])
def test_a_per_project_routing_artifact_fails(assembly, rel):
    _write(str(assembly / "site" / rel.replace("/", os.sep)), "leaked")
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("routing-artifacts")]
    assert any(rel in m for m in messages)


def test_the_sites_own_routing_files_are_not_a_defect(assembly):
    assert os.path.isfile(str(assembly / "site" / "_headers"))
    assert os.path.isfile(str(assembly / "site" / "_worker.js"))
    assert _verify(assembly).failures_of("routing-artifacts") == []


# -- cross-project links -------------------------------------------------------


def test_the_link_registry_is_built_from_the_emitted_pages(assembly):
    tree = read_tree(str(assembly), CANONICAL_BASE)
    registry = extract_link_registry(tree)
    assert registry["alpha/guide/index.html"] == ["beta/"]


def test_a_link_inside_one_project_is_not_a_cross_project_link(assembly):
    tree = read_tree(str(assembly), CANONICAL_BASE)
    registry = extract_link_registry(tree)
    # alpha/index.html links to alpha/guide/ -- the same project.
    assert "alpha/index.html" not in registry


def test_a_cross_project_link_to_a_page_nobody_publishes_fails(assembly):
    _write(str(assembly / "site" / "beta" / "ghost" / "index.html"),
           _page("Ghost", f"{CANONICAL_BASE}/beta/ghost/", version="2.0.0"))
    _write(str(assembly / "site" / "alpha" / "guide" / "index.html"),
           _page("Alpha Guide", f"{CANONICAL_BASE}/alpha/guide/",
                 body='  <a href="../../beta/ghost/">Ghost</a>',
                 version="1.0.0"))
    report = _verify(assembly)
    messages = [str(f) for f in report.failures_of("cross-project-links")]
    assert any("beta/ghost/" in m for m in messages)


def test_a_cross_project_link_to_a_published_post_resolves(assembly):
    _write(str(assembly / "site" / "beta" / "index.html"),
           _page("Beta", f"{CANONICAL_BASE}/beta/",
                 body='  <a href="../alpha/posts/hello/">Hello</a>',
                 version="2.0.0"))
    report = _verify(assembly)
    assert report.failures_of("cross-project-links") == []
