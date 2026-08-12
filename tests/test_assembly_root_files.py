"""The machine-readable files at the assembly's site root.

``robots.txt``, ``llms.txt``, ``sitemap.xml`` and ``404.html`` are the
site's, not any project's.  Each constituent build writes its own copy of
all four at its own output root, where they end up buried under
``<slug>/`` and are read by nobody; the ones that answer are generated
here, once, for the whole site.

What each has to be true of:

* **404.html** is a real not-found page.  On Cloudflare Pages the file at
  that name is what an address matching no asset gets, with a 404 status,
  so its body has to differ from the front page's -- otherwise an address
  that does not exist renders the home page and reads as one that does.
* **robots.txt** names the sitemap absolutely, and carries the same
  crawler policy the per-project template declares, read from the same
  place so the two cannot drift.
* **llms.txt** composes the per-project ones *by reference*: a link to
  each project's own file, never a copy of its contents.
* **sitemap.xml** is absolute in every ``<loc>`` -- the protocol has no
  relative form -- and sits at the root, where robots.txt says it is.
"""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET

import pytest

from selfblog.assembly import generate_shared_files
from selfblog.shared import (
    ROBOTS_AGENTS,
    generate_llms_txt,
    generate_not_found_page,
    generate_robots_txt,
    generate_sitemap,
)

CANONICAL_BASE = "https://docs.example.com"


def _manifest(slug, name, description="", pages=(), posts=()):
    return {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "version": "1.0.0",
        "description": description,
        "language": "python",
        "base_url": f"{CANONICAL_BASE}/{slug}",
        "pages": list(pages) or [{"path": "index.md", "title": "Home"}],
        "posts": list(posts),
        "last_gen": "2024-01-01T00:00:00+00:00",
    }


MANIFESTS = [
    _manifest("alpha", "Alpha", "Does the alpha thing.",
              pages=[{"path": "index.md", "title": "Home"},
                     {"path": "guide.md", "title": "Guide"}],
              posts=[{"slug": "hello", "title": "Hello", "date": "2024-06-01",
                      "path": "blog/hello.md", "tags": []}]),
    _manifest("beta", "Beta", "Does the beta thing."),
    _manifest("home", "Home", "The front page."),
]


@pytest.fixture()
def generated(tmp_path):
    """The shared files as a deploy writes them, with a home project."""
    site = tmp_path / "site"
    manifests = tmp_path / "manifests"
    os.makedirs(site)
    os.makedirs(manifests)
    for m in MANIFESTS:
        with open(manifests / f"{m['slug']}.json", "w", encoding="utf-8") as f:
            json.dump(m, f)
    generate_shared_files(
        str(site), str(manifests), CANONICAL_BASE,
        docs_base=CANONICAL_BASE, home_slug="home",
    )
    return site


def _read(site, name):
    with open(os.path.join(str(site), name), encoding="utf-8") as f:
        return f.read()


# -- the root 404 --------------------------------------------------------------


def test_the_root_404_is_written(generated):
    assert os.path.isfile(os.path.join(str(generated), "404.html"))


def test_the_root_404_is_a_whole_page_from_the_shared_wrapper(generated):
    html = _read(generated, "404.html")
    assert html.startswith("<!DOCTYPE html>")
    assert "<title>Page not found</title>" in html
    assert f'<link rel="canonical" href="{CANONICAL_BASE}/404.html">' in html


def test_the_root_404_says_the_page_is_not_there(generated):
    html = _read(generated, "404.html")
    assert "<h1>Page not found</h1>" in html


def test_the_root_404_links_home_projects_and_blog(generated):
    html = _read(generated, "404.html")
    assert f'href="{CANONICAL_BASE}/"' in html
    assert f'href="{CANONICAL_BASE}/projects/"' in html
    assert f'href="{CANONICAL_BASE}/blog/"' in html


def test_the_root_404_is_not_the_front_page():
    """A soft 404 -- the home page under an unknown address -- is the defect."""
    not_found = generate_not_found_page(CANONICAL_BASE)
    listing = _read_projects_page()
    assert "Page not found" not in listing
    assert "<h1>Projects</h1>" not in not_found


def _read_projects_page():
    from selfblog.shared import generate_homepage, wrap_shared_page

    return wrap_shared_page(
        "Projects", generate_homepage(MANIFESTS, CANONICAL_BASE, home_slug="home"),
        canonical_url=f"{CANONICAL_BASE}/projects/",
    )


def test_the_root_404_escapes_its_base():
    html = generate_not_found_page('https://x/"><script>')
    assert "<script>" not in html.split("<body>")[1]


# -- robots.txt ----------------------------------------------------------------


def test_robots_names_the_root_sitemap_absolutely(generated):
    assert f"Sitemap: {CANONICAL_BASE}/sitemap.xml" in _read(generated, "robots.txt")


def test_the_sitemap_robots_names_is_the_one_that_exists(generated):
    assert os.path.isfile(os.path.join(str(generated), "sitemap.xml"))


def test_robots_carries_the_per_project_crawler_policy():
    """One declaration of the policy, read by both generators.

    The per-project template and the site-wide file name the same crawlers
    because they read the same tuple; a disallow added to one cannot leave
    the other allowing it.
    """
    from selfdoc_core.robots import ROBOTS_AGENTS as CORE_AGENTS

    assert ROBOTS_AGENTS is CORE_AGENTS
    robots = generate_robots_txt(CANONICAL_BASE)
    for agent in CORE_AGENTS:
        assert f"User-agent: {agent}\nAllow: /" in robots


def test_robots_names_the_ai_crawlers_explicitly():
    """The allowlist is deliberate: naming each one is the whole point."""
    robots = generate_robots_txt(CANONICAL_BASE)
    for agent in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended",
                  "OAI-SearchBot", "ChatGPT-User", "Googlebot"):
        assert f"User-agent: {agent}" in robots


def test_robots_tolerates_a_trailing_slash_on_the_base():
    assert generate_robots_txt(CANONICAL_BASE + "/") == \
        generate_robots_txt(CANONICAL_BASE)


# -- llms.txt ------------------------------------------------------------------


def test_llms_txt_is_written_at_the_site_root(generated):
    assert os.path.isfile(os.path.join(str(generated), "llms.txt"))


def test_llms_txt_links_each_project_own_file(generated):
    llms = _read(generated, "llms.txt")
    assert f"[Alpha]({CANONICAL_BASE}/alpha/llms.txt)" in llms
    assert f"[Beta]({CANONICAL_BASE}/beta/llms.txt)" in llms


def test_llms_txt_carries_each_project_description(generated):
    llms = _read(generated, "llms.txt")
    assert "Does the alpha thing." in llms
    assert "Does the beta thing." in llms


def test_llms_txt_leaves_out_the_home_project(generated):
    """The home project is the root the file is served from, not an entry."""
    assert "/home/llms.txt" not in _read(generated, "llms.txt")


def test_llms_txt_links_the_blog(generated):
    assert f"[Blog]({CANONICAL_BASE}/blog/)" in _read(generated, "llms.txt")


def test_llms_txt_never_inlines_a_project_page_list(generated):
    """Composition is by reference: an inlined copy goes stale on every deploy.

    The per-project file lists that project's pages; if any of those page
    titles appeared here, the site-wide file would be a second rendering
    of a document its owner republishes without telling this one.
    """
    llms = _read(generated, "llms.txt")
    assert f"{CANONICAL_BASE}/alpha/guide/" not in llms
    assert "Guide" not in llms


def test_llms_txt_is_ordered_by_name():
    llms = generate_llms_txt([
        _manifest("zeta", "Zeta"), _manifest("alpha", "Alpha"),
    ], CANONICAL_BASE)
    assert llms.index("[Alpha]") < llms.index("[Zeta]")


def test_llms_txt_says_so_when_nothing_is_published():
    llms = generate_llms_txt([], CANONICAL_BASE)
    assert "No projects are published yet." in llms


def test_llms_txt_survives_a_project_with_no_description():
    llms = generate_llms_txt([_manifest("alpha", "Alpha")], CANONICAL_BASE)
    assert f"- [Alpha]({CANONICAL_BASE}/alpha/llms.txt)" in llms


def test_llms_txt_takes_only_the_first_line_of_a_description():
    llms = generate_llms_txt(
        [_manifest("alpha", "Alpha", "One line.\nAnd another.")],
        CANONICAL_BASE,
    )
    assert "One line." in llms
    assert "And another." not in llms


# -- the sitemap ---------------------------------------------------------------


def _locs(xml_text):
    root = ET.fromstring(xml_text)
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    return [el.text for el in root.iter(f"{ns}loc")]


def test_every_sitemap_loc_is_absolute_under_the_canonical_base(generated):
    locs = _locs(_read(generated, "sitemap.xml"))
    assert locs
    for loc in locs:
        assert loc.startswith(CANONICAL_BASE + "/"), loc


def test_the_sitemap_carries_pages_and_posts(generated):
    locs = set(_locs(_read(generated, "sitemap.xml")))
    assert f"{CANONICAL_BASE}/alpha/guide/" in locs
    assert f"{CANONICAL_BASE}/blog/hello/" in locs
    # The home project's pages are addressed from the site root.
    assert f"{CANONICAL_BASE}/" in locs


def test_the_sitemap_refuses_a_relative_base():
    """A root-relative base produces entries every crawler discards."""
    with pytest.raises(ValueError, match="absolute base URL"):
        generate_sitemap(MANIFESTS, "")
    with pytest.raises(ValueError, match="absolute base URL"):
        generate_sitemap(MANIFESTS, "/docs")


def test_the_sitemap_stays_absolute_when_docs_base_is_relative(tmp_path):
    """docs_base may be root-relative for in-page links; the sitemap may not.

    The generator takes the canonical base for the sitemap regardless, so
    a deploy that passes a relative --docs-base still emits a usable one.
    """
    site = tmp_path / "site"
    manifests = tmp_path / "manifests"
    os.makedirs(site)
    os.makedirs(manifests)
    for m in MANIFESTS:
        with open(manifests / f"{m['slug']}.json", "w", encoding="utf-8") as f:
            json.dump(m, f)
    generate_shared_files(
        str(site), str(manifests), CANONICAL_BASE,
        docs_base="", home_slug="home",
    )
    for loc in _locs(_read(site, "sitemap.xml")):
        assert loc.startswith(CANONICAL_BASE + "/"), loc
