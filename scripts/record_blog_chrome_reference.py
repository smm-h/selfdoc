#!/usr/bin/env python3
"""Record selfblog.chrome's text constants as reference files for the Go port.

The Go ``internal/blog/chrome`` package is a port of ``selfblog/chrome.py``.
Its composed stylesheet cannot be compared byte for byte -- the port
highlights with chroma rather than pygments, which renames the token classes
by design -- but the assembly's own shared-page rules are the port's own text
and are asserted against the bytes this script writes.

Usage::

    scripts/record_blog_chrome_reference.py
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

OUT_DIR = os.path.join(REPO, "internal", "blog", "chrome", "testdata")


def main():
    from selfblog.chrome import _SHARED_PAGE_CSS

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "shared_page.css")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(_SHARED_PAGE_CSS)
    print(f"wrote {os.path.relpath(path, REPO)} ({len(_SHARED_PAGE_CSS)} chars)")


if __name__ == "__main__":
    main()
