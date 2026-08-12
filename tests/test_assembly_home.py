"""Tests for the home project: the one project served at the site root.

The assembly declares exactly one home project.  Its content root is the
site root -- no locale segment, no version segment, no archive -- and it is
the front page every other page is reached from.  Everything below is a
property of that role: the declaration, the graft, the addresses it may not
claim, the two renderings of its curated listing, and the two moments its
site-level directives resolve.
"""

import json
import os

import pytest

from selfblog.assembly import (
    HOME_DROPPED_ARTIFACTS,
    RosterEntry,
    apply_project_files,
    check_home_collisions,
    generate_shared_files,
    home_collisions,
    parse_roster,
    render_roster,
    split_build_output,
)
from selfblog.listing import (
    Listing,
    ListingCategory,
    ListingProject,
    parse_listing,
    render_listing_html,
)
from selfblog.sitedirectives import (
    SiteContext,
    build_home_project,
    refresh_regions,
    region_names,
    render_region,
)
from selfblog.verify import verify_assembly

CANONICAL_BASE = "https://docs.example.com"


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _page(title, address, body=""):
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        f"  <title>{title}</title>\n"
        f'  <link rel="canonical" href="{CANONICAL_BASE}/{address}">\n'
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def _manifest(slug, name, version, pages=None, posts=()):
    return {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "version": version,
        "description": f"{name} docs",
        "language": "python",
        "base_url": f"{CANONICAL_BASE}/{slug}",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "pages": pages if pages is not None else [
            {"path": "index.md", "title": "Home"},
        ],
        "posts": list(posts),
        "last_gen": "2024-01-01T00:00:00+00:00",
    }


LISTING_TOML = """\
[[category]]
name = "Frameworks"

  [[category.project]]
  slug = "alpha"
  blurb = "Does the alpha thing."

[[category]]
name = "Elsewhere"

  [[category.project]]
  slug = "outside"
  name = "Outside"
  blurb = "Lives somewhere else."
  url = "https://example.org/outside"
"""


# -- the declaration -----------------------------------------------------------


def test_a_roster_declares_exactly_one_home():
    roster = parse_roster(
        'home = "home"\n'
        '[[project]]\nslug = "home"\nrepo = "o/home"\n'
        '[[project]]\nslug = "alpha"\nrepo = "o/alpha"\n'
    )
    assert roster.home == "home"
    assert sorted(roster) == ["alpha", "home"]


def test_a_roster_with_no_home_is_refused():
    with pytest.raises(RuntimeError, match="declares no home project"):
        parse_roster('[[project]]\nslug = "alpha"\nrepo = "o/alpha"\n')


def test_an_empty_home_is_refused():
    with pytest.raises(RuntimeError, match="declares no home project"):
        parse_roster(
            'home = "  "\n[[project]]\nslug = "alpha"\nrepo = "o/alpha"\n'
        )


def test_a_home_that_is_not_a_declared_project_is_refused():
    with pytest.raises(RuntimeError, match="no \\[\\[project\\]\\] block declares it"):
        parse_roster(
            'home = "ghost"\n[[project]]\nslug = "alpha"\nrepo = "o/alpha"\n'
        )


def test_the_rendered_roster_carries_the_home_key():
    text = render_roster([RosterEntry("home", "o/home")], home="home")
    assert 'home = "home"' in text
    assert parse_roster(text).home == "home"


# -- the graft -----------------------------------------------------------------


def test_the_home_projects_pages_land_at_the_site_root():
    produced = split_build_output(
        ["index.html", "cv/index.html", "assets/pic.jpg"], "home", home=True,
    )
    assert produced == {
        "index.html": "index.html",
        "cv/index.html": "cv/index.html",
        "assets/pic.jpg": "assets/pic.jpg",
    }


def test_another_projects_pages_still_land_under_its_slug():
    produced = split_build_output(["index.html"], "alpha")
    assert produced == {"index.html": "alpha/index.html"}


def test_the_home_projects_posts_are_still_site_level():
    produced = split_build_output(
        ["blog/hello/index.html", "blog/index.html"], "home", home=True,
    )
    assert produced == {"blog/hello/index.html": "blog/hello/index.html"}


def test_the_home_build_drops_the_artifacts_the_assembly_writes():
    """Its own build wrote a robots.txt for standalone hosting; the site has one."""
    produced = split_build_output(
        [*HOME_DROPPED_ARTIFACTS, "index.html", "index.html.gz"],
        "home", home=True,
    )
    assert produced == {"index.html": "index.html"}


def test_a_home_page_on_a_reserved_directory_is_refused():
    """A page called projects.md would claim the generated listing's address."""
    with pytest.raises(RuntimeError, match="projects/"):
        check_home_collisions(["index.html", "projects/index.html"], slug="home")


def test_every_reserved_directory_is_refused():
    found = dict(home_collisions([
        "blog/x/index.html", "projects/index.html", "v/1.0.0/index.html",
        "pagefind/pagefind.js", "cv/index.html",
    ]))
    assert set(found) == {
        "blog/x/index.html", "projects/index.html", "v/1.0.0/index.html",
        "pagefind/pagefind.js",
    }


def test_the_graft_refuses_a_colliding_home_build(tmp_path):
    source = tmp_path / "source"
    build = source / "docs" / "_build"
    _write(str(build / "index.html"), _page("Front", ""))
    _write(str(build / "projects" / "index.html"), _page("Projects", "projects/"))
    _write(str(source / ".selfdoc" / "manifest.json"),
           json.dumps(_manifest("home", "Home", "0.1.0")))
    with pytest.raises(RuntimeError, match="addresses the assembly owns"):
        apply_project_files(
            str(tmp_path / "assembly"), str(source), "home", "full", home=True,
        )


def test_the_graft_copies_the_curated_listing_in(tmp_path):
    source = tmp_path / "source"
    build = source / "docs" / "_build"
    _write(str(build / "index.html"), _page("Front", ""))
    _write(str(source / "docs" / "projects.toml"), LISTING_TOML)
    _write(str(source / ".selfdoc" / "manifest.json"),
           json.dumps(_manifest("home", "Home", "0.1.0")))
    assembly = tmp_path / "assembly"

    apply_project_files(str(assembly), str(source), "home", "full", home=True)

    sidecar = assembly / "manifests" / "home-listing.json"
    assert sidecar.is_file()
    assert json.loads(sidecar.read_text())["categories"][0]["name"] == "Frameworks"
    assert (assembly / "site" / "index.html").is_file()

    # The claims are recorded at the addresses the pages actually landed at,
    # which for the home project means no slug prefix.
    record = json.loads(
        (assembly / "manifests" / "home-files.json").read_text()
    )
    assert record["owners"]["release"] == ["index.html"]


# -- the assembled tree --------------------------------------------------------


@pytest.fixture()
def home_assembly(tmp_path):
    """An assembly whose home project has deployed its front page and CV."""
    root = tmp_path / "assembly"
    site = root / "site"
    manifests = root / "manifests"

    _write(str(root / "roster.toml"), render_roster([
        RosterEntry("home", "owner/home"),
        RosterEntry("alpha", "owner/alpha"),
    ], home="home"))
    _write(str(root / "projects.json"), json.dumps({
        "home": {"repo": "owner/home", "ref": "v0.1.0", "version": "0.1.0"},
        "alpha": {"repo": "owner/alpha", "ref": "v1.0.0", "version": "1.0.0"},
    }))

    _write(str(manifests / "alpha.json"), json.dumps(_manifest(
        "alpha", "Alpha", "1.0.0",
        posts=[{"slug": "hello", "title": "Hello", "date": "2024-06-01",
                "path": "blog/hello.md", "tags": []}],
    )))
    _write(str(manifests / "alpha-files.json"), json.dumps({
        "schema_version": 2, "slug": "alpha",
        "owners": {"release": ["alpha/index.html", "blog/hello/index.html"]},
    }))
    _write(str(manifests / "home.json"), json.dumps(_manifest(
        "home", "Home", "0.1.0",
        pages=[{"path": "index.md", "title": "Front page"},
               {"path": "cv.md", "title": "CV"}],
    )))
    _write(str(manifests / "home-files.json"), json.dumps({
        "schema_version": 2, "slug": "home",
        "owners": {"release": ["index.html", "cv/index.html"]},
    }))
    _write(str(manifests / "home-listing.json"), json.dumps({
        "format_version": 1, "slug": "home",
        "categories": [{
            "name": "Frameworks",
            "projects": [{"slug": "alpha", "blurb": "Does the alpha thing.",
                          "url": "", "name": ""}],
        }],
    }))

    _write(str(site / "alpha" / "index.html"), _page("Alpha", "alpha/"))
    _write(str(site / "blog" / "hello" / "index.html"),
           _page("Hello", "blog/hello/"))
    _write(str(site / "cv" / "index.html"), _page("CV", "cv/"))
    _write(str(site / "index.html"), _page(
        "Front page", "",
        body=(
            "<p>Prose the author wrote.</p>\n"
            + render_region("projects-cards", {}, SiteContext(
                manifests=[_manifest("alpha", "Alpha", "0.9.0")],
                docs_base=CANONICAL_BASE,
                listing=Listing((ListingCategory("Frameworks", (
                    ListingProject("alpha", "Does the alpha thing."),
                )),)),
                home_slug="home",
            ))
        ),
    ))

    _write(str(site / "pagefind" / "pagefind-entry.json"), json.dumps({
        "version": "1.3.0",
        "languages": {"en": {"hash": "en_abc", "wasm": "en", "page_count": 4}},
    }))
    _write(str(site / "pagefind" / "fragment" / "en_abc.pf_fragment"), "f")
    return root


def _shared(root):
    return generate_shared_files(
        str(root / "site"), str(root / "manifests"), CANONICAL_BASE,
        docs_base=CANONICAL_BASE, home_slug="home",
    )


def test_the_home_pages_sit_beside_the_generated_pages(home_assembly):
    _shared(home_assembly)
    site = home_assembly / "site"
    assert (site / "index.html").is_file()
    assert (site / "cv" / "index.html").is_file()
    assert (site / "projects" / "index.html").is_file()
    assert (site / "blog" / "index.html").is_file()


def test_the_generated_listing_leaves_the_home_project_out(home_assembly):
    _shared(home_assembly)
    listing = (home_assembly / "site" / "projects" / "index.html").read_text()
    assert "Alpha" in listing
    assert ">Home<" not in listing


def test_nav_leaves_the_home_project_out(home_assembly):
    _shared(home_assembly)
    nav = json.loads((home_assembly / "site" / "nav.json").read_text())
    assert [p["slug"] for p in nav["projects"]] == ["alpha"]


def test_the_sitemap_addresses_home_pages_from_the_site_root(home_assembly):
    _shared(home_assembly)
    sitemap = (home_assembly / "site" / "sitemap.xml").read_text()
    assert f"<loc>{CANONICAL_BASE}/cv/</loc>" in sitemap
    assert f"{CANONICAL_BASE}/home/" not in sitemap


def test_a_deploy_of_another_project_refreshes_the_front_page(home_assembly):
    """The card's version badge is as current as alpha's last deploy."""
    before = (home_assembly / "site" / "index.html").read_text()
    assert "v0.9.0" in before

    _shared(home_assembly)

    after = (home_assembly / "site" / "index.html").read_text()
    assert "v1.0.0" in after
    assert "v0.9.0" not in after
    assert "Prose the author wrote." in after


def test_the_refresh_is_idempotent(home_assembly):
    _shared(home_assembly)
    once = (home_assembly / "site" / "index.html").read_text()
    _shared(home_assembly)
    assert (home_assembly / "site" / "index.html").read_text() == once


def test_the_assembled_tree_verifies_clean(home_assembly):
    _shared(home_assembly)
    report = verify_assembly(str(home_assembly), canonical_base=CANONICAL_BASE)
    assert report.ok, report.error_text()


def test_a_home_subtree_residue_is_named(home_assembly):
    """A site/<home>/ directory is a second, stale copy of the front page."""
    _shared(home_assembly)
    _write(str(home_assembly / "site" / "home" / "index.html"),
           _page("Stale front page", "home/"))
    report = verify_assembly(str(home_assembly), canonical_base=CANONICAL_BASE)
    messages = [str(f) for f in report.failures_of("home-project")]
    assert any("site/home" in m and "residue" in m for m in messages)


def test_a_home_directory_that_shadows_a_project_is_named(home_assembly):
    _shared(home_assembly)
    record = home_assembly / "manifests" / "home-files.json"
    data = json.loads(record.read_text())
    data["owners"]["release"].append("alpha/index.html")
    record.write_text(json.dumps(data))
    report = verify_assembly(str(home_assembly), canonical_base=CANONICAL_BASE)
    messages = [str(f) for f in report.failures_of("home-project")]
    assert any("alpha" in m for m in messages)


def test_an_empty_region_on_a_published_page_is_named(home_assembly):
    _shared(home_assembly)
    page = home_assembly / "site" / "index.html"
    page.write_text(_page(
        "Front page", "",
        body='<selfblog-region data-directive="projects-cards">'
             "</selfblog-region>",
    ))
    report = verify_assembly(str(home_assembly), canonical_base=CANONICAL_BASE)
    messages = [str(f) for f in report.failures_of("home-project")]
    assert any("empty site-level region" in m for m in messages)


def test_an_unclosed_region_on_a_published_page_is_named(home_assembly):
    _shared(home_assembly)
    page = home_assembly / "site" / "index.html"
    page.write_text(_page(
        "Front page", "",
        body='<selfblog-region data-directive="projects-cards">',
    ))
    report = verify_assembly(str(home_assembly), canonical_base=CANONICAL_BASE)
    messages = [str(f) for f in report.failures_of("home-project")]
    assert any("never close" in m for m in messages)


# -- the curated listing -------------------------------------------------------


def test_a_listing_parses_categories_in_declared_order():
    listing = parse_listing(LISTING_TOML)
    assert [c.name for c in listing.categories] == ["Frameworks", "Elsewhere"]
    assert listing.slugs == ["alpha", "outside"]
    assert listing.categories[1].projects[0].external


def test_an_unknown_key_on_a_listed_project_is_a_hard_error():
    with pytest.raises(RuntimeError, match="unknown key"):
        parse_listing(
            '[[category]]\nname = "A"\n'
            '[[category.project]]\nslug = "a"\nblurb = "b"\nnote = "typo"\n'
        )


def test_an_unknown_top_level_key_is_a_hard_error():
    with pytest.raises(RuntimeError, match="unknown top-level key"):
        parse_listing('projects = []\n')


def test_a_listed_project_needs_a_blurb():
    with pytest.raises(RuntimeError, match="non-empty 'blurb'"):
        parse_listing(
            '[[category]]\nname = "A"\n[[category.project]]\nslug = "a"\n'
        )


def test_an_external_entry_needs_a_name():
    with pytest.raises(RuntimeError, match="Declare 'name'"):
        parse_listing(
            '[[category]]\nname = "A"\n[[category.project]]\nslug = "a"\n'
            'blurb = "b"\nurl = "https://x/"\n'
        )


def test_a_served_entry_may_not_declare_a_name():
    """Its name comes from its manifest; two sources would drift apart."""
    with pytest.raises(RuntimeError, match="second source"):
        parse_listing(
            '[[category]]\nname = "A"\n[[category.project]]\nslug = "a"\n'
            'blurb = "b"\nname = "A Thing"\n'
        )


def test_a_duplicate_slug_across_categories_is_a_hard_error():
    with pytest.raises(RuntimeError, match="repeats the slug"):
        parse_listing(
            '[[category]]\nname = "A"\n'
            '[[category.project]]\nslug = "a"\nblurb = "b"\n'
            '[[category]]\nname = "B"\n'
            '[[category.project]]\nslug = "a"\nblurb = "b"\n'
        )


def test_an_empty_category_is_a_hard_error():
    with pytest.raises(RuntimeError, match="declares no \\[\\[category.project\\]\\]"):
        parse_listing('[[category]]\nname = "A"\n')


def test_a_listed_slug_with_no_manifest_is_a_hard_error():
    listing = parse_listing(LISTING_TOML)
    with pytest.raises(RuntimeError, match="alpha"):
        render_listing_html(listing, [], CANONICAL_BASE, home_slug="home")


def test_the_home_project_may_not_list_itself():
    listing = parse_listing(
        '[[category]]\nname = "A"\n'
        '[[category.project]]\nslug = "home"\nblurb = "me"\n'
    )
    with pytest.raises(RuntimeError, match="which is the home project"):
        render_listing_html(
            listing, [_manifest("home", "Home", "0.1.0")], CANONICAL_BASE,
            home_slug="home",
        )


def test_a_roster_project_the_listing_omits_is_legal():
    """Curation is selection: an unlisted project simply has no card."""
    listing = parse_listing(
        '[[category]]\nname = "A"\n'
        '[[category.project]]\nslug = "alpha"\nblurb = "b"\n'
    )
    html = render_listing_html(
        listing,
        [_manifest("alpha", "Alpha", "1.0.0"),
         _manifest("beta", "Beta", "2.0.0")],
        CANONICAL_BASE, home_slug="home",
    )
    assert "Alpha" in html
    assert "Beta" not in html


def test_an_external_entry_links_out_and_carries_no_version():
    listing = parse_listing(LISTING_TOML)
    html = render_listing_html(
        listing, [_manifest("alpha", "Alpha", "1.0.0")], CANONICAL_BASE,
        home_slug="home",
    )
    assert 'href="https://example.org/outside"' in html
    assert "Outside" in html


def test_both_renderings_come_from_the_one_file(home_assembly):
    """The /projects/ page and the front page's cards say the same thing."""
    _shared(home_assembly)
    listing_page = (home_assembly / "site" / "projects" / "index.html").read_text()
    front_page = (home_assembly / "site" / "index.html").read_text()
    for fragment in ("Frameworks", "Alpha", "Does the alpha thing.", "v1.0.0"):
        assert fragment in listing_page
        assert fragment in front_page


# -- the site-level directives -------------------------------------------------


def test_a_region_survives_a_re_render_with_its_attributes():
    context = SiteContext(
        manifests=[_manifest("alpha", "Alpha", "1.0.0", posts=[
            {"slug": "hello", "title": "Hello", "date": "2024-06-01"},
        ])],
        docs_base=CANONICAL_BASE,
    )
    once = render_region("blog-highlights", {"limit": "1"}, context)
    assert region_names(once) == ["blog-highlights"]
    twice = refresh_regions(once, context)
    assert region_names(twice) == ["blog-highlights"]
    assert "Hello" in twice


def test_blog_highlights_honours_its_limit():
    context = SiteContext(
        manifests=[_manifest("alpha", "Alpha", "1.0.0", posts=[
            {"slug": "one", "title": "One", "date": "2024-06-01"},
            {"slug": "two", "title": "Two", "date": "2024-07-01"},
        ])],
        docs_base=CANONICAL_BASE,
    )
    html = render_region("blog-highlights", {"limit": "1"}, context)
    assert "Two" in html
    assert ">One<" not in html


def test_blog_highlights_requires_a_limit():
    context = SiteContext(manifests=[], docs_base=CANONICAL_BASE)
    with pytest.raises(RuntimeError, match="requires limit"):
        render_region("blog-highlights", {}, context)


def test_projects_cards_without_a_listing_is_a_hard_error():
    context = SiteContext(manifests=[], docs_base=CANONICAL_BASE)
    with pytest.raises(RuntimeError, match="docs/projects.toml"):
        render_region("projects-cards", {}, context)


def test_a_region_that_never_closes_is_a_hard_error():
    context = SiteContext(manifests=[], docs_base=CANONICAL_BASE)
    with pytest.raises(RuntimeError, match="open and never close"):
        refresh_regions(
            '<selfblog-region data-directive="projects-cards">', context,
            source="page",
        )


def test_a_paragraph_wrapper_around_a_region_is_absorbed():
    """Markdown wraps the emitted region in <p>; a block element is not staying there."""
    context = SiteContext(
        manifests=[_manifest("alpha", "Alpha", "1.0.0")],
        docs_base=CANONICAL_BASE,
        listing=Listing((ListingCategory("A", (
            ListingProject("alpha", "b"),
        )),)),
        home_slug="home",
    )
    wrapped = (
        '<p><selfblog-region data-directive="projects-cards">old'
        "</selfblog-region></p>"
    )
    refreshed = refresh_regions(wrapped, context)
    assert not refreshed.startswith("<p>")
    assert refreshed.endswith("</selfblog-region>")


def test_a_page_with_no_region_is_returned_unchanged():
    context = SiteContext(manifests=[], docs_base=CANONICAL_BASE)
    page = "<html><body><p>nothing to do</p></body></html>"
    assert refresh_regions(page, context) == page


# -- what a build without the assembly's data does -----------------------------


def test_a_home_build_without_the_manifests_refuses(tmp_path):
    config = {"versions": [{"version": "0.1.0"}],
              "locales": [{"code": "en", "label": "English", "default": True}]}
    with pytest.raises(RuntimeError, match="--site-manifests is required"):
        build_home_project(
            str(tmp_path), config, site_manifests="", docs_base=CANONICAL_BASE,
        )


def test_a_home_build_without_a_docs_base_refuses(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    config = {"versions": [{"version": "0.1.0"}],
              "locales": [{"code": "en", "label": "English", "default": True}]}
    with pytest.raises(RuntimeError, match="--docs-base is required"):
        build_home_project(
            str(tmp_path), config, site_manifests=str(manifests), docs_base="",
        )


def test_a_home_build_resolves_the_directives_into_sentinel_regions(tmp_path):
    """End to end: the marker in the source becomes a region in the output."""
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "alpha.json").write_text(json.dumps(_manifest(
        "alpha", "Alpha", "1.0.0",
        posts=[{"slug": "hello", "title": "Hello", "date": "2024-06-01"}],
    )))

    project = tmp_path / "project"
    docs = project / "docs"
    docs.mkdir(parents=True)
    (docs / "projects.toml").write_text(
        '[[category]]\nname = "Frameworks"\n'
        '[[category.project]]\nslug = "alpha"\nblurb = "Does the alpha thing."\n'
    )
    (docs / "index.md").write_text(
        "---\ntitle: Front page\n---\n\n"
        "# Me\n\nProse the author wrote.\n\n"
        ":-: projects-cards\n\n"
        ':-: blog-highlights limit="3"\n'
    )
    config = {
        "name": "Home",
        "base_url": CANONICAL_BASE,
        "author": {"name": "Test Author", "url": "https://author.example"},
        "search_engine": "pagefind",
        "docs": "docs/",
        "output": "docs/_build/",
        "version": "0.1.0",
        "versions": [{"version": "0.1.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "topology": {"slug": "home"},
    }

    build_home_project(
        str(project), config, site_manifests=str(manifests),
        docs_base=CANONICAL_BASE,
    )

    page = (project / "docs" / "_build" / "index.html").read_text()
    assert "Prose the author wrote." in page
    assert region_names(page) == ["blog-highlights", "projects-cards"] or \
        region_names(page) == ["projects-cards", "blog-highlights"]
    assert "Does the alpha thing." in page
    assert "v1.0.0" in page
    assert "Hello" in page


def test_a_plain_selfdoc_build_cannot_resolve_a_site_level_directive():
    """selfdoc's catalogue has no site-level directive, so it stops at the marker."""
    from selfdoc_core.catalog import ALL_BUILTIN_DIRECTIVES
    from selfdoc_core.directives import DirectiveError, parse_directives

    assert "projects-cards" not in ALL_BUILTIN_DIRECTIVES
    assert "blog-highlights" not in ALL_BUILTIN_DIRECTIVES
    with pytest.raises(DirectiveError, match="Unknown directive 'projects-cards'"):
        parse_directives(":-: projects-cards\n", valid_names=ALL_BUILTIN_DIRECTIVES)
