"""The assembly's site-level page chrome.

Two properties are asserted here.  The first is the defect the live site
shipped: the pages the assembly generates itself -- the blog index, the
project listing and the root 404 -- carried no stylesheet at all, because
``wrap_shared_page`` took a ``css_url`` no caller ever passed.  A wrapped
page now names a stylesheet, and the file it names exists in the tree.

The second is the structural fix behind it.  A project's build writes its
own ``style.css`` at its own output root, so inside the assembly the same
stylesheet sat once per subtree and a presentation fix meant republishing
every project.  The assembly now emits one site-level asset per theme in
use and re-points every page at it on every deploy.
"""

import json
import os
import re

import pytest

from selfblog.assembly import SITE_RESERVED_DIRS, generate_shared_files
from selfblog.chrome import (
    CHROME_DIR,
    DEFAULT_THEME,
    chrome_asset_rel,
    chrome_css,
    chrome_href,
    chrome_themes,
    is_chrome_reference,
    manifest_theme,
    page_theme,
    repoint_page,
    site_root_prefix,
    write_chrome_assets,
)
from selfblog.shared import generate_not_found_page, wrap_shared_page

CANONICAL_BASE = "https://docs.example.com"

_STYLESHEET_RE = re.compile(
    r"""<link\b[^>]*\brel="stylesheet"[^>]*>""", re.IGNORECASE,
)
_HREF_RE = re.compile(r'href="([^"]*)"')


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _manifest(slug, name, version, pages=None, posts=None, theme=None):
    manifest = {
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
        "posts": posts or [],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }
    if theme is not None:
        manifest["theme"] = theme
    return manifest


def _built_page(css_href, canonical):
    """A page shaped the way a project's build shapes one.

    Three references to the same stylesheet -- the preload, the async
    stylesheet and the ``<noscript>`` fallback -- because that is what
    ``_wrap_page`` writes and all three have to be re-pointed together.
    """
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<title>A page</title>\n"
        f'<link rel="canonical" href="{canonical}">\n'
        f'<link rel="preload" href="{css_href}" as="style">\n'
        f'<link rel="stylesheet" href="{css_href}" media="print" '
        "onload=\"this.media='all'\">"
        f'<noscript><link rel="stylesheet" href="{css_href}"></noscript>\n'
        "</head>\n<body>\n<p>body</p>\n</body>\n</html>\n"
    )


@pytest.fixture()
def tree(tmp_path):
    """A site with one project subtree and the manifests beside it."""
    site = tmp_path / "site"
    manifests = tmp_path / "manifests"
    os.makedirs(site)
    os.makedirs(manifests)
    _write(str(manifests / "alpha.json"), json.dumps(_manifest(
        "alpha", "Alpha", "1.0.0",
        pages=[{"path": "index.md", "title": "Home"},
               {"path": "guide.md", "title": "Guide"}],
        posts=[{"slug": "hello", "title": "Hello", "date": "2024-06-01"}],
    )))
    _write(str(site / "alpha" / "index.html"),
           _built_page("style.css", f"{CANONICAL_BASE}/alpha/"))
    _write(str(site / "alpha" / "guide" / "index.html"),
           _built_page("../style.css", f"{CANONICAL_BASE}/alpha/guide/"))
    _write(str(site / "alpha" / "style.css"), "/* alpha's own copy */")
    _write(str(site / "blog" / "hello" / "index.html"),
           _built_page("../../style.css", f"{CANONICAL_BASE}/blog/hello/"))
    return tmp_path


def _generate(tmp_path, **kwargs):
    return generate_shared_files(
        str(tmp_path / "site"), str(tmp_path / "manifests"),
        CANONICAL_BASE, docs_base=CANONICAL_BASE, **kwargs,
    )


def _stylesheets(page_html):
    """Every ``rel=stylesheet`` href on a page, in document order."""
    return [
        match.group(1)
        for tag in _STYLESHEET_RE.findall(page_html)
        for match in [_HREF_RE.search(tag)]
        if match is not None
    ]


def _resolve(page_rel, ref):
    """The site-relative file a document-relative *ref* on a page names."""
    base = os.path.dirname(page_rel)
    return os.path.normpath(os.path.join(base, ref)).replace(os.sep, "/")


# -- S1: a wrapped shared page ships a stylesheet that exists -----------------


def test_wrap_shared_page_requires_a_stylesheet():
    """The parameter is not optional any more, so it cannot go dead again."""
    with pytest.raises(TypeError):
        wrap_shared_page("Blog", "<p>x</p>", search_prefix="")


def test_wrap_shared_page_refuses_an_empty_stylesheet():
    with pytest.raises(ValueError, match="css_url"):
        wrap_shared_page("Blog", "<p>x</p>", css_url="", search_prefix="")


def test_wrap_shared_page_links_the_stylesheet_it_is_given():
    page = wrap_shared_page(
        "Blog", "<p>x</p>", css_url="../_chrome/minimal-abc.css",
        search_prefix="../",
    )
    assert "../_chrome/minimal-abc.css" in _stylesheets(page)


def test_the_not_found_page_carries_a_stylesheet():
    page = generate_not_found_page(
        CANONICAL_BASE, css_url=f"{CHROME_DIR}/minimal-abc.css",
    )
    assert f"{CHROME_DIR}/minimal-abc.css" in _stylesheets(page)


@pytest.mark.parametrize("page_rel", [
    "blog/index.html", "projects/index.html", "404.html",
])
def test_every_generated_shared_page_names_a_stylesheet_that_exists(
        tree, page_rel):
    """The live defect: these three shipped as bare HTML."""
    _generate(tree)
    site = tree / "site"
    page_html = (site / page_rel).read_text(encoding="utf-8")
    hrefs = [
        ref for ref in _stylesheets(page_html)
        if is_chrome_reference(ref)
    ]
    assert hrefs, f"site/{page_rel} names no page-chrome stylesheet"
    for ref in hrefs:
        target = _resolve(page_rel, ref)
        assert (site / target).is_file(), (
            f"site/{page_rel} names {ref}, which resolves to "
            f"site/{target} and no such file was written"
        )


def test_no_shared_page_carries_the_old_inline_fallback(tree):
    """The five-line inline block the pages fell back to is gone."""
    _generate(tree)
    page = (tree / "site" / "blog" / "index.html").read_text(encoding="utf-8")
    assert "font-family: system-ui" not in page


# -- S2: one site-level chrome asset, referenced by every page ----------------


def test_the_chrome_directory_is_a_reserved_site_directory():
    """No project may claim it as a slug."""
    assert CHROME_DIR in SITE_RESERVED_DIRS


def test_generate_writes_one_chrome_asset(tree):
    _generate(tree)
    chrome_dir = tree / "site" / CHROME_DIR
    assets = sorted(p.name for p in chrome_dir.iterdir())
    assert len(assets) == 1
    assert assets[0].startswith(f"{DEFAULT_THEME}-")
    assert assets[0].endswith(".css")


def test_the_chrome_asset_is_the_theme_stylesheet(tree):
    _generate(tree)
    rel = chrome_asset_rel(DEFAULT_THEME, chrome_css(DEFAULT_THEME))
    written = (tree / "site" / rel).read_text(encoding="utf-8")
    assert written == chrome_css(DEFAULT_THEME)
    # Theme rules and the assembly's own shared-page rules, in one file.
    assert ".topbar" in written
    assert ".blog-entry" in written


def test_the_asset_name_is_content_hashed():
    css = chrome_css(DEFAULT_THEME)
    rel = chrome_asset_rel(DEFAULT_THEME, css)
    assert rel == chrome_asset_rel(DEFAULT_THEME, css)
    assert rel != chrome_asset_rel(DEFAULT_THEME, css + "\n.x{}")


def test_every_grafted_page_is_repointed_at_the_site_asset(tree):
    """A project's pages stop naming their own subtree copy."""
    _generate(tree)
    site = tree / "site"
    rel = chrome_asset_rel(DEFAULT_THEME, chrome_css(DEFAULT_THEME))
    for page_rel in ("alpha/index.html", "alpha/guide/index.html",
                     "blog/hello/index.html"):
        page_html = (site / page_rel).read_text(encoding="utf-8")
        assert chrome_href(page_rel, rel) in page_html
        assert _stylesheets(page_html)
        for ref in _stylesheets(page_html):
            assert not ref.endswith("/style.css")
            assert ref != "style.css"


def test_all_three_references_on_a_page_move_together(tree):
    """Preload, async stylesheet and noscript fallback name one file."""
    _generate(tree)
    page_html = (tree / "site" / "alpha" / "guide" / "index.html").read_text(
        encoding="utf-8",
    )
    rel = chrome_asset_rel(DEFAULT_THEME, chrome_css(DEFAULT_THEME))
    href = chrome_href("alpha/guide/index.html", rel)
    assert page_html.count(f'href="{href}"') == 3


def test_a_projects_own_style_css_is_left_in_place(tree):
    """Migration: the subtree copy stays, so nothing is broken mid-flight."""
    _generate(tree)
    assert (tree / "site" / "alpha" / "style.css").is_file()


def test_a_second_deploy_repoints_pages_at_a_changed_asset(tree, monkeypatch):
    """A toolchain upgrade reaches the whole site without republishing it."""
    _generate(tree)
    site = tree / "site"
    first = sorted(p.name for p in (site / CHROME_DIR).iterdir())

    import selfblog.chrome as chrome_mod
    real = chrome_mod.chrome_css
    monkeypatch.setattr(
        chrome_mod, "chrome_css", lambda theme: real(theme) + ".added{}",
    )
    _generate(tree)

    second = sorted(p.name for p in (site / CHROME_DIR).iterdir())
    assert second != first
    # The stale asset is gone, not accumulated.
    assert len(second) == 1
    page_html = (site / "alpha" / "index.html").read_text(encoding="utf-8")
    assert second[0] in page_html
    assert first[0] not in page_html


def test_custom_css_is_never_repointed(tree):
    """``custom.css`` is the project's content, not the chrome."""
    _write(str(tree / "site" / "alpha" / "extra.html"),
           _built_page("style.css", f"{CANONICAL_BASE}/alpha/extra/").replace(
               "</head>", '<link rel="stylesheet" href="custom.css">\n</head>',
           ))
    _generate(tree)
    page_html = (tree / "site" / "alpha" / "extra.html").read_text(
        encoding="utf-8",
    )
    assert 'href="custom.css"' in page_html


# -- theme keying --------------------------------------------------------------


def test_a_manifest_without_a_theme_uses_the_builds_own_default():
    assert manifest_theme(_manifest("alpha", "Alpha", "1.0.0")) == DEFAULT_THEME


def test_a_manifest_theme_is_honoured():
    assert manifest_theme(
        _manifest("alpha", "Alpha", "1.0.0", theme="clean"),
    ) == "clean"


def test_the_asset_set_covers_every_declared_theme(tmp_path):
    site = tmp_path / "site"
    os.makedirs(site)
    assets = write_chrome_assets(str(site), ["minimal", "clean"])
    assert set(assets) == {"minimal", "clean"}
    for rel in assets.values():
        assert (tmp_path / "site" / rel).is_file()


def test_themes_are_keyed_by_slug_with_the_home_theme_named():
    by_slug, home_theme = chrome_themes(
        [
            _manifest("home", "Home", "0.1.0", theme="clean"),
            _manifest("alpha", "Alpha", "1.0.0"),
        ],
        "home",
    )
    assert by_slug == {"home": "clean", "alpha": DEFAULT_THEME}
    assert home_theme == "clean"


def test_a_page_in_a_subtree_takes_that_projects_theme():
    by_slug = {"alpha": "clean", "home": "minimal"}
    assert page_theme("alpha/guide/index.html", by_slug, "minimal") == "clean"


def test_a_site_level_page_takes_the_home_theme():
    by_slug = {"alpha": "clean"}
    for page_rel in ("404.html", "blog/index.html", "blog/hello/index.html",
                     "projects/index.html", "cv/index.html"):
        assert page_theme(page_rel, by_slug, "minimal") == "minimal"


# -- the reference shape -------------------------------------------------------


@pytest.mark.parametrize("page_rel,expected", [
    ("404.html", ""),
    ("blog/index.html", "../"),
    ("alpha/guide/index.html", "../../"),
])
def test_the_hop_back_to_the_site_root(page_rel, expected):
    assert site_root_prefix(page_rel) == expected


def test_the_reference_is_relative_never_origin_absolute():
    """The tree has to resolve under any mount point."""
    href = chrome_href("alpha/guide/index.html", f"{CHROME_DIR}/minimal-a.css")
    assert not href.startswith("/")
    assert href == f"../../{CHROME_DIR}/minimal-a.css"


@pytest.mark.parametrize("ref,recognised", [
    ("style.css", True),
    ("../style.css", True),
    (f"../{CHROME_DIR}/minimal-abc.css", True),
    ("custom.css", False),
    ("pagefind/pagefind-ui.css", False),
    ("/style.css", False),
    ("https://cdn.example.com/style.css", False),
    ("", False),
])
def test_which_references_the_pass_owns(ref, recognised):
    assert is_chrome_reference(ref) is recognised


def test_repointing_leaves_a_page_with_no_chrome_reference_alone():
    page = "<html><head><title>x</title></head><body></body></html>"
    assert repoint_page(page, "a/index.html", f"{CHROME_DIR}/m-a.css") == page
