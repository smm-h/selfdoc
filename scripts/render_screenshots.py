#!/usr/bin/env python3
"""Build the rendered-reality fixture site and photograph its pages.

Same tree the browser suite asserts against -- ``build_fixture_site`` plus
``build_standalone_project``, served by the production preview server -- so
a screenshot is a picture of what the suite measured, not of a second
rendering path.

Usage::

    uv run python scripts/render_screenshots.py --out shots/ \\
        --theme tinymoon --page home --page docs

``--theme`` and ``--page`` repeat; both default to everything.  Page names
are the labels the browser suite uses.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))

PAGES = {
    "home": ("assembly", "/"),
    "docs": ("assembly", "/alpha/"),
    "docs-tables": ("assembly", "/alpha/tables/"),
    "docs-glossary": ("assembly", "/alpha/glossary/"),
    "post": ("assembly", "/blog/the-first-post/"),
    "cv": ("assembly", "/cv/"),
    "standalone-archive": ("standalone", "/v/0.1.0/"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True,
                        help="directory the PNGs are written to")
    parser.add_argument("--theme", action="append", default=[],
                        help="theme to photograph (repeatable)")
    parser.add_argument("--page", action="append", default=[],
                        help="page label to photograph (repeatable)")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--full-page", action="store_true")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    from rendered_site import (
        build_fixture_site, build_standalone_project, serve,
    )
    from selfdoc_core.themes import list_themes

    themes = args.theme or list_themes()
    labels = args.page or list(PAGES)
    for label in labels:
        if label not in PAGES:
            parser.error(f"unknown page {label!r}; known: {', '.join(PAGES)}")

    os.makedirs(args.out, exist_ok=True)
    written = []
    with sync_playwright() as play:
        browser = play.chromium.launch()
        for theme in themes:
            root = tempfile.mkdtemp(prefix=f"shots-{theme}-")
            summary = build_fixture_site(root, theme)
            standalone_dir = build_standalone_project(root, theme)
            with serve(summary["site_dir"], theme) as assembly, \
                    serve(standalone_dir, theme) as standalone:
                sites = {"assembly": assembly, "standalone": standalone}
                context = browser.new_context(
                    viewport={"width": args.width, "height": args.height},
                )
                page = context.new_page()
                for label in labels:
                    where, path = PAGES[label]
                    page.goto(sites[where].url(path), wait_until="load")
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(300)
                    out = os.path.join(args.out, f"{theme}-{label}.png")
                    page.screenshot(path=out, full_page=args.full_page)
                    written.append(out)
                    print(out)
                context.close()
        browser.close()
    print(f"{len(written)} screenshot(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
