"""The generated ``_worker.js``, asserted twice over.

The worker is generated JavaScript, so there are two honest things to
assert about it and this module does both.

**Its structure**, from Python: which constants it declares, that the
address space it embeds is data read from the manifests, and that its size
grows with the number of projects and posts rather than with the number of
pages.

**Its behaviour**, in node.  The generated module exports ``routeRequest``,
a pure function from a request URL to either the absolute URL of a 301 or
``null`` for "serve this".  Each test writes the generated worker to a temp
directory beside a driver module, runs the pair under ``node``, and asserts
the table of input to output.  Running the real generated artifact is the
point: a test that re-implemented the routing in Python would assert
against a second implementation, not against what gets deployed.

``node`` is what the worker runtime is, so a machine without it cannot make
this assertion at all; those tests skip and say so rather than passing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from selfblog.assembly import generate_worker_js

CANONICAL_BASE = "https://docs.example.com"
LEGACY_BLOG_HOST = "blog.example.com"
PROJECT_SLUGS = ("alpha", "beta")
POST_SLUGS = ("hello", "world")

needs_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is the worker's runtime; without it the generated module "
           "cannot be executed and its routing cannot be asserted.",
)

_DRIVER = """\
import { routeRequest } from "./worker.mjs";
const inputs = JSON.parse(process.argv[2]);
console.log(JSON.stringify(inputs.map((url) => routeRequest(url))));
"""


def _worker(**kwargs) -> str:
    params = {
        "project_slugs": PROJECT_SLUGS,
        "post_slugs": POST_SLUGS,
    }
    params.update(kwargs)
    return generate_worker_js(CANONICAL_BASE, LEGACY_BLOG_HOST, **params)


def _route(tmp_path, urls, js=None):
    """Return what the generated worker routes each of *urls* to."""
    js = _worker() if js is None else js
    worker_path = os.path.join(str(tmp_path), "worker.mjs")
    driver_path = os.path.join(str(tmp_path), "driver.mjs")
    with open(worker_path, "w", encoding="utf-8") as f:
        f.write(js)
    with open(driver_path, "w", encoding="utf-8") as f:
        f.write(_DRIVER)
    result = subprocess.run(
        ["node", driver_path, json.dumps(list(urls))],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _routes(tmp_path, table, js=None):
    """Assert a whole input-to-output table in one node run."""
    urls = list(table)
    got = _route(tmp_path, urls, js=js)
    assert dict(zip(urls, got)) == dict(table)


# -- one hostname -------------------------------------------------------------


@needs_node
def test_canonical_host_requests_pass_through(tmp_path):
    """Nothing on the canonical host is redirected just for being there."""
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/": None,
        f"{CANONICAL_BASE}/alpha/guide/": None,
        f"{CANONICAL_BASE}/blog/hello/": None,
        f"{CANONICAL_BASE}/alpha/?q=x": None,
    })


@needs_node
def test_every_other_host_lands_on_the_same_path(tmp_path):
    """Any non-canonical host 301s to the same path on the canonical one."""
    _routes(tmp_path, {
        "https://other.example.com/alpha/guide/":
            f"{CANONICAL_BASE}/alpha/guide/",
        "https://smmh-preview.pages.dev/projects/":
            f"{CANONICAL_BASE}/projects/",
        "https://other.example.com/": f"{CANONICAL_BASE}/",
    })


@needs_node
def test_off_host_redirect_preserves_the_query(tmp_path):
    _routes(tmp_path, {
        "https://other.example.com/alpha/?tab=api&page=2":
            f"{CANONICAL_BASE}/alpha/?tab=api&page=2",
    })


@needs_node
def test_retired_blog_subdomain_keeps_its_blog_prefix(tmp_path):
    """The blog subdomain's whole space was the blog, so it maps under it.

    Mapping it to the same path would send every live post link to the
    site root, where nothing answers.
    """
    _routes(tmp_path, {
        "https://blog.example.com/hello/": f"{CANONICAL_BASE}/blog/hello/",
        "https://blog.example.com/": f"{CANONICAL_BASE}/blog/",
        "https://blog.example.com/hello/?utm=x":
            f"{CANONICAL_BASE}/blog/hello/?utm=x",
    })


@needs_node
def test_without_a_legacy_blog_host_nothing_is_prefixed(tmp_path):
    js = _worker()
    js_no_legacy = generate_worker_js(
        CANONICAL_BASE, "",
        project_slugs=PROJECT_SLUGS, post_slugs=POST_SLUGS,
    )
    assert "HOST_PREFIXES = new Map([])" in js_no_legacy
    assert LEGACY_BLOG_HOST in js
    _routes(tmp_path, {
        "https://blog.example.com/hello/": f"{CANONICAL_BASE}/hello/",
    }, js=js_no_legacy)


# -- the redirect map: retired locale + version scheme -------------------------


@needs_node
def test_locale_version_paths_collapse_to_the_stable_address(tmp_path):
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/alpha/en/1.0.0/guide/":
            f"{CANONICAL_BASE}/alpha/guide/",
        f"{CANONICAL_BASE}/alpha/en/0.2.3/api/reference/":
            f"{CANONICAL_BASE}/alpha/api/reference/",
        f"{CANONICAL_BASE}/alpha/en/1.0.0/": f"{CANONICAL_BASE}/alpha/",
        f"{CANONICAL_BASE}/alpha/en/1.0.0": f"{CANONICAL_BASE}/alpha/",
    })


@needs_node
def test_any_version_segment_collapses_not_only_the_current_one(tmp_path):
    """Version-agnostic on purpose: an old deep link wants the page now.

    Archived versions are still served at ``/<slug>/v/<version>/``; what
    this rule answers is a link to a version that was current when it was
    copied.
    """
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/alpha/en/0.1/guide/": f"{CANONICAL_BASE}/alpha/guide/",
        f"{CANONICAL_BASE}/alpha/en/v2.0.0/guide/":
            f"{CANONICAL_BASE}/alpha/guide/",
        f"{CANONICAL_BASE}/alpha/en/1.0.0-rc.1/guide/":
            f"{CANONICAL_BASE}/alpha/guide/",
        f"{CANONICAL_BASE}/alpha/en/9.9.9/guide/":
            f"{CANONICAL_BASE}/alpha/guide/",
    })


@needs_node
def test_any_locale_segment_is_recognised(tmp_path):
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/alpha/fr/1.0.0/guide/":
            f"{CANONICAL_BASE}/alpha/guide/",
        f"{CANONICAL_BASE}/alpha/pt-br/1.0.0/guide/":
            f"{CANONICAL_BASE}/alpha/guide/",
    })


@needs_node
def test_the_archive_address_is_served_not_redirected(tmp_path):
    """``/v/<version>/`` is the current scheme for a superseded version."""
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/alpha/v/1.0.0/guide/": None,
        f"{CANONICAL_BASE}/alpha/v/1.0.0/": None,
    })


# -- the redirect map: retired post addresses ---------------------------------


@needs_node
def test_project_scoped_post_addresses_move_to_the_blog(tmp_path):
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/alpha/posts/hello/": f"{CANONICAL_BASE}/blog/hello/",
        f"{CANONICAL_BASE}/alpha/posts/hello": f"{CANONICAL_BASE}/blog/hello/",
        f"{CANONICAL_BASE}/beta/posts/world/": f"{CANONICAL_BASE}/blog/world/",
    })


@needs_node
def test_post_redirect_preserves_the_query(tmp_path):
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/alpha/posts/hello/?ref=x":
            f"{CANONICAL_BASE}/blog/hello/?ref=x",
    })


# -- unknown addresses fall through -------------------------------------------


@needs_node
def test_a_path_that_names_no_real_project_is_not_redirected(tmp_path):
    """Historical-looking is not historical. Unknown falls through to the 404."""
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/nosuch/en/1.0.0/guide/": None,
        f"{CANONICAL_BASE}/nosuch/posts/hello/": None,
    })


@needs_node
def test_a_post_the_blog_does_not_serve_is_not_redirected(tmp_path):
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/alpha/posts/nosuch/": None,
    })


@needs_node
def test_a_third_segment_that_is_not_a_version_is_not_redirected(tmp_path):
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/alpha/en/guide/page/": None,
    })


@needs_node
def test_the_flat_scheme_is_the_current_one_and_is_served(tmp_path):
    """The old flat sitemap addresses are what the site serves today."""
    _routes(tmp_path, {
        f"{CANONICAL_BASE}/alpha/": None,
        f"{CANONICAL_BASE}/alpha/guide/": None,
        f"{CANONICAL_BASE}/blog/hello/": None,
    })


# -- one hop, never two -------------------------------------------------------


@needs_node
def test_a_historical_path_on_a_foreign_host_is_one_hop(tmp_path):
    """Host and path are resolved together, so no redirect chains."""
    _routes(tmp_path, {
        "https://other.example.com/alpha/en/1.0.0/guide/":
            f"{CANONICAL_BASE}/alpha/guide/",
        "https://other.example.com/alpha/posts/hello/":
            f"{CANONICAL_BASE}/blog/hello/",
    })


@needs_node
def test_no_route_output_is_itself_routed_again(tmp_path):
    """Every redirect target is a final address: routing it returns null."""
    sources = [
        "https://other.example.com/alpha/guide/",
        "https://blog.example.com/hello/",
        f"{CANONICAL_BASE}/alpha/en/1.0.0/guide/",
        f"{CANONICAL_BASE}/alpha/posts/hello/",
    ]
    targets = _route(tmp_path, sources)
    assert all(t is not None for t in targets)
    assert _route(tmp_path, targets) == [None] * len(targets)


# -- structure ----------------------------------------------------------------


def test_worker_embeds_the_address_space_as_data():
    js = _worker()
    assert 'const PROJECT_SLUGS = new Set(["alpha", "beta"])' in js
    assert 'const POST_SLUGS = new Set(["hello", "world"])' in js


def test_worker_declares_the_legacy_host_prefix():
    js = _worker()
    assert f'["{LEGACY_BLOG_HOST}", "/blog"]' in js


def test_worker_exports_its_routing_for_testing():
    js = _worker()
    assert "export function routeRequest(" in js
    assert "export function legacyTarget(" in js


def test_worker_redirects_are_permanent():
    assert "Response.redirect(target, 301)" in _worker()


def test_worker_still_serves_assets():
    assert "env.ASSETS.fetch(request)" in _worker()


def test_worker_slugs_are_sorted_and_deduplicated():
    """The generated file is stable input to input, so deploys do not churn."""
    js = generate_worker_js(
        CANONICAL_BASE, LEGACY_BLOG_HOST,
        project_slugs=["beta", "alpha", "beta"],
        post_slugs=["world", "hello", "world"],
    )
    assert 'new Set(["alpha", "beta"])' in js
    assert 'new Set(["hello", "world"])' in js


def test_worker_size_tracks_projects_and_posts_not_pages():
    """The map is patterns plus two sets, never one entry per page."""
    slugs = [f"project-{i:03d}" for i in range(100)]
    posts = [f"post-{i:03d}" for i in range(200)]
    js = generate_worker_js(
        CANONICAL_BASE, LEGACY_BLOG_HOST,
        project_slugs=slugs, post_slugs=posts,
    )
    # Three hundred names at ~14 bytes each, plus a fixed body of routing.
    assert len(js) < 12000
    # And nothing page-shaped: no rule mentions an individual page.
    assert "/guide/" not in js
