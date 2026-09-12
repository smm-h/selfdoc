#!/usr/bin/env python3
"""Record selfblog.shared's output as reference files for the Go port.

The Go ``internal/blog/shared`` package is a byte-for-byte port of
``selfblog/shared.py``.  Its tests assert equality against the files this
script writes, so the reference is the Python's real output rather than a
transcription of it.

Usage::

    scripts/record_blog_shared_reference.py

Every case is deterministic: no clock, no filesystem, no process state.
"""

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

OUT_DIR = os.path.join(REPO, "internal", "blog", "shared", "testdata")

CANONICAL_BASE = "https://docs.example.com"


def _manifest(name, slug, version, description="", pages=None, posts=None,
              theme=None):
    manifest = {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "version": version,
        "description": description,
        "language": "python",
        "base_url": f"https://example.com/{slug}",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "pages": pages or [],
        "posts": posts or [],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }
    if theme is not None:
        manifest["theme"] = theme
    return manifest


def _post(slug, title="Post", date="2024-06-01"):
    return {"slug": slug, "title": title, "date": date,
            "path": f"blog/{slug}.md", "tags": []}


ROSTER = [
    _manifest("Alpha", "alpha", "1.0.0", "Does the alpha thing.",
              pages=[{"path": "index.md", "title": "Home"},
                     {"path": "guide.md", "title": "Guide"},
                     {"path": "api/reference.md", "title": "API"}],
              posts=[_post("hello", "Hello", "2024-06-01")]),
    _manifest("Zebra", "zebra", "0.0.0", "Does the zebra thing.",
              pages=[{"path": "index.md", "title": "Home"}],
              posts=[_post("later", "Later", "2025-02-03")]),
    _manifest("Home", "home", "0.1.0", "The front page.\nSecond line.",
              pages=[{"path": "index.md", "title": "Home"},
                     {"path": "cv.md", "title": "CV"}]),
]

MIXED_CASE = [
    _manifest("charlie", "charlie", "1.0.0", "C."),
    _manifest("Alpha", "alpha", "2.0.0", "A."),
    _manifest("bravo", "bravo", "3.0.0", "B."),
]

ESCAPES = [
    _manifest("<script>alert(1)</script>", "xss", "1.0.0",
              "It's & \"quoted\" <b>"),
]


def _cases():
    from selfblog.shared import (
        generate_blog_index,
        generate_homepage,
        generate_llms_txt,
        generate_nav_json,
        generate_not_found_page,
        generate_robots_txt,
        generate_sitemap,
        generate_unified_feed,
        wrap_shared_page,
    )

    return {
        # -- wrap_shared_page -------------------------------------------
        "wrap_pagefind_root.html": lambda: wrap_shared_page(
            "Projects", '<section class="content"><h1>Welcome</h1></section>',
            css_url="_chrome/minimal-abcdef012345.css", search_prefix="",
        ),
        "wrap_pagefind_nested.html": lambda: wrap_shared_page(
            "Blog", "<p>x</p>", canonical_url=f"{CANONICAL_BASE}/blog/",
            css_url="../_chrome/minimal-abcdef012345.css",
            search_prefix="../",
        ),
        "wrap_escapes.html": lambda: wrap_shared_page(
            "It's <b>&</b> \"q\"", "<p>x</p>",
            canonical_url='https://x/"><script>',
            css_url='_chrome/x\'".css', search_prefix="",
        ),
        "wrap_framework.html": lambda: wrap_shared_page(
            "Framework", "<p>x</p>",
            css_url="../_chrome/tinymoon-abcdef012345/css/style.css",
            search_prefix="../",
        ),
        # -- generate_homepage (the name-ordered, no-home rendering) ----
        "homepage_name_ordered.html": lambda: generate_homepage(
            ROSTER, "../",
        ),
        "homepage_root_hop.html": lambda: generate_homepage(
            MIXED_CASE, "",
        ),
        "homepage_escapes.html": lambda: generate_homepage(
            ESCAPES, "../",
        ),
        "homepage_empty.html": lambda: generate_homepage([], "../"),
        "homepage_home_excluded.html": lambda: generate_homepage(
            ROSTER, "../", home_slug="home", listing=_listing(),
        ),
        # -- generate_blog_index ----------------------------------------
        "blog_index.html": lambda: generate_blog_index(ROSTER, "../"),
        "blog_index_root.html": lambda: generate_blog_index(ROSTER, ""),
        "blog_index_empty.html": lambda: generate_blog_index(
            MIXED_CASE, "../",
        ),
        # -- generate_nav_json ------------------------------------------
        "nav.json": lambda: generate_nav_json(ROSTER),
        "nav_home_excluded.json": lambda: generate_nav_json(
            ROSTER, "/articles/", home_slug="home",
        ),
        "nav_empty.json": lambda: generate_nav_json([]),
        # -- generate_unified_feed --------------------------------------
        "feed.xml": lambda: generate_unified_feed(ROSTER, CANONICAL_BASE),
        "feed_titled.xml": lambda: generate_unified_feed(
            ROSTER, CANONICAL_BASE, feed_title="My <Custom> Feed",
        ),
        # -- generate_sitemap -------------------------------------------
        "sitemap.xml": lambda: generate_sitemap(ROSTER, CANONICAL_BASE),
        "sitemap_home.xml": lambda: generate_sitemap(
            ROSTER, CANONICAL_BASE, home_slug="home",
        ),
        # -- generate_robots_txt ----------------------------------------
        "robots.txt": lambda: generate_robots_txt(CANONICAL_BASE),
        "robots_trailing_slash.txt": lambda: generate_robots_txt(
            CANONICAL_BASE + "/",
        ),
        # -- generate_llms_txt ------------------------------------------
        "llms.txt": lambda: generate_llms_txt(ROSTER, CANONICAL_BASE),
        "llms_home.txt": lambda: generate_llms_txt(
            ROSTER, CANONICAL_BASE + "/", home_slug="home",
        ),
        "llms_empty.txt": lambda: generate_llms_txt([], CANONICAL_BASE),
        # -- generate_not_found_page ------------------------------------
        "not_found.html": lambda: generate_not_found_page(
            css_url="_chrome/minimal-abcdef012345.css",
        ),
        "not_found_hopped.html": lambda: generate_not_found_page(
            css_url="../_chrome/minimal-abcdef012345.css", site_hop="../",
        ),
        "not_found_escaped_hop.html": lambda: generate_not_found_page(
            css_url="_chrome/x.css", site_hop='"><script>',
        ),
    }


def _listing():
    from selfblog.listing import parse_listing_sidecar

    sidecar = {
        "format_version": 1,
        "slug": "home",
        "categories": [{
            "name": "Frameworks",
            "projects": [
                {"slug": "alpha", "blurb": "Does the alpha thing.",
                 "url": "", "name": "", "repo": ""},
                {"slug": "zebra", "blurb": "Does the zebra thing.",
                 "url": "", "name": "", "repo": ""},
            ],
        }],
    }
    return parse_listing_sidecar(
        json.dumps(sidecar), source="home-listing.json",
    )


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, produce in sorted(_cases().items()):
        text = produce()
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"wrote {os.path.relpath(path, REPO)} ({len(text)} chars)")


if __name__ == "__main__":
    main()
