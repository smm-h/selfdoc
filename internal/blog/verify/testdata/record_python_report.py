"""Record the Python verifier's report text for the pinned failing tree.

The Go port asserts its own report is byte-identical to this recording, so the
tree built here has to be the tree ``newAssembly`` plus ``breakEverything``
builds in ``report_parity_test.go``: the same roster, the same manifests, the
same pages, the same shared-file generation, and the same defects injected in
the same order.

Run it against the pinned Python that has selfblog importable, from the
repository root:

    /home/m/.local/share/uv/tools/selfblog/bin/python \
        internal/blog/verify/testdata/record_python_report.py \
        > internal/blog/verify/testdata/failing-tree-report.txt

The recording, not this script, is what the Go test reads. The script is here
so a reader can see where the bytes came from and reproduce them; it goes away
with the rest of the Python.
"""

import json
import os
import re
import shutil
import sys
import tempfile

from selfblog.assembly import RosterEntry, generate_shared_files, render_roster
from selfblog.chrome import (
    DEFAULT_THEME,
    chrome_asset_rel,
    chrome_css,
    chrome_href,
)
from selfblog.verify import verify_assembly

CANONICAL_BASE = "https://docs.example.com"
HOME = "home"
ROSTER = [
    RosterEntry("home", "owner/home"),
    RosterEntry("alpha", "owner/alpha"),
    RosterEntry("beta", "owner/beta"),
]


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def chrome_ref(page_rel):
    return chrome_href(
        page_rel, chrome_asset_rel(DEFAULT_THEME, chrome_css(DEFAULT_THEME)),
    )


def page(title, canonical, body="", version="", css_href="style.css",
         no_css=False):
    version_attr = f' data-default-version="{version}"' if version else ""
    stylesheet = "" if no_css else (
        f'  <link rel="stylesheet" href="{css_href}">\n'
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        f"  <title>{title}</title>\n"
        f'  <link rel="canonical" href="{canonical}">\n'
        f"{stylesheet}"
        "</head>\n"
        "<body>\n"
        f'  <dialog class="search-dialog" data-search-base="./"'
        f"{version_attr}></dialog>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def manifest(slug, name, version, pages, posts=()):
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


def build(root):
    site = os.path.join(root, "site")
    manifests = os.path.join(root, "manifests")

    write(os.path.join(root, "roster.toml"), render_roster(ROSTER, home=HOME))
    write(os.path.join(root, "projects.json"), json.dumps({
        "home": {"repo": "owner/home", "ref": "v0.1.0", "version": "0.1.0"},
        "alpha": {"repo": "owner/alpha", "ref": "v1.0.0", "version": "1.0.0"},
        "beta": {"repo": "owner/beta", "ref": "v2.0.0", "version": "2.0.0"},
    }))

    write(os.path.join(manifests, "alpha.json"), json.dumps(manifest(
        "alpha", "Alpha", "1.0.0",
        pages=[{"path": "index.md", "title": "Home"},
               {"path": "guide.md", "title": "Guide"}],
        posts=[{"slug": "hello", "title": "Hello", "date": "2024-06-01",
                "path": "blog/hello.md", "tags": []}],
    )))
    write(os.path.join(manifests, "beta.json"), json.dumps(manifest(
        "beta", "Beta", "2.0.0",
        pages=[{"path": "index.md", "title": "Home"}],
    )))
    write(os.path.join(manifests, "home.json"), json.dumps(manifest(
        "home", "Home", "0.1.0",
        pages=[{"path": "index.md", "title": "Front page"},
               {"path": "cv.md", "title": "CV"}],
    )))
    write(os.path.join(manifests, "home-files.json"), json.dumps({
        "schema_version": 2, "slug": "home",
        "owners": {"release": ["index.html", "cv/index.html"]},
    }))
    write(os.path.join(manifests, "home-listing.json"), json.dumps({
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
    write(os.path.join(manifests, "alpha-files.json"), json.dumps({
        "schema_version": 2, "slug": "alpha",
        "owners": {"release": ["alpha/index.html", "alpha/guide/index.html",
                               "blog/hello/index.html"]},
    }))

    write(os.path.join(site, "alpha", "index.html"),
          page("Alpha", f"{CANONICAL_BASE}/alpha/",
               body='  <a href="guide/">Guide</a>', version="1.0.0"))
    write(os.path.join(site, "alpha", "guide", "index.html"),
          page("Alpha Guide", f"{CANONICAL_BASE}/alpha/guide/",
               body='  <a href="../../beta/">Beta</a>', version="1.0.0"))
    write(os.path.join(site, "blog", "hello", "index.html"),
          page("Hello", f"{CANONICAL_BASE}/blog/hello/", version="1.0.0"))
    write(os.path.join(site, "beta", "index.html"),
          page("Beta", f"{CANONICAL_BASE}/beta/", version="2.0.0"))
    write(os.path.join(site, "index.html"),
          page("Front page", f"{CANONICAL_BASE}/",
               body='  <a href="cv/">CV</a>'))
    write(os.path.join(site, "cv", "index.html"),
          page("CV", f"{CANONICAL_BASE}/cv/"))

    write(os.path.join(site, "pagefind", "pagefind.js"), "// runtime")
    write(os.path.join(site, "pagefind", "pagefind-ui.js"), "// ui")
    write(os.path.join(site, "pagefind", "pagefind-ui.css"), "/* ui */")
    write(os.path.join(site, "pagefind", "pagefind-entry.json"), json.dumps({
        "version": "1.3.0",
        "languages": {"en": {"hash": "en_abc123", "wasm": "en",
                             "page_count": 4}},
    }))
    write(os.path.join(site, "pagefind", "index", "en_abc123.pf_index"),
          "index")
    for name in ("f1", "f2", "f3", "f4"):
        write(os.path.join(site, "pagefind", "fragment",
                           f"en_{name}.pf_fragment"), "fragment")

    generate_shared_files(
        site, manifests, CANONICAL_BASE, docs_base=CANONICAL_BASE,
        home_slug=HOME,
    )


def break_everything(root):
    """Inject one defect per asserted property, in a fixed order."""
    site = os.path.join(root, "site")

    write(os.path.join(site, "gamma", "index.html"),
          page("Gamma", f"{CANONICAL_BASE}/gamma/",
               css_href=chrome_ref("gamma/index.html")))
    write(os.path.join(site, "beta", "index.html"),
          page("Beta", f"{CANONICAL_BASE}/beta/", version="1.9.0",
               css_href=chrome_ref("beta/index.html")))
    os.remove(os.path.join(site, "alpha", "guide", "index.html"))
    os.remove(os.path.join(site, "robots.txt"))
    write(os.path.join(site, "cv", "index.html"),
          page("", f"{CANONICAL_BASE}/cv/",
               css_href=chrome_ref("cv/index.html")))
    blog_index = os.path.join(site, "blog", "index.html")
    write(blog_index, re.sub(
        r'<link rel="stylesheet" href="[^"]*_chrome[^"]*">\n?', "",
        read(blog_index),
    ))
    write(os.path.join(site, "blog", "hello", "index.html"),
          page("Hello", f"{CANONICAL_BASE}/blog/hello/", version="1.0.0",
               body="<blockquote><em>[selfdoc: python_ref target=x "
                    "— not yet resolved]</em></blockquote>",
               css_href=chrome_ref("blog/hello/index.html")))
    write(os.path.join(site, "alpha", "_headers"), "leaked")
    sitemap = os.path.join(site, "sitemap.xml")
    write(sitemap, read(sitemap).replace(
        "</urlset>",
        "  <url><loc>https://old.example.net/alpha/</loc></url>\n</urlset>",
    ))


def main():
    root = tempfile.mkdtemp(prefix="selfblog-verify-record-")
    try:
        assembly = os.path.join(root, "assembly")
        build(assembly)
        report = verify_assembly(assembly, canonical_base=CANONICAL_BASE)
        if not report.ok:
            raise SystemExit(
                "the clean tree did not verify:\n" + report.error_text()
            )
        break_everything(assembly)
        report = verify_assembly(assembly, canonical_base=CANONICAL_BASE)
        sys.stdout.write(report.error_text() + "\n")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
