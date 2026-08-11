"""Tests for the single addressing authority (selfdoc_core.address).

Two layers:

1. Unit tests for ``page_address`` -- the one function that maps a page
   plus its locale/version to an output key, a stable address, a pinned
   address, and a depth.
2. A whole-tree link walker: build a fixture project with multi-level
   pages and two versions, then assert that every ``href``/``src``/
   canonical reference emitted into the output resolves to a file the
   same build actually wrote.  The walker runs the project twice --
   once mounted at an origin root and once under a slug prefix -- and
   the emitted tree must be identical, because a documentation site has
   to work at whatever path it is served from.
"""

import html as html_mod
import json
import os
import posixpath
import re
import subprocess

import pytest

from selfdoc_core.address import PageAddress, page_address
from selfdoc.build import build


# --- Unit tests: page_address ------------------------------------------


class TestPageAddress:
    """The addressing authority itself."""

    def test_root_page_versioned(self):
        addr = page_address("index.html", locale="en", version="1.0.0")
        assert addr.output_key == "en/1.0.0/index.html"
        assert addr.pinned == "en/1.0.0/"
        assert addr.stable == "en/"
        assert addr.depth == 2
        assert addr.to_site_root == "../../"
        assert addr.to_mount_root == ""

    def test_nested_page_versioned(self):
        addr = page_address("guide/index.html", locale="en", version="1.0.0")
        assert addr.output_key == "en/1.0.0/guide/index.html"
        assert addr.pinned == "en/1.0.0/guide/"
        assert addr.stable == "en/guide/"
        assert addr.depth == 3
        assert addr.to_site_root == "../../../"
        assert addr.to_mount_root == "../"

    def test_deeply_nested_page(self):
        addr = page_address(
            "reference/deep/notes/index.html", locale="fa", version="0.2.0",
        )
        assert addr.output_key == "fa/0.2.0/reference/deep/notes/index.html"
        assert addr.depth == 5
        assert addr.to_site_root == "../../../../../"
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
        addr = page_address("posts/hello/index.html")
        assert addr.output_key == "posts/hello/index.html"
        assert addr.pinned == "posts/hello/"
        assert addr.stable == "posts/hello/"
        assert addr.depth == 2
        assert addr.to_site_root == "../../"
        assert addr.to_mount_root == "../../"

    def test_mount(self):
        assert page_address("index.html", locale="en", version="1.0").mount == "en/1.0"
        assert page_address("index.html", locale="en").mount == "en"
        assert page_address("index.html").mount == ""

    def test_unified_project_mount(self):
        """A unified site mounts each constituent at <locale>/<slug>/<version>."""
        addr = page_address(
            "guide/index.html", locale="en", project="core", version="1.0.0",
        )
        assert addr.mount == "en/core/1.0.0"
        assert addr.output_key == "en/core/1.0.0/guide/index.html"
        assert addr.pinned == "en/core/1.0.0/guide/"
        assert addr.stable == "en/core/guide/"
        assert addr.depth == 4
        assert addr.to_site_root == "../../../../"
        assert addr.to_mount_root == "../"

    def test_unified_project_unversioned(self):
        addr = page_address("about/index.html", locale="en", project="core")
        assert addr.output_key == "en/core/about/index.html"
        assert addr.pinned == "en/core/about/"
        assert addr.stable == "en/core/about/"

    def test_rejects_project_without_locale(self):
        with pytest.raises(ValueError):
            page_address("index.html", project="core")

    def test_site_root_hop_reaches_the_output_root(self):
        """to_site_root resolves the output key's directory back to "."."""
        for page in ("index.html", "guide/index.html", "a/b/c/index.html"):
            addr = page_address(page, locale="en", version="1.0.0")
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
            ) == "en/1.0.0"

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

    def test_rejects_version_without_locale(self):
        """A version segment with no locale is not an address this site emits."""
        with pytest.raises(ValueError):
            page_address("index.html", locale="", version="1.0.0")


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
}


def _make_fixture(root, config_extra):
    """Create a two-version, multi-level fixture project under *root*."""
    root.mkdir(parents=True, exist_ok=True)
    versions = ["0.1.0", "0.2.0"]
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "version": versions[-1],
        "versions": [{"version": v, "indexed": True} for v in versions],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }
    config.update(config_extra)
    (root / "selfdoc.json").write_text(json.dumps(config, indent=2))

    src = root / "src"
    src.mkdir(exist_ok=True)
    (src / "__init__.py").write_text('"""Fixture package."""\n')

    docs = root / "docs"
    for rel, text in PAGES.items():
        path = docs / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    _git(["init"], cwd=root)
    _git(["add", "."], cwd=root)
    _git(["commit", "-m", "initial"], cwd=root)
    for v in versions:
        (docs / "index.md").write_text(f"# Fixture\n\nRoot page for {v}.\n")
        _git(["add", "docs/index.md"], cwd=root)
        _git(["commit", "-m", f"docs {v}"], cwd=root)
        _git(["tag", f"v{v}"], cwd=root)
    return root


ORIGIN_ROOT_CONFIG = {"base_url": "https://example.com"}
SLUG_PREFIX_CONFIG = {
    "base_url": "https://docs.example.com/fixture",
    "topology": {"docs_base": "https://docs.example.com", "slug": "fixture"},
}


# Attributes whose value is a single URL reference.
_REF_ATTRS = ("href", "src")
_SKIP_SCHEMES = ("http://", "https://", "//", "mailto:", "data:", "javascript:")


def _emitted_files(output_dir):
    """Every file the build wrote, as posix paths relative to output root."""
    out = set()
    for dirpath, _dirs, files in os.walk(output_dir):
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
    for m in re.finditer(r'\bdata-search-base="([^"]*)"', page_html):
        yield "data-search-base", html_mod.unescape(m.group(1))


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


def _walk_and_check(output_dir):
    """Assert every local reference in every emitted page resolves to an emitted file."""
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
    _walk_and_check(os.path.join(str(project), "docs", "_build"))


def test_output_tree_is_mount_independent(tmp_path):
    """The emitted file set does not depend on where the site is mounted."""
    origin = _make_fixture(tmp_path / "o", ORIGIN_ROOT_CONFIG)
    slug = _make_fixture(tmp_path / "s", SLUG_PREFIX_CONFIG)
    build(str(origin))
    build(str(slug))
    assert _emitted_files(
        os.path.join(str(origin), "docs", "_build"),
    ) == _emitted_files(os.path.join(str(slug), "docs", "_build"))


def test_search_index_paths_are_site_relative(tmp_path):
    """Search entry paths address pages from the site root, prefix included."""
    project = _make_fixture(tmp_path / "search", ORIGIN_ROOT_CONFIG)
    build(str(project))
    index_path = os.path.join(
        str(project), "docs", "_build", "search-index.json",
    )
    with open(index_path, encoding="utf-8") as f:
        entries = json.load(f)
    assert entries
    emitted = _emitted_files(os.path.join(str(project), "docs", "_build"))
    for entry in entries:
        path = entry["path"].split("#", 1)[0]
        assert not path.startswith("/"), entry
        target = posixpath.normpath(posixpath.join(path, "index.html"))
        assert target in emitted, f"search entry {entry['path']} -> {target}"
