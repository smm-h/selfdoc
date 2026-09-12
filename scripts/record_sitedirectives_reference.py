#!/usr/bin/env python3
"""Record selfblog.sitedirectives's output as reference files for the Go port.

The Go ``internal/blog/sitedirectives`` package is a byte-for-byte port of
``selfblog/sitedirectives.py``.  Its tests assert equality against the files
this script writes, so the reference is the Python's real output rather than a
transcription of it.

Usage::

    scripts/record_sitedirectives_reference.py

Every case is deterministic: no clock, no filesystem, no process state.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

OUT_DIR = os.path.join(
    REPO, "internal", "blog", "sitedirectives", "testdata",
)

CANONICAL_BASE = "https://docs.example.com"


def _manifest(slug, name, version, posts=()):
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
        "posts": list(posts),
        "last_gen": "2024-01-01T00:00:00+00:00",
    }


def _post(slug, title, date):
    return {"slug": slug, "title": title, "date": date,
            "path": f"blog/{slug}.md", "tags": []}


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
  repo = "https://github.com/someone/outside"
"""


def main():
    from selfblog.listing import parse_listing
    from selfblog.sitedirectives import (
        SiteContext,
        refresh_regions,
        render_region,
    )

    os.makedirs(OUT_DIR, exist_ok=True)
    cases = {}

    # One post, a page one level down, and values that need escaping in
    # every position a highlight interpolates one.
    cases["region_blog_highlights_escapes.html"] = render_region(
        "blog-highlights", {"limit": "1"},
        SiteContext(
            manifests=[_manifest("alpha", "Alpha & Co", "1.0.0", posts=[
                _post("hello", 'A "quoted" <title>', "2024-06-01"),
            ])],
            site_hop="../",
        ),
    )

    # The newest three posts across two projects, newest first.
    cases["region_blog_highlights_limit.html"] = render_region(
        "blog-highlights", {"limit": "3"},
        SiteContext(
            manifests=[
                _manifest("alpha", "Alpha", "1.0.0", posts=[
                    _post("older", "Older", "2024-01-01"),
                    _post("newest", "Newest", "2024-09-01"),
                    _post("oldest", "Oldest", "2023-01-01"),
                ]),
                _manifest("beta", "Beta", "2.0.0", posts=[
                    _post("middle", "Middle", "2024-05-01"),
                ]),
            ],
            site_hop="",
        ),
    )

    # A site with no posts at all.
    cases["region_blog_highlights_empty.html"] = render_region(
        "blog-highlights", {"limit": "3"},
        SiteContext(manifests=[_manifest("alpha", "Alpha", "1.0.0")],
                    site_hop=""),
    )

    listing = parse_listing(LISTING_TOML)
    cards_context = SiteContext(
        manifests=[_manifest("alpha", "Alpha", "1.0.0")],
        site_hop="",
        listing=listing,
        home_slug="home",
    )

    # The curated cards: one served project, one external entry.
    cases["region_projects_cards.html"] = render_region(
        "projects-cards", {}, cards_context,
    )

    # The same cards addressed from a page one level down.
    cases["region_projects_cards_hop.html"] = render_region(
        "projects-cards", {},
        SiteContext(
            manifests=cards_context.manifests, site_hop="../",
            listing=listing, home_slug="home",
        ),
    )

    # A markdown converter's paragraph wrapper, absorbed on re-render.
    cases["refreshed_paragraph.html"] = refresh_regions(
        '<p>\n  <selfblog-region data-directive="projects-cards">old'
        "</selfblog-region>\n</p>",
        cards_context,
    )

    # A whole page: prose the author wrote around two regions.
    page = (
        "<h1>Me</h1>\n<p>Prose the author wrote.</p>\n"
        + render_region("projects-cards", {}, cards_context)
        + "\n"
        + render_region("blog-highlights", {"limit": "2"}, cards_context)
        + "\n"
    )
    cases["refreshed_page.html"] = refresh_regions(page, cards_context)

    for name, text in cases.items():
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {os.path.relpath(path, REPO)}")


if __name__ == "__main__":
    main()
