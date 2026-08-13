"""Tests for the single addressing authority (selfdoc_core.address).

Two layers:

1. Unit tests for ``page_address`` -- the one function that maps a page
   plus its locale/version to an output key, a stable address, a pinned
   address, and a depth.
2. A whole-tree link walker: build a fixture project with multi-level
   pages, two versions and an unversioned page, then assert that every
   ``href``/``src``/canonical reference emitted into the output resolves
   to a file the same build actually wrote.  The walker runs over every
   shape the addressing has to survive: an origin-root mount, a slug
   mount, a two-locale build, and a unified site with two constituent
   projects.  The emitted tree must not depend on the mount, because a
   documentation site has to work at whatever path it is served from.
"""

import html as html_mod
import json
import os
import posixpath
import re
import subprocess

import pytest

from selfdoc_core.address import PageAddress, locale_segment, page_address
from selfdoc.build import build
from selfblog.unified import build_unified


# --- Unit tests: page_address ------------------------------------------


class TestPageAddress:
    """The addressing authority itself."""

    def test_current_version_has_no_version_segment(self):
        addr = page_address("index.html", locale="en", version="1.0.0")
        assert addr.output_key == "en/index.html"
        assert addr.stable == "en/"
        assert addr.pinned == "en/v/1.0.0/"
        assert addr.url == "en/"
        assert addr.depth == 1
        assert addr.to_site_root == "../"
        assert addr.to_mount_root == ""

    def test_archived_version_sits_under_the_archive_prefix(self):
        addr = page_address(
            "index.html", locale="en", version="1.0.0", archived=True,
        )
        assert addr.output_key == "en/v/1.0.0/index.html"
        assert addr.stable == "en/"
        assert addr.pinned == "en/v/1.0.0/"
        assert addr.url == addr.pinned
        assert addr.depth == 3
        assert addr.to_site_root == "../../../"
        assert addr.to_mount_root == ""

    def test_no_locale_segment_when_the_site_has_one_locale(self):
        """The caller drops the locale via locale_segment; addressing obeys."""
        addr = page_address("guide/index.html", version="1.0.0")
        assert addr.output_key == "guide/index.html"
        assert addr.stable == "guide/"
        assert addr.pinned == "v/1.0.0/guide/"
        assert addr.depth == 1

    def test_nested_page_current_version(self):
        addr = page_address("guide/index.html", locale="en", version="1.0.0")
        assert addr.output_key == "en/guide/index.html"
        assert addr.stable == "en/guide/"
        assert addr.depth == 2
        assert addr.to_site_root == "../../"
        assert addr.to_mount_root == "../"

    def test_nested_page_archived(self):
        addr = page_address(
            "guide/index.html", locale="en", version="1.0.0", archived=True,
        )
        assert addr.output_key == "en/v/1.0.0/guide/index.html"
        assert addr.pinned == "en/v/1.0.0/guide/"
        assert addr.stable == "en/guide/"
        assert addr.depth == 4
        assert addr.to_site_root == "../../../../"
        assert addr.to_mount_root == "../"
        # Two levels further out than to_mount_root: over v/<version>/.
        assert addr.to_stable_mount_root == "../../../"

    def test_deeply_nested_page(self):
        addr = page_address(
            "reference/deep/notes/index.html", locale="fa", version="0.2.0",
            archived=True,
        )
        assert addr.output_key == "fa/v/0.2.0/reference/deep/notes/index.html"
        assert addr.depth == 6
        assert addr.to_site_root == "../../../../../../"
        assert addr.to_mount_root == "../../../"

    def test_unversioned_page_keeps_locale(self):
        addr = page_address("about/index.html", locale="en", version="")
        assert addr.output_key == "en/about/index.html"
        assert addr.pinned == "en/about/"
        assert addr.stable == "en/about/"
        assert addr.depth == 2
        assert addr.to_site_root == "../../"
        assert addr.to_mount_root == "../"

    def test_no_mount_at_all(self):
        addr = page_address("blog/hello/index.html")
        assert addr.output_key == "blog/hello/index.html"
        assert addr.pinned == "blog/hello/"
        assert addr.stable == "blog/hello/"
        assert addr.depth == 2
        assert addr.to_site_root == "../../"
        assert addr.to_mount_root == "../../"

    def test_mount(self):
        assert page_address("index.html", locale="en", version="1.0").mount == "en"
        assert page_address(
            "index.html", locale="en", version="1.0", archived=True,
        ).mount == "en/v/1.0"
        assert page_address("index.html", locale="en").mount == "en"
        assert page_address("index.html").mount == ""

    def test_unified_project_mount(self):
        """A unified site mounts each constituent at <locale>/<slug>/."""
        addr = page_address(
            "guide/index.html", locale="en", project="core", version="1.0.0",
        )
        assert addr.mount == "en/core"
        assert addr.output_key == "en/core/guide/index.html"
        assert addr.stable == "en/core/guide/"
        assert addr.pinned == "en/core/v/1.0.0/guide/"
        assert addr.depth == 3
        assert addr.to_site_root == "../../../"
        assert addr.to_mount_root == "../"

    def test_unified_project_archived(self):
        addr = page_address(
            "guide/index.html", locale="en", project="core", version="1.0.0",
            archived=True,
        )
        assert addr.output_key == "en/core/v/1.0.0/guide/index.html"
        assert addr.stable == "en/core/guide/"

    def test_unified_project_unversioned(self):
        addr = page_address("about/index.html", locale="en", project="core")
        assert addr.output_key == "en/core/about/index.html"
        assert addr.pinned == "en/core/about/"
        assert addr.stable == "en/core/about/"

    def test_project_without_locale_is_a_single_locale_unified_site(self):
        """With one locale the segment is gone, project or no project."""
        addr = page_address("index.html", project="core")
        assert addr.output_key == "core/index.html"
        assert addr.stable == "core/"

    def test_site_root_hop_reaches_the_output_root(self):
        """to_site_root resolves the output key's directory back to "."."""
        for page in ("index.html", "guide/index.html", "a/b/c/index.html"):
            for archived in (False, True):
                addr = page_address(
                    page, locale="en", version="1.0.0", archived=archived,
                )
                here = posixpath.dirname(addr.output_key)
                assert posixpath.normpath(
                    posixpath.join(here, addr.to_site_root or "."),
                ) == "."

    def test_mount_root_hop_reaches_the_mount_root(self):
        for page in ("index.html", "guide/index.html", "a/b/c/index.html"):
            addr = page_address(page, locale="en", version="1.0.0")
            here = posixpath.dirname(addr.output_key)
            assert posixpath.normpath(
                posixpath.join(here, addr.to_mount_root or "."),
            ) == "en"
            archived = page_address(
                page, locale="en", version="1.0.0", archived=True,
            )
            here = posixpath.dirname(archived.output_key)
            assert posixpath.normpath(
                posixpath.join(here, archived.to_mount_root or "."),
            ) == "en/v/1.0.0"

    def test_stable_mount_hop_reaches_the_stable_mount(self):
        """From an archive page, the hop lands on the current version's mount."""
        for page in ("index.html", "guide/index.html", "a/b/c/index.html"):
            addr = page_address(
                page, locale="en", version="1.0.0", archived=True,
            )
            here = posixpath.dirname(addr.output_key)
            assert posixpath.normpath(
                posixpath.join(here, addr.to_stable_mount_root or "."),
            ) == "en"

    def test_is_frozen(self):
        addr = page_address("index.html", locale="en", version="1.0.0")
        assert isinstance(addr, PageAddress)
        with pytest.raises(Exception):
            addr.depth = 9  # type: ignore[misc]

    def test_rejects_absolute_page_path(self):
        with pytest.raises(ValueError):
            page_address("/index.html", locale="en", version="1.0.0")

    def test_rejects_empty_page_path(self):
        with pytest.raises(ValueError):
            page_address("", locale="en", version="1.0.0")

    def test_rejects_the_reserved_archive_segment(self):
        """A top-level page named `v` would collide with the archive tree."""
        with pytest.raises(ValueError, match="reserved segment"):
            page_address("v/index.html", locale="en", version="1.0.0")

    def test_rejects_archived_without_a_version(self):
        with pytest.raises(ValueError, match="needs a version"):
            page_address("index.html", locale="en", archived=True)

    def test_a_bare_version_needs_no_locale(self):
        """A single-locale site's archive is v/<version>/, locale-free."""
        addr = page_address("index.html", version="1.0.0", archived=True)
        assert addr.output_key == "v/1.0.0/index.html"


class TestLocaleSegment:
    """The one place that decides whether a mount carries a locale."""

    ONE = [{"code": "en", "label": "English", "default": True}]
    TWO = ONE + [{"code": "fa", "label": "Persian"}]

    def test_single_locale_drops_the_segment(self):
        assert locale_segment("en", self.ONE) == ""

    def test_multi_locale_keeps_the_segment(self):
        assert locale_segment("en", self.TWO) == "en"
        assert locale_segment("fa", self.TWO) == "fa"

    def test_no_locales_configured_drops_the_segment(self):
        assert locale_segment("en", []) == ""
        assert locale_segment("en", None) == ""


# --- Whole-tree link walker --------------------------------------------


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True)


PAGES = {
    "index.md": "# Fixture\n\nRoot page.\n",
    "guide.md": "---\ntitle: Guide\n---\n\n# Guide\n\nOne level down.\n",
    "reference/api.md": (
        "---\ntitle: API\n---\n\n# API\n\nTwo levels down.\n"
    ),
    "reference/deep/notes.md": (
        "---\ntitle: Notes\n---\n\n# Notes\n\nThree levels down.\n"
    ),
    # A page that opts out of versioning: it is built once per locale at
    # <locale>/about/, one level shallower than every versioned page, and
    # every versioned page links to it from the sidebar.
    "about.md": (
        "---\ntitle: About\nversioned: false\n---\n\n"
        "# About\n\nThe same page under every version.\n"
    ),
}


def _make_fixture(root, config_extra, locale_codes=("en",)):
    """Create a two-version, multi-level fixture project under *root*.

    With more than one locale the pages are written per-locale under
    ``docs/<code>/``, which is the layout a localized project uses.
    """
    root.mkdir(parents=True, exist_ok=True)
    versions = ["0.1.0", "0.2.0"]
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "search_engine": "pagefind",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "version": versions[-1],
        "versions": [{"version": v} for v in versions],
        "locales": [
            {
                "code": code,
                "label": code.upper(),
                "default": idx == 0,
            }
            for idx, code in enumerate(locale_codes)
        ],
    }
    config.update(config_extra)
    (root / "selfdoc.json").write_text(json.dumps(config, indent=2))

    src = root / "src"
    src.mkdir(exist_ok=True)
    (src / "__init__.py").write_text('"""Fixture package."""\n')

    docs = root / "docs"
    localized = len(locale_codes) > 1
    doc_roots = [
        (docs / code) if localized else docs for code in locale_codes
    ]
    for doc_root in doc_roots:
        for rel, text in PAGES.items():
            path = doc_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    _git(["init"], cwd=root)
    _git(["add", "."], cwd=root)
    _git(["commit", "-m", "initial"], cwd=root)
    for v in versions:
        for doc_root in doc_roots:
            (doc_root / "index.md").write_text(
                f"# Fixture\n\nRoot page for {v}.\n",
            )
        _git(["add", "docs"], cwd=root)
        _git(["commit", "-m", f"docs {v}"], cwd=root)
        _git(["tag", f"v{v}"], cwd=root)
    return root


ORIGIN_ROOT_CONFIG = {"base_url": "https://example.com"}
SLUG_PREFIX_CONFIG = {
    "base_url": "https://docs.example.com/fixture",
    "author": {"name": "Test Author", "url": "https://author.example"},
    "topology": {"docs_base": "https://docs.example.com", "slug": "fixture"},
}


# Attributes whose value is a single URL reference.
_REF_ATTRS = ("href", "src")
_SKIP_SCHEMES = ("http://", "https://", "//", "mailto:", "data:", "javascript:")


def _emitted_files(output_dir, *, include_index=True):
    """Every file the build wrote, as posix paths relative to output root.

    ``include_index=False`` drops the ``pagefind/`` tree, whose file names
    are content hashes: two builds of the same pages at different base URLs
    index the same content under different names, which says nothing about
    the page tree.
    """
    out = set()
    for dirpath, _dirs, files in os.walk(output_dir):
        if not include_index and (
            os.path.basename(dirpath) == "pagefind"
            or f"{os.sep}pagefind{os.sep}" in dirpath + os.sep
        ):
            continue
        for name in files:
            if name.endswith((".gz", ".br")):
                continue
            full = os.path.join(dirpath, name)
            out.add(os.path.relpath(full, output_dir).replace(os.sep, "/"))
    return out


def _references(page_html):
    """Yield (attribute, raw_value) for every URL-bearing attribute."""
    for attr in _REF_ATTRS:
        for m in re.finditer(rf'\b{attr}="([^"]*)"', page_html):
            yield attr, html_mod.unescape(m.group(1))


def _resolve(page_rel, ref):
    """Resolve *ref* against the page at *page_rel*; return an output-relative path."""
    ref = ref.split("#", 1)[0].split("?", 1)[0]
    if not ref:
        return None
    target = posixpath.normpath(
        posixpath.join(posixpath.dirname(page_rel), ref),
    )
    if ref.endswith("/") or target == ".":
        target = posixpath.join(target, "index.html")
    return posixpath.normpath(target)


def _walk_and_check(output_dir, base_url=""):
    """Assert every local reference in every emitted page resolves to an emitted file.

    ``base_url`` opts in to the absolute references too -- the share
    control's addresses, which are handed to a reader to open and so must
    name a page this build wrote just as much as an ``href`` does.
    """
    emitted = _emitted_files(output_dir)
    pages = sorted(p for p in emitted if p.endswith(".html"))
    assert pages, "build emitted no HTML"
    problems = []
    checked = 0
    for page_rel in pages:
        with open(os.path.join(output_dir, page_rel), encoding="utf-8") as f:
            page_html = f.read()
        for attr, raw in _references(page_html):
            if not raw or raw.startswith("#"):
                continue
            if raw.startswith(_SKIP_SCHEMES):
                continue
            if raw.startswith("/"):
                problems.append(
                    f"{page_rel}: {attr}=\"{raw}\" is origin-absolute; the "
                    f"site must resolve under any mount point",
                )
                continue
            target = _resolve(page_rel, raw)
            if target is None:
                continue
            checked += 1
            if target.startswith(".."):
                problems.append(
                    f"{page_rel}: {attr}=\"{raw}\" escapes the output root",
                )
            elif target not in emitted:
                problems.append(
                    f"{page_rel}: {attr}=\"{raw}\" -> {target} (not emitted)",
                )
        if base_url:
            prefix = base_url.rstrip("/") + "/"
            for raw in re.findall(r'data-share-url="([^"]*)"', page_html):
                share = html_mod.unescape(raw)
                assert share.startswith(prefix), (
                    f"{page_rel}: share address {share} is not this site's"
                )
                target = share[len(prefix):] or "index.html"
                if target.endswith("/"):
                    target += "index.html"
                checked += 1
                if target not in emitted:
                    problems.append(
                        f"{page_rel}: data-share-url=\"{share}\" -> {target} "
                        f"(not emitted)",
                    )
    assert checked > 0, "walker checked no references"
    assert not problems, (
        f"{len(problems)} unresolvable reference(s):\n  "
        + "\n  ".join(sorted(set(problems)))
    )


@pytest.mark.parametrize(
    "config_extra, name",
    [(ORIGIN_ROOT_CONFIG, "origin"), (SLUG_PREFIX_CONFIG, "slug")],
)
def test_every_emitted_reference_resolves(tmp_path, config_extra, name):
    """Every href/src in the emitted tree points at a file the build wrote."""
    project = _make_fixture(tmp_path / name, config_extra)
    build(str(project))
    _walk_and_check(
        os.path.join(str(project), "docs", "_build"),
        base_url=config_extra["base_url"],
    )


def test_every_emitted_reference_resolves_multi_locale(tmp_path):
    """Two locales, versioned and unversioned pages: every link resolves."""
    project = _make_fixture(
        tmp_path / "ml", ORIGIN_ROOT_CONFIG, locale_codes=("en", "fa"),
    )
    build(str(project))
    _walk_and_check(
        os.path.join(str(project), "docs", "_build"),
        base_url=ORIGIN_ROOT_CONFIG["base_url"],
    )


def test_multi_locale_with_unversioned_page_builds_every_page(tmp_path):
    """A ``versioned: false`` page must not silence the whole build.

    The page partition is per-locale: a project whose docs live under
    ``docs/<locale>/`` still has to produce every versioned page in
    every locale, plus the unversioned page once per locale.
    """
    project = _make_fixture(
        tmp_path / "ml2", ORIGIN_ROOT_CONFIG, locale_codes=("en", "fa"),
    )
    build(str(project))
    emitted = _emitted_files(os.path.join(str(project), "docs", "_build"))
    pages = (
        "index.html",
        "guide/index.html",
        "reference/api/index.html",
        "reference/deep/notes/index.html",
    )
    for locale in ("en", "fa"):
        # The current version at the stable mount, 0.1.0 under the archive
        # prefix beside it.
        for mount in (locale, f"{locale}/v/0.1.0"):
            for page in pages:
                assert f"{mount}/{page}" in emitted
        assert f"{locale}/v/0.2.0" not in " ".join(sorted(emitted))
        # The unversioned page is built once per locale, at the stable
        # mount, and never inside an archive.
        assert f"{locale}/about/index.html" in emitted
        assert f"{locale}/v/0.1.0/about/index.html" not in emitted


def test_a_build_that_produces_no_content_pages_is_a_hard_error(
    tmp_path, monkeypatch,
):
    """Zero content pages must fail loudly instead of writing an empty site.

    The page partition drives every content build; when it hands back
    paths no build can match (the shape a locale-blind partition
    produced), the site used to be written with assets and redirect
    stubs and no pages at all.
    """
    from selfdoc_core import build as build_mod

    project = _make_fixture(
        tmp_path / "empty", ORIGIN_ROOT_CONFIG, locale_codes=("en", "fa"),
    )

    def _locale_blind_partition(config, docs_dir, dir_path):
        # Paths that carry the locale segment: no per-locale build can
        # match them, so every filtered build yields nothing.
        return (
            {"en/index.md"}, {"en/about.md"}, {"en/about.md": "# About"}, {},
            set(),
        )

    monkeypatch.setattr(build_mod, "_partition_pages", _locale_blind_partition)

    with pytest.raises(RuntimeError, match="no content pages"):
        build(str(project))


def _add_walker_pages(docs_dir):
    """Give a fixture docs tree depth plus one unversioned page."""
    for rel, text in PAGES.items():
        if rel == "index.md":
            continue
        path = os.path.join(docs_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def test_every_emitted_reference_resolves_unified(make_unified_project):
    """A unified site with two constituents: every link resolves.

    The unified mount adds a project segment, and the docs-site's own
    pages mount under ``common``.  Both the landing page and the
    constituent pages have to address each other across those mounts.
    """
    docs_site = make_unified_project([
        {"name": "core", "language": "python"},
        {"name": "cli", "language": "python"},
    ])
    packages_dir = os.path.dirname(str(docs_site))
    for name in ("core", "cli"):
        _add_walker_pages(os.path.join(packages_dir, name, "docs"))
    _add_walker_pages(os.path.join(str(docs_site), "docs"))

    build_unified(str(docs_site))
    _walk_and_check(os.path.join(str(docs_site), "docs", "_build"))


def test_output_tree_is_mount_independent_but_for_the_not_found_page(tmp_path):
    """The emitted page tree does not depend on where the site is mounted.

    One file does, and only one: ``404.html``.  A hosting provider
    answers an unmatched address from the root of what it serves, so the
    not-found page belongs to the served root -- which a mounted project
    is not.  Everything else is addressed document-relative and is
    identical under every mount.
    """
    origin = _make_fixture(tmp_path / "o", ORIGIN_ROOT_CONFIG)
    slug = _make_fixture(tmp_path / "s", SLUG_PREFIX_CONFIG)
    build(str(origin))
    build(str(slug))
    origin_files = _emitted_files(
        os.path.join(str(origin), "docs", "_build"), include_index=False,
    )
    slug_files = _emitted_files(
        os.path.join(str(slug), "docs", "_build"), include_index=False,
    )
    assert origin_files - slug_files == {"404.html"}
    assert slug_files - origin_files == set()


def test_search_index_addresses_pages_that_exist(tmp_path):
    """Every indexed page is a page the build emitted, mount included."""
    from test_pagefind_index import _fragments

    project = _make_fixture(tmp_path / "search", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")
    fragments = _fragments(output_dir)
    assert fragments
    emitted = _emitted_files(output_dir)
    for fragment in fragments:
        path = fragment["url"].split("#", 1)[0].lstrip("/")
        if not path.endswith(".html"):
            path = posixpath.join(path, "index.html")
        target = posixpath.normpath(path)
        assert target in emitted, f"indexed page {fragment['url']} -> {target}"


# --- The scheme itself, over a built tree ------------------------------


def _canonical_of(html):
    """The single rel=canonical URL a page declares."""
    found = re.findall(r'<link rel="canonical" href="([^"]*)">', html)
    assert len(found) == 1, f"expected one canonical, got {found}"
    return found[0]


def _read(output_dir, rel):
    with open(os.path.join(output_dir, rel), encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize(
    "config_extra, name",
    [(ORIGIN_ROOT_CONFIG, "origin"), (SLUG_PREFIX_CONFIG, "slug")],
)
def test_two_versions_emit_the_stable_tree_plus_one_archive(
    tmp_path, config_extra, name,
):
    """The current version at the stable address, the older one under v/.

    The emitted tree is the same under either mount: a documentation site
    has to work at whatever path it is served from.
    """
    project = _make_fixture(tmp_path / name, config_extra)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")
    emitted = _emitted_files(output_dir)
    pages = (
        "index.html",
        "guide/index.html",
        "reference/api/index.html",
        "reference/deep/notes/index.html",
    )
    for page in pages:
        assert page in emitted, f"{page} missing from the stable tree"
        assert f"v/0.1.0/{page}" in emitted, f"{page} missing from the archive"
    # The current version has no archive tree of its own.
    assert not any(p.startswith("v/0.2.0/") for p in emitted)
    # And the unversioned page is emitted once, at the stable mount.
    assert "about/index.html" in emitted
    assert "v/0.1.0/about/index.html" not in emitted


def test_no_locale_segment_in_single_locale_output(tmp_path):
    """One locale means no locale segment anywhere -- paths or links."""
    project = _make_fixture(tmp_path / "single", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")
    for rel in _emitted_files(output_dir):
        assert "en/" not in rel, f"locale segment in output path {rel}"
    home = _read(output_dir, "index.html")
    assert "/en/" not in home
    assert 'hreflang' not in home


def test_multi_locale_keeps_the_locale_segment(tmp_path):
    """Two locales: the segment is back, and it leads both trees."""
    project = _make_fixture(
        tmp_path / "ml-scheme", ORIGIN_ROOT_CONFIG, locale_codes=("en", "fa"),
    )
    build(str(project))
    emitted = _emitted_files(os.path.join(str(project), "docs", "_build"))
    assert "en/guide/index.html" in emitted
    assert "fa/guide/index.html" in emitted
    assert "en/v/0.1.0/guide/index.html" in emitted
    assert "fa/v/0.1.0/guide/index.html" in emitted


def test_archives_carry_the_stable_canonical_and_no_index_directive(tmp_path):
    """An archive is canonicalized away, never noindexed.

    A page carrying both a canonical and a noindex tells a crawler to
    follow the canonical and to drop the page it points from, so the
    directive can be attributed to the canonical target.  Archives carry
    the canonical alone.
    """
    project = _make_fixture(tmp_path / "canon", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")

    for page in ("index.html", "guide/index.html"):
        current = _read(output_dir, page)
        archived = _read(output_dir, f"v/0.1.0/{page}")
        assert _canonical_of(archived) == _canonical_of(current)
        assert "/v/0.1.0/" not in _canonical_of(archived)
        assert "noindex" not in archived
        assert "noindex" not in current


def test_sitemap_lists_stable_addresses_only(tmp_path):
    """Archives are canonicalized away, so the sitemap does not list them."""
    project = _make_fixture(tmp_path / "sitemap", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")
    sitemap = _read(output_dir, "sitemap.xml")
    locs = re.findall(r"<loc>([^<]*)</loc>", sitemap)
    assert locs
    for loc in locs:
        assert "/v/" not in loc, f"archive address in the sitemap: {loc}"
    assert "https://example.com/guide/" in locs
    # Every listed address is a page this build wrote.
    emitted = _emitted_files(output_dir)
    for loc in locs:
        rel = loc[len("https://example.com/"):] or ""
        assert posixpath.normpath(posixpath.join(rel, "index.html")) in emitted


def test_feed_links_stable_addresses(tmp_path):
    project = _make_fixture(tmp_path / "feed", ORIGIN_ROOT_CONFIG)
    build(str(project))
    feed = _read(os.path.join(str(project), "docs", "_build"), "feed.xml")
    for link in re.findall(r'<link href="([^"]*)"', feed):
        assert "/v/" not in link, f"archive address in the feed: {link}"


def test_version_picker_links_are_server_side_and_resolve(tmp_path):
    """Every option carries the address the build computed for it."""
    project = _make_fixture(tmp_path / "picker", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")
    emitted = _emitted_files(output_dir)

    page = "guide/index.html"
    html = _read(output_dir, page)
    options = re.findall(r'data-value="([^"]*)" data-href="([^"]*)"', html)
    assert {v for v, _ in options} == {"0.1.0", "0.2.0"}
    for version, href in options:
        target = _resolve(page, html_mod.unescape(href))
        assert target in emitted, f"picker option {version} -> {target}"
    # The current version's option is the stable address; the older one's
    # is its archive.
    hrefs = dict(options)
    assert hrefs["0.2.0"] == "../guide/"
    assert hrefs["0.1.0"] == "../v/0.1.0/guide/"

    # From inside the archive the hops are longer, and still resolve.
    archived_page = "v/0.1.0/guide/index.html"
    archived_hrefs = dict(re.findall(
        r'data-value="([^"]*)" data-href="([^"]*)"',
        _read(output_dir, archived_page),
    ))
    assert archived_hrefs["0.2.0"] == "../../../guide/"
    assert archived_hrefs["0.1.0"] == "../../../v/0.1.0/guide/"
    # No client-side path arithmetic is left in the picker script.
    assert "location.pathname" not in html


def test_archive_pages_carry_a_dismissable_notice_keyed_per_version(tmp_path):
    project = _make_fixture(tmp_path / "notice", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")

    archived = _read(output_dir, "v/0.1.0/guide/index.html")
    assert 'class="version-notice"' in archived
    assert 'data-notice-key="0.1.0"' in archived
    assert 'class="version-notice-dismiss"' in archived
    assert "selfdoc-version-notice-" in archived, "dismissal is not stored"
    # The current version has nothing to say about being superseded.
    assert 'class="version-notice"' not in _read(output_dir, "guide/index.html")


def test_the_share_control_never_offers_an_address_that_is_not_emitted(tmp_path):
    """A pinned choice appears only where the pinned address is real.

    The current version is emitted at the stable address and nowhere else;
    its ``v/<current>/`` address does not exist until a newer version
    supersedes it.  So the current version's page offers the evergreen
    choice alone, and the pinned choice belongs to archive pages, where it
    names the page's own address.
    """
    project = _make_fixture(tmp_path / "share", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")

    def _share_urls(page):
        return re.findall(
            r'data-share-url="([^"]*)"', _read(output_dir, page),
        )

    # Current version: one choice, the evergreen address it is served at.
    current = _share_urls("guide/index.html")
    assert current == ["https://example.com/guide/"], current

    # Archive: both, and the pinned one is this page's own address.
    archived = _share_urls("v/0.1.0/guide/index.html")
    assert archived == [
        "https://example.com/guide/",
        "https://example.com/v/0.1.0/guide/",
    ], archived

    # Nothing anywhere in the tree offers the current version's phantom
    # archive address.
    emitted = _emitted_files(output_dir)
    for page in sorted(p for p in emitted if p.endswith(".html")):
        for url in _share_urls(page):
            target = url[len("https://example.com/"):] + "index.html"
            assert target in emitted, f"{page} shares {url}, never written"


def test_a_page_named_v_is_refused(tmp_path):
    """`v` is the archive prefix, so no page may take it."""
    project = _make_fixture(tmp_path / "reserved", ORIGIN_ROOT_CONFIG)
    with open(os.path.join(str(project), "docs", "v.md"), "w") as f:
        f.write("# V\n\nA page that wants the archive prefix.\n")
    with pytest.raises(RuntimeError, match="reserved top-level path 'v'"):
        build(str(project))


def test_the_resolution_check_passes_on_a_good_build(tmp_path):
    """LINK001 is the walker's assertion as a user-facing check."""
    from selfdoc_core.resolution import check_output_resolution

    project = _make_fixture(tmp_path / "resolve-ok", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")
    assert check_output_resolution(
        output_dir, base_url="https://example.com",
    ) == []


def test_the_resolution_check_fires_on_a_broken_reference(tmp_path):
    from selfdoc_core.resolution import check_output_resolution

    project = _make_fixture(tmp_path / "resolve-bad", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")

    page = os.path.join(output_dir, "guide", "index.html")
    with open(page, encoding="utf-8") as f:
        html = f.read()
    with open(page, "w", encoding="utf-8") as f:
        f.write(html.replace("<article", '<a href="../nowhere/">gone</a><article', 1))

    lints = check_output_resolution(output_dir, base_url="https://example.com")
    assert [lint.code for lint in lints] == ["LINK001"]
    assert lints[0].severity == "error"
    assert "nowhere" in lints[0].message
    assert lints[0].file == "guide/index.html"


def test_the_resolution_check_fires_on_a_share_address_that_was_not_written(
    tmp_path,
):
    """A share address is a reference, so LINK001 owns it too.

    This is the structural guard behind the share control's shape: the
    control offering the current version's ``v/<version>/`` address (which
    nothing writes until that version is superseded) is not a judgement
    call the renderer gets to make quietly -- the check refuses the build.
    """
    from selfdoc_core.resolution import check_output_resolution

    project = _make_fixture(tmp_path / "resolve-share", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")

    page = os.path.join(output_dir, "guide", "index.html")
    with open(page, encoding="utf-8") as f:
        html = f.read()
    with open(page, "w", encoding="utf-8") as f:
        f.write(html.replace(
            'data-share-url="https://example.com/guide/"',
            'data-share-url="https://example.com/v/0.2.0/guide/"',
            1,
        ))

    lints = check_output_resolution(output_dir, base_url="https://example.com")
    assert [lint.code for lint in lints] == ["LINK001"]
    assert "share address" in lints[0].message
    assert "v/0.2.0/guide/" in lints[0].message
    assert lints[0].file == "guide/index.html"


def test_the_resolution_check_fires_on_a_broken_sitemap_entry(tmp_path):
    from selfdoc_core.resolution import check_output_resolution

    project = _make_fixture(tmp_path / "resolve-sitemap", ORIGIN_ROOT_CONFIG)
    build(str(project))
    output_dir = os.path.join(str(project), "docs", "_build")

    sitemap = os.path.join(output_dir, "sitemap.xml")
    with open(sitemap, encoding="utf-8") as f:
        body = f.read()
    with open(sitemap, "w", encoding="utf-8") as f:
        f.write(body.replace(
            "</urlset>",
            "  <url><loc>https://example.com/ghost/</loc></url>\n</urlset>",
        ))

    lints = check_output_resolution(output_dir, base_url="https://example.com")
    assert [lint.code for lint in lints] == ["LINK001"]
    assert "ghost" in lints[0].message


def test_posts_are_at_the_same_blog_address_in_both_builds(tmp_path):
    """The full build and the posts-only build agree on where a post lives."""
    import selfblog  # registers the post provider

    assert selfblog
    project = _make_fixture(tmp_path / "posts", ORIGIN_ROOT_CONFIG)
    posts_dir = os.path.join(str(project), ".selfdoc", "posts")
    os.makedirs(posts_dir, exist_ok=True)
    with open(os.path.join(posts_dir, "2026-01-01-hello.md"), "w") as f:
        f.write(
            "---\ntitle: Hello World\ndate: 2026-01-01\nslug: hello-world\n"
            "directives: false\n"
            "---\n\nA post body paragraph.\n"
        )
    config_path = os.path.join(str(project), "selfdoc.json")
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    config["posts"] = {"dir": ".selfdoc/posts/"}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    output_dir = os.path.join(str(project), "docs", "_build")

    build(str(project))
    full = _emitted_files(output_dir)
    assert "blog/hello-world/index.html" in full
    assert "blog/index.html" in full
    _walk_and_check(output_dir)

    build(str(project), target="posts")
    posts_only = {p for p in _emitted_files(output_dir) if p.endswith(".html")}
    assert posts_only == {"blog/hello-world/index.html", "blog/index.html"}
