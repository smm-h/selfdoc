"""Whether every reference a build emitted resolves to a file it wrote.

The build derives every address from :mod:`selfdoc_core.address`, and the
test suite walks a built tree asserting that each emitted reference lands
on an emitted file.  This module is that assertion as a user-facing check:
one lint code, ``LINK001``, over the output directory.

Five kinds of reference are covered, which is every kind the build emits:

* document-relative ``href``/``src`` attributes in the pages themselves,
* the absolute ``rel="canonical"`` link on each page,
* the absolute ``data-share-url`` addresses the share control offers,
* the ``<loc>`` entries of every sitemap,
* the entry links of the Atom feed.

The last four are absolute URLs, so they are checked against the site's
configured base: an absolute URL that points into this site must name a
page this build wrote, and one that points elsewhere is not ours to
verify.  A share address is a reference like any other -- it is handed to
a reader to open -- so a control that offers an address the build did not
write fails here rather than 404ing for whoever it was shared with.
"""

from __future__ import annotations

import html as html_mod
import os
import posixpath
import re

from selfdoc_core.lints import LintResult

__all__ = [
    "LINT_CODE",
    "check_output_resolution",
    "external_references",
    "page_references",
    "reference_target",
    "site_relative_path",
]

#: The lint code every unresolvable reference is reported under.
LINT_CODE = "LINK001"

_REF_ATTR_RE = re.compile(r'\b(href|src|data-search-base)="([^"]*)"')
_CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]*)"')
_SHARE_URL_RE = re.compile(r'\bdata-share-url="([^"]*)"')
_LOC_RE = re.compile(r"<loc>([^<]*)</loc>")
_FEED_LINK_RE = re.compile(r'<link href="([^"]*)"')
_SKIP_SCHEMES = (
    "http://", "https://", "//", "mailto:", "data:", "javascript:", "tel:",
)


def _emitted_files(output_dir):
    """Every file the build wrote, as posix paths relative to *output_dir*."""
    emitted = set()
    for dirpath, _dirs, files in os.walk(output_dir):
        for name in files:
            if name.endswith((".gz", ".br")):
                continue
            full = os.path.join(dirpath, name)
            emitted.add(
                os.path.relpath(full, output_dir).replace(os.sep, "/")
            )
    return emitted


def reference_target(page_rel, ref):
    """Resolve *ref*, written on the page at *page_rel*, to an output path.

    Returns None when the reference addresses nothing on its own (an empty
    value, or a bare fragment).
    """
    ref = ref.split("#", 1)[0].split("?", 1)[0]
    if not ref:
        return None
    target = posixpath.normpath(
        posixpath.join(posixpath.dirname(page_rel), ref),
    )
    if ref.endswith("/") or target == ".":
        target = posixpath.join(target, "index.html")
    return posixpath.normpath(target)


def site_relative_path(url, base_url):
    """The output-relative path an absolute *url* names, or None.

    None means the URL is not this site's -- an external link, or a URL
    with no base to measure it against.
    """
    if not base_url:
        return None
    base = base_url.rstrip("/")
    if url == base:
        return "index.html"
    if not url.startswith(base + "/"):
        return None
    path = url[len(base) + 1:].split("#", 1)[0].split("?", 1)[0]
    if not path or path.endswith("/"):
        path += "index.html"
    return posixpath.normpath(path)


def page_references(page_html):
    """Yield ``(attr, ref)`` for every internal reference *page_html* writes.

    Internal means "addressed within this site": a fragment, an empty
    value and every off-site scheme are dropped, so what is left is either
    a document-relative reference or an origin-absolute one (which is a
    defect this module reports, not a reference to follow).
    """
    for attr, raw in _REF_ATTR_RE.findall(page_html):
        ref = html_mod.unescape(raw)
        if not ref or ref.startswith("#") or ref.startswith(_SKIP_SCHEMES):
            continue
        yield attr, ref


def external_references(page_html):
    """Yield every absolute ``http(s)`` URL *page_html* references.

    The other half of :func:`page_references`: what this module cannot
    verify against the emitted tree, because it names somebody else's
    server.  Whether those still answer is the outbound check's question.
    """
    for _attr, raw in _REF_ATTR_RE.findall(page_html):
        ref = html_mod.unescape(raw)
        if ref.startswith(("http://", "https://")):
            yield ref


def check_output_resolution(output_dir, base_url=""):
    """Check every emitted reference in *output_dir* against what was written.

    Args:
        output_dir: The build output directory.  A directory that holds no
            HTML is not a built site and yields no diagnostics.
        base_url: The site's configured base URL, used to tell this site's
            absolute URLs (canonicals, sitemap entries, feed links) from
            everyone else's.

    Returns:
        A list of ``LintResult`` under :data:`LINT_CODE`, one per
        unresolvable reference.
    """
    if not os.path.isdir(output_dir):
        return []
    emitted = _emitted_files(output_dir)
    pages = sorted(p for p in emitted if p.endswith(".html"))
    if not pages:
        return []

    lints = []

    def _fail(where, message):
        lints.append(LintResult(
            file=where, line=None, code=LINT_CODE, message=message,
        ))

    def _check_absolute(where, kind, url):
        target = site_relative_path(url, base_url)
        if target is None:
            return
        if target not in emitted:
            _fail(where, f"{kind} {url} -> {target}, which this build did not write")

    for page_rel in pages:
        with open(os.path.join(output_dir, page_rel), encoding="utf-8") as f:
            page_html = f.read()

        for attr, ref in page_references(page_html):
            if ref.startswith("/"):
                _fail(
                    page_rel,
                    f'{attr}="{ref}" is origin-absolute; the site has to '
                    f"resolve under any mount point, so links are "
                    f"document-relative",
                )
                continue
            target = reference_target(page_rel, ref)
            if target is None:
                continue
            if target.startswith(".."):
                _fail(page_rel, f'{attr}="{ref}" escapes the output root')
            elif target not in emitted:
                _fail(
                    page_rel,
                    f'{attr}="{ref}" -> {target}, which this build did '
                    f"not write",
                )

        for canonical in _CANONICAL_RE.findall(page_html):
            _check_absolute(
                page_rel, "canonical", html_mod.unescape(canonical),
            )

        for share in _SHARE_URL_RE.findall(page_html):
            _check_absolute(
                page_rel, "share address", html_mod.unescape(share),
            )

    for rel in sorted(emitted):
        if rel.endswith(".xml") and "sitemap" in os.path.basename(rel):
            with open(os.path.join(output_dir, rel), encoding="utf-8") as f:
                body = f.read()
            for loc in _LOC_RE.findall(body):
                loc = html_mod.unescape(loc)
                if loc.endswith(".xml"):
                    # A sitemap index names sitemaps, not pages.
                    target = site_relative_path(loc, base_url)
                    if target is not None and target not in emitted:
                        _fail(rel, f"sitemap index entry {loc} was not written")
                    continue
                _check_absolute(rel, "sitemap entry", loc)
        elif os.path.basename(rel) == "feed.xml":
            with open(os.path.join(output_dir, rel), encoding="utf-8") as f:
                body = f.read()
            for link in _FEED_LINK_RE.findall(body):
                link = html_mod.unescape(link)
                if link.endswith("feed.xml"):
                    continue
                _check_absolute(rel, "feed link", link)

    return lints
