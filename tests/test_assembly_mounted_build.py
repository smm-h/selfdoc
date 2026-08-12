"""A real mounted build, grafted: do the references still resolve?

The other assembly tests stand fixture pages in for a build's output.  This
one runs the actual build -- a project declaring ``topology.docs_base`` and
``topology.slug``, with a post -- grafts what it produced the way a deploy
does, and reads the result with the deploy's own verification.

That is the only way the defect this file covers could be seen at all: the
build emitted a project page linking ``../blog/<post>/`` and a post
canonicalized under the project's slug, both of which are correct in the
project's own output tree and both of which name nothing once the assembly
has moved the posts to the site level.  Every published project contributed
its own copies of it.
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

from selfdoc.build import build
from selfblog.assembly import integrate_project
from selfblog.verify import read_tree, verify_assembly
from selfdoc_core.resolution import check_output_resolution

from tests.test_assembly_integrate import (  # noqa: F401  (fixtures)
    CANONICAL_BASE,
    RunRecorder,
    _manifest,
    _page,
    _write,
    runner,
)
from tests.test_assembly_site_blog import blogging_assembly, _post  # noqa: F401

from conftest import default_config


POST_SLUG = "hello-world"


@pytest.fixture()
def real_alpha_build(tmp_path):
    """A real build of a mounted project with a post.

    Built here rather than inside the assembly fixture because the
    integrate fixtures stand in for every subprocess, and a build shells
    out to git for the post manifest.  This fixture is requested first, so
    the build runs against the real world before the stub is installed.
    """
    return _build_alpha(str(tmp_path / "alpha-src"))


def _install_alpha_build(root, built, extra_files=()):
    """Put a real build where the deploy expects alpha's clone to be."""
    source = os.path.join(str(root), "source", "alpha")
    shutil.rmtree(source)
    shutil.copytree(built, source)
    for rel, content in extra_files:
        _write(os.path.join(source, "docs", "_build", *rel.split("/")), content)
    # The site root's own assets, which the home project supplies on the
    # live site: its output root IS the site root, so its stylesheet and
    # favicon are the ones a page at the site level asks for.
    site = os.path.join(str(root), "site")
    for name in ("style.css", "favicon.svg"):
        _write(os.path.join(site, name), "/* home */")
    return source


def _build_alpha(source):
    """Build a project mounted at ``/alpha/`` with one post."""
    os.makedirs(source)

    config = default_config(
        docs="docs/", output="docs/_build/",
        base_url=f"{CANONICAL_BASE}/alpha",
        topology={"docs_base": CANONICAL_BASE, "slug": "alpha"},
    )
    with open(os.path.join(source, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    src = os.path.join(source, "src")
    os.makedirs(src)
    with open(os.path.join(src, "__init__.py"), "w") as f:
        f.write('"""Example package."""\n')

    docs = os.path.join(source, "docs")
    os.makedirs(docs)
    with open(os.path.join(docs, "index.md"), "w") as f:
        f.write("# Alpha\n\nWelcome.\n")
    with open(os.path.join(docs, "guide.md"), "w") as f:
        f.write("# Guide\n\nHow to.\n")

    posts = os.path.join(source, ".selfdoc", "posts")
    os.makedirs(posts)
    with open(os.path.join(posts, "hello.md"), "w") as f:
        f.write(
            "---\ntitle: Hello World\ndate: 2024-06-01\n"
            f"slug: {POST_SLUG}\ntags: []\ndraft: false\ndirectives: false\n"
            "---\nThe post body.\n"
        )

    build(source)

    _write(os.path.join(source, ".selfdoc", "manifest.json"), json.dumps(
        _manifest("alpha", "Alpha", "1.0.0", posts=[
            _post(POST_SLUG, "Hello World", "2024-06-01"),
        ]),
    ))
    return source


@pytest.fixture()
def grafted(real_alpha_build, blogging_assembly, runner):  # noqa: F811
    """The assembly after a real mounted build of alpha was deployed into it."""
    root = blogging_assembly
    _install_alpha_build(root, real_alpha_build)
    integrate_project(
        slug="alpha", version="1.0.0", ref="v1.0.0",
        source_repo="owner/alpha", scope="full",
        canonical_base=CANONICAL_BASE, assembly_dir=str(root),
        retry_delay=0, build=False,
    )
    return root


def _read(root, *parts):
    with open(os.path.join(str(root), "site", *parts), encoding="utf-8") as f:
        return f.read()


# -- where the build put the post, and where the assembly serves it ------------


def test_the_post_is_served_at_the_site_level(grafted):
    assert os.path.isfile(
        os.path.join(str(grafted), "site", "blog", POST_SLUG, "index.html"),
    )
    assert not os.path.exists(
        os.path.join(str(grafted), "site", "alpha", "blog"),
    )


def test_a_project_page_links_the_post_where_the_assembly_serves_it(grafted):
    guide = _read(grafted, "alpha", "guide", "index.html")
    assert f'href="{CANONICAL_BASE}/blog/{POST_SLUG}/"' in guide


def test_the_posts_canonical_is_its_site_level_address(grafted):
    post = _read(grafted, "blog", POST_SLUG, "index.html")
    assert f'<link rel="canonical" href="{CANONICAL_BASE}/blog/{POST_SLUG}/">' \
        in post


# -- the deploy's own reading of the tree --------------------------------------


def test_no_reference_into_the_site_level_blog_dangles(grafted):
    """The 554-strong class of dead references this fixes.

    Every ``blog/`` reference in the assembled tree is resolved the way
    the deploy resolves it, and none of them may name a file the tree
    does not carry.
    """
    tree = read_tree(str(grafted), CANONICAL_BASE)
    failures = check_output_resolution(tree.site_dir, CANONICAL_BASE)
    dangling = [
        f"{lint.file}: {lint.message}" for lint in failures
        if "blog" in (lint.message or "") or "blog" in (lint.file or "")
    ]
    assert dangling == []


def test_the_grafted_tree_verifies_clean(grafted):
    report = verify_assembly(str(grafted), canonical_base=CANONICAL_BASE)
    assert report.ok, report.error_text()


# -- the not-found page --------------------------------------------------------


def test_the_mounted_build_emitted_no_404_to_graft(grafted):
    """Nothing to filter, because nothing was written."""
    assert not os.path.exists(
        os.path.join(str(grafted), "source", "alpha", "docs", "_build",
                     "404.html"),
    )
    assert not os.path.exists(
        os.path.join(str(grafted), "site", "alpha", "404.html"),
    )


def test_a_404_already_in_a_build_is_dropped_at_the_graft(
    real_alpha_build, blogging_assembly, runner,  # noqa: F811  (fixtures)
):
    """A project built by an older selfdoc still carries one.

    It is filtered on the way in, like every other routing artifact: a
    subtree 404 is never served, and it fails the page assertions.
    """
    root = blogging_assembly
    _install_alpha_build(root, real_alpha_build, extra_files=[
        ("404.html", _page("Page not found", "alpha/404.html")),
    ])
    site = os.path.join(str(root), "site")
    integrate_project(
        slug="alpha", version="1.0.0", ref="v1.0.0",
        source_repo="owner/alpha", scope="full",
        canonical_base=CANONICAL_BASE, assembly_dir=str(root),
        retry_delay=0, build=False,
    )
    assert not os.path.exists(os.path.join(site, "alpha", "404.html"))
